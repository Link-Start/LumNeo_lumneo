# backend/services/llm_service.py
import os
import uuid
import json
import time
import asyncio
from fastapi import Request
from openai import AsyncOpenAI, APIError
from typing import List, Dict, AsyncGenerator, Optional
from backend.services.tools import get_all_tools, execute_tool
from backend.services.tools import is_dangerous_tool
from backend.db.decisions import create_decision, get_decision_status
from backend.db.tool_calls import create_tool_call, update_tool_call, update_tool_call_arguments, update_tool_call_status, get_tool_call_status
from backend.db.messages import add_message
from config_loader import config
from backend.bootstrap import logger


class LLMService:
    instance: Optional["LLMService"] = None

    def __init__(self,
                 model_type: str,
                 model_name: str,
                 api_key: str = "",
                 base_url: str = None,
                 thinking: str = 'enabled',
                 reasoning_effort: str = 'high'):
        self.model_type = model_type
        self.model_name = model_name
        self.thinking = thinking
        self.reasoning_effort = reasoning_effort if thinking == 'enabled' else None
        self.client = AsyncOpenAI(api_key=api_key or 'none', base_url=base_url)


    async def _process_single_tool(
        self,
        idx: str,
        tc: dict,
        tool_preview_active: dict,
        segments: list,
        current_messages: list,
        chat_id: Optional[str],
        mcp_manager,
        approval_mode: bool,
        auto_decision: bool,
        tool_timeout: int,
        retry_count: int,
        retry_delay: int,
        request: Optional[Request],
        skip_approval: bool = False, 
    ) -> dict:
        """
        处理单个工具调用，返回一个字典，包含所有需要 yield 的内容和其他状态。
        """
        outputs = []          # 本工具产生的所有输出字符串
        new_segments = []     # 本工具新增/替换的 segments 条目
        
        if idx not in tool_preview_active:
            outputs.append(f"⚠️ 跳过工具 {tc['function']['name']}，未找到预览状态\n")
            return {
                'outputs': outputs,
                'new_segments': new_segments,
                'call_id': None,
                'failed': True,
                'status': 'skipped',
                'error_message': '预览状态缺失',
                'result_str': '',
                'exec_time_ms': 0,
                'meta_data': {},
                'tool_message_content': None
            }

        local_call_id = tool_preview_active[idx]['call_id']
        func_name = tc["function"]["name"] or "未知工具"
        raw_args = tc["function"]["arguments"]

        # 确保预览已发送
        if not tool_preview_active[idx].get('preview_sent', False):
            outputs.append(f"<!--tool_preview:start:{local_call_id}:{func_name}-->")
            tool_preview_active[idx]['preview_sent'] = True

        # 解析参数
        try:
            args = json.loads(raw_args) if raw_args else {}
        except json.JSONDecodeError as e:
            error_detail = f"JSON 解析失败: {e}\n原始参数: {raw_args[:200]}"
            outputs.append(f"\n❌ 工具 `{func_name}` 参数错误：{error_detail}\n")
            args = {"raw": raw_args, "parse_error": str(e)}

        if chat_id:
            try:
                await update_tool_call_arguments(local_call_id, args)
            except Exception as e:
                logger.error(f"[数据库] 更新参数失败：{e}")

        # ---------- 审批逻辑 ----------
        need_approval = False
        if approval_mode and not skip_approval:
            if auto_decision:
                need_approval = is_dangerous_tool(func_name)
            else:
                need_approval = True

        if need_approval:
            await update_tool_call_status(local_call_id, "pending_confirmation")

            args_preview = json.dumps(args, ensure_ascii=False)
            if len(args_preview) > 2000:
                args_preview = args_preview[:2000] + "...(已截断)"
            outputs.append(f"<!--tool_confirm_required:{local_call_id}:{func_name}:{args_preview}-->")

            # 直接返回需要审批的状态，不等待
            return {
                'outputs': outputs,
                'new_segments': new_segments,
                'call_id': local_call_id,
                'failed': False,
                'status': 'need_approval',
                'error_message': None,
                'result_str': '',
                'exec_time_ms': 0,
                'meta_data': {},
                'tool_message_content': None,
                'approval_info': {
                    'local_call_id': local_call_id,
                    'func_name': func_name,
                    'args_preview': args_preview,
                    'args': args,
                }
            }

        # ---------- 执行工具（带重试和超时） ----------
        exec_time_ms = 0
        failed = False
        result = None

        for attempt in range(retry_count + 1):
            try:
                start_time = time.time()
                async with asyncio.timeout(tool_timeout):
                    result = await execute_tool(func_name, args, mcp_manager)
                exec_time_ms = int((time.time() - start_time) * 1000)

                # ===== 检查逻辑失败 =====
                is_logical_failure = False
                if isinstance(result, dict) and result.get("success") is False:
                    is_logical_failure = True
                elif isinstance(result, str):
                    try:
                        parsed = json.loads(result)
                        if isinstance(parsed, dict) and parsed.get("success") is False:
                            is_logical_failure = True
                    except json.JSONDecodeError:
                        pass

                # 如果是逻辑失败，且还有重试次数，则重试
                if is_logical_failure and attempt < retry_count:
                    outputs.append(f"\n🔄 工具 `{func_name}` 逻辑执行失败（返回 success=false），{retry_delay}秒后重试（{attempt + 1}/{retry_count}）...\n")
                    await asyncio.sleep(retry_delay)
                    continue
                elif is_logical_failure:
                    # 最后一次尝试，标记为失败并退出循环
                    failed = True
                    break

                # 正常成功，跳出重试循环
                break

            except asyncio.TimeoutError:
                result = f"工具执行超时（{tool_timeout}秒）"
                failed = True
                if attempt < retry_count:
                    outputs.append(f"\n⏱️ 工具 `{func_name}` 执行超时，{retry_delay}秒后重试（{attempt + 1}/{retry_count}）...\n")
                    await asyncio.sleep(retry_delay)
                    continue
                else:
                    outputs.append(f"\n❌ 工具 `{func_name}` 执行超时（{tool_timeout}秒），已达最大重试次数\n")
                    break
            except Exception as e:
                error_msg = str(e)
                if len(error_msg) > 1000:
                    error_msg = error_msg[:1000] + "...(错误信息过长已截断)"
                result = f"工具执行出错: {error_msg}"
                failed = True
                if attempt < retry_count:
                    outputs.append(f"\n🔄 工具 `{func_name}` 执行出错，{retry_delay}秒后重试（{attempt + 1}/{retry_count}）...\n")
                    await asyncio.sleep(retry_delay)
                    continue
                else:
                    outputs.append(f"\n❌ 工具 `{func_name}` 执行出错，已达最大重试次数\n")
                    break

        # 检查结果是否标记为失败
        if result is not None and not failed:
            if isinstance(result, str):
                try:
                    result_obj = json.loads(result)
                    if isinstance(result_obj, dict) and result_obj.get("success") is False:
                        failed = True
                except json.JSONDecodeError:
                    if result.startswith("工具执行出错:"):
                        failed = True
            elif isinstance(result, dict) and result.get("success") is False:
                failed = True

        # 格式化结果
        if result is None:
            result = "工具执行未返回任何结果"
        if isinstance(result, dict):
            result_str = json.dumps(result, ensure_ascii=False)
        else:
            result_str = str(result)

        # 大文件落盘
        MAX_DB_LEN = 20000
        meta_data = {}
        final_db_result = ""
        if len(result_str) > MAX_DB_LEN:
            file_dir = f"{chat_id}/{local_call_id}.txt" if chat_id else f"unknown/{local_call_id}.txt"
            file_path = f"{config.cache_dir}/{file_dir}"
            os.makedirs(os.path.dirname(file_path), exist_ok=True)
            with open(file_path, "w", encoding="utf-8") as f:
                f.write(result_str)
            meta_data = {
                "storage_type": "file",
                "file_path": file_dir,
                "size": len(result_str),
                "preview": result_str[:1000]
            }
            final_db_result = f"[数据量过大(共{len(result_str)}字)，完整内容已保存至本地文件]"
        else:
            final_db_result = result_str

        # 更新数据库
        if chat_id:
            try:
                await update_tool_call(
                    call_id=local_call_id,
                    arguments=args,
                    result=final_db_result,
                    status="error" if failed else "success",
                    execution_time=exec_time_ms,
                    error_message=result if failed else None,
                    meta_data=meta_data
                )
            except Exception as e:
                logger.error(f"[数据库] 更新结果失败：{e}")

        # 准备返回数据
        status_val = "error" if failed else "success"
        err_msg = result if failed else None

        # 构造状态输出
        outputs.append(f"<!--tool_status:{local_call_id}:{status_val}-->")
        outputs.append(f"<!--tool_preview:end:{local_call_id}-->")

        # 构造替换的 segments 片段
        seg_content = {
            'id': local_call_id,
            'name': func_name,
            'status': status_val
        }
        if err_msg:
            seg_content['error_message'] = err_msg
        new_segments.append({
            'type': 'tool_call',
            'content': seg_content
        })

        # 删除预览状态
        if idx in tool_preview_active:
            del tool_preview_active[idx]

        return {
            'outputs': outputs,
            'new_segments': new_segments,
            'call_id': local_call_id,
            'failed': failed,
            'status': status_val,
            'error_message': err_msg,
            'result_str': result_str,
            'exec_time_ms': exec_time_ms,
            'meta_data': meta_data,
            'tool_message_content': result_str
        }

    async def generate_response(
        self,
        messages: List[Dict[str, str]],
        enable_tools: bool = False,
        tools: Optional[List[Dict]] = None,
        request: Optional[Request] = None,
        mcp_manager=None,
        params: Dict = None,
        profile_id:int = None,
        model_id:str = None,
        chat_id: Optional[str] = None,
        turn_index: Optional[int] = None,
    ) -> AsyncGenerator[str, None]:
        params = params or {}
        current_step_reasoning = ""

        max_steps = params.get('max_iterations', 10)
        max_consecutive_failures = params.get('failure_threshold', 3)
        tool_timeout = params.get('tool_timeout', 30)
        retry_count = params.get('retry_count', 2)
        retry_delay = params.get('retry_delay', 1)
        failure_behavior = params.get('failure_behavior', 'continue')  # continue / stop / ask
        max_parallel = params.get('max_parallel', 5)
        approval_mode = params.get('approval_mode', True)
        auto_decision = params.get('auto_decision', False)

        # 只有审批模式关闭时，才启用并行执行
        enable_parallel = not approval_mode and max_parallel > 1

        # ---------- 图像生成分支 ----------
        if "image" in self.model_name.lower():
            prompt = ""
            for msg in reversed(messages):
                if msg.get("role") == "user":
                    prompt = msg.get("content", "")
                    break

            if not prompt:
                yield "❌ 未找到有效的用户提示词，无法生成图像。"
                return

            size = params.get("size", "1024x768")
            quality = params.get("quality", "standard")
            n = params.get("n", 1)

            try:
                response = await self.client.images.generate(
                    model=self.model_name,
                    prompt=prompt,
                    size=size,
                    quality=quality,
                    n=n,
                )

                if not response.data or len(response.data) == 0:
                    yield "❌ 图像生成服务未返回有效结果。"
                    return

                img_data = response.data[0]

                if hasattr(img_data, 'url') and img_data.url:
                    image_url = img_data.url
                    yield f"![生成的图片]({image_url})"
                else:
                    if hasattr(img_data, 'b64_json') and img_data.b64_json:
                        yield "⚠️ 图像生成服务仅返回 base64 数据，无法提供直接链接。"
                    else:
                        yield "❌ 图像生成服务未返回图片 URL 或 base64 数据。"
                return

            except APIError as e:
                yield f"❌ 图像生成 API 错误：{e.message}"
            except Exception as e:
                yield f"❌ 图像生成失败：{str(e)}"
            return

        # ---------- 文本生成 + 工具调用分支 ----------
        current_messages = messages.copy()

        if tools is None and enable_tools:
            tools = await get_all_tools(mcp_manager)

        # 用于记录整轮的结构化片段（按出现顺序）
        segments = []
        reasoning_buffer = ""
        reasoning_start_time = None
        in_reasoning = False

        # 全步骤累计 token
        total_usage_all_steps = {
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "total_tokens": 0,
            "completion_tokens_details": {}
        }

        # 最后一步 token 和生成耗时
        last_step_usage = None
        last_step_generation_time = 0.0

        consecutive_failures = 0
        force_final = False

        for step in range(max_steps):
            final_answer_content = ""   # 强制在每次循环开始前声明
            if request and await request.is_disconnected():
                break

            tool_calls_by_index = {}
            step_usage_record = None
            step_generation_time = 0.0

            kwargs = {
                "model": self.model_name,
                "messages": current_messages,
                "stream": True,
                "reasoning_effort": self.reasoning_effort,
                "temperature": params.get('temperature', 1.0),
                "top_p": params.get('top_p', 0.95),
                "frequency_penalty": params.get('frequency_penalty', 0.0),
                "presence_penalty": params.get('presence_penalty', 0.0),
                "stream_options": {"include_usage": True},
            }

            extra_body = {
                "top_k": params.get('top_k', 20),
                "chat_template_kwargs": {},
                "thinking": {"type": self.thinking}
            }

            if self.thinking == "enabled":
                extra_body["enable_thinking"] = True
                extra_body["preserve_thinking"] = True
                extra_body["chat_template_kwargs"]["enable_thinking"] = True
                extra_body["chat_template_kwargs"]["preserve_thinking"] = True
            if self.thinking == "disabled":
                extra_body["enable_thinking"] = False
                extra_body["preserve_thinking"] = False
                extra_body["chat_template_kwargs"]["enable_thinking"] = False
                extra_body["chat_template_kwargs"]["preserve_thinking"] = False

            kwargs["extra_body"] = extra_body

            # 强制总结逻辑
            if force_final or step == max_steps - 1:
                # 根据触发原因选择不同的提示
                if force_final:
                    yield "\n⚠️ 工具调用遇到了一些阻碍，正在基于已有信息生成最终总结...\n"
                    system_instruction = (
                        "【系统提示】工具调用遇到了一些阻碍，暂时无法继续执行。"
                        "请基于目前已获取的信息，为用户提供最有帮助的回答。"
                        "如果信息不足以完成任务，请友好地告知用户并给出建议。"
                    )
                else:
                    yield "\n⚠️ 工具调用次数已达上限，正在基于已有信息生成最终总结...\n"
                    system_instruction = (
                        "【系统提示】本轮工具调用次数已用完，接下来将基于已有信息回答。"
                        "请综合已经收集到的上下文，为用户提供全面、准确的回应。"
                    )

                current_messages.append({
                    "role": "user",
                    "content": system_instruction
                })
                kwargs["messages"] = current_messages
                tools = None
                force_final = False
            elif tools:
                kwargs["tools"] = tools
                kwargs["tool_choice"] = "auto"

            try:
                response = await self.client.chat.completions.create(**kwargs)
            except APIError as e:
                logger.error(f"LLM API 错误:{e.message}")
                error_content = f"❌ 模型服务错误：{e.message}"
                segments.append({
                    "type": "error",
                    "content": error_content
                })
                yield f"\n❌ 模型服务错误：{e.message}"
                break

            first_token_time = None
            tool_preview_active = {}
            tool_calls_started = False
            final_answer_content = ""

            async for chunk in response:
                if request and await request.is_disconnected():
                    break

                # ---------- usage 收集 ----------
                if hasattr(chunk, 'usage') and chunk.usage:
                    step_usage = chunk.usage
                    try:
                        su = step_usage.model_dump()
                    except AttributeError:
                        su = dict(step_usage)

                    total_usage_all_steps["prompt_tokens"] += su.get("prompt_tokens", 0) or 0
                    total_usage_all_steps["completion_tokens"] += su.get("completion_tokens", 0) or 0
                    total_usage_all_steps["total_tokens"] += su.get("total_tokens", 0) or 0

                    details = su.get("completion_tokens_details") or {}
                    for k, v in details.items():
                        total_usage_all_steps["completion_tokens_details"][k] = \
                            total_usage_all_steps["completion_tokens_details"].get(k, 0) + (v or 0)

                    step_usage_record = {
                        "prompt_tokens": su.get("prompt_tokens", 0) or 0,
                        "completion_tokens": su.get("completion_tokens", 0) or 0,
                        "total_tokens": su.get("total_tokens", 0) or 0,
                        "completion_tokens_details": details
                    }

                if chunk.choices:
                    delta = chunk.choices[0].delta
                    if first_token_time is None:
                        if (getattr(delta, 'reasoning_content', None) or
                            getattr(delta, 'content', None) or
                            getattr(delta, 'tool_calls', None)):
                            first_token_time = time.time()
                else:
                    continue

                delta = chunk.choices[0].delta
                reasoning = getattr(delta, 'reasoning_content', None)
                tool_calls_data = getattr(delta, 'tool_calls', None)
                delta_content = getattr(delta, 'content', None)

                # ---------- 推理处理 ----------
                if reasoning:
                    if not in_reasoning:
                        in_reasoning = True
                        reasoning_start_time = time.time()
                        yield "<!--reasoning:start-->"
                    reasoning_buffer += reasoning
                    yield reasoning
                    continue

                # 推理结束（遇到 content 或 tool_calls）
                if in_reasoning and (delta_content or tool_calls_data):
                    reasoning_time = time.time() - reasoning_start_time
                    yield f"<!--reasoning:end:{reasoning_time:.2f}-->"
                    current_step_reasoning = reasoning_buffer
                    # 将推理片段加入 segments
                    segments.append({
                        "type": "reasoning",
                        "content": reasoning_buffer,
                        "duration": f"{reasoning_time:.2f}"
                    })
                    reasoning_buffer = ""
                    in_reasoning = False

                # ---------- 工具调用处理 ----------
                if tool_calls_data:
                    if not tool_calls_started:
                        tool_calls_started = True
                        yield "\n<!--tool_calls:start-->"

                    for tc_delta in tool_calls_data:
                        idx = getattr(tc_delta, 'index', None)
                        if idx is None:
                            idx = tc_delta.id if tc_delta.id else str(uuid.uuid4())

                        if idx not in tool_preview_active and tc_delta.function and tc_delta.function.name:
                            call_id = getattr(tc_delta, 'id', str(uuid.uuid4()))
                            func_name = tc_delta.function.name
                            tool_preview_active[idx] = {
                                'call_id': call_id,
                                'name': func_name,
                                'db_created': False,
                                'preview_sent': True
                            }

                            yield f"<!--tool_preview:start:{call_id}:{func_name}-->"

                            # 创建数据库记录（使用 chat_id）
                            if chat_id:
                                try:
                                    await create_tool_call(
                                        chat_id=chat_id,
                                        call_id=call_id,
                                        tool_name=func_name
                                    )
                                    tool_preview_active[idx]['db_created'] = True
                                except Exception as e:
                                    logger.error(f"[数据库] 创建工具调用记录失败： {e}")

                            # 添加轻量工具调用片段到 segments
                            segments.append({
                                "type": "tool_call",
                                "content": {
                                    "id": call_id,
                                    "name": func_name
                                },
                            })

                        if idx not in tool_calls_by_index:
                            tool_calls_by_index[idx] = {
                                "id": getattr(tc_delta, 'id', None),
                                "type": "function",
                                "function": {"name": "", "arguments": ""},
                            }
                        target = tool_calls_by_index[idx]
                        if tc_delta.id:
                            target["id"] = tc_delta.id
                        if tc_delta.function:
                            if tc_delta.function.name and not target["function"]["name"]:
                                target["function"]["name"] = tc_delta.function.name
                            arg_delta = tc_delta.function.arguments or ""
                            target["function"]["arguments"] += arg_delta

                # ---------- 普通文本内容 ----------
                elif delta_content:
                    final_answer_content += delta_content
                    yield delta_content

            # 如果推理还未结束（流结束时仍有未闭合的推理），强制结束
            if in_reasoning:
                reasoning_time = time.time() - reasoning_start_time
                yield f"<!--reasoning:end:{reasoning_time:.2f}-->"
                segments.append({
                    "type": "reasoning",
                    "content": reasoning_buffer,
                    "duration": f"{reasoning_time:.2f}"
                })
                reasoning_buffer = ""
                in_reasoning = False

            # ===== 当前 step 的文本立即落盘到 segments =====
            if final_answer_content:
                try:
                    parsed = json.loads(final_answer_content)
                    if isinstance(parsed, list):
                        logger.warning("检测到异常的数据结构序列化，跳过 type:text 落盘")
                        final_answer_content = ""
                except Exception:
                    pass

                if final_answer_content and final_answer_content.strip():
                    segments.append({
                        "type": "text",
                        "content": final_answer_content
                    })

            if step_usage_record:
                last_step_usage = step_usage_record

            if first_token_time is not None:
                step_generation_time = time.time() - first_token_time
                last_step_generation_time = step_generation_time

            # ---------- 构建工具调用列表 ----------
            tool_calls = {}
            for idx, tc in tool_calls_by_index.items():
                tool_calls[tc["id"]] = tc

            if tool_calls and request and await request.is_disconnected():
                break

            if not tool_calls:
                break

            # ---------- 验证并执行工具 ----------
            valid_calls = {}
            for idx, tc in tool_calls_by_index.items():
                if tc["function"]["name"].strip():
                    valid_calls[idx] = tc
                else:
                    yield "\n⚠️ 检测到无效工具调用（名称空白），已忽略。\n"

            if not valid_calls:
                break

            if not tool_calls_started:
                yield "\n<!--tool_calls:start-->"

            # 将 assistant 消息加入内存（用于下一轮）
            assistant_msg = {
                "role": "assistant",
                "content": None,
                "tool_calls": list(tool_calls.values())
            }
            if current_step_reasoning:
                assistant_msg["reasoning_content"] = current_step_reasoning
            current_messages.append(assistant_msg)

            # ---------- 执行工具 ----------
            # 先构建任务列表
            tool_tasks = []
            tool_infos = []  # 保存原始顺序
            for idx, tc in valid_calls.items():
                # 将每个工具的处理封装为异步任务
                task = self._process_single_tool(
                    idx=idx,
                    tc=tc,
                    tool_preview_active=tool_preview_active,
                    segments=segments,
                    current_messages=current_messages,
                    chat_id=chat_id,
                    mcp_manager=mcp_manager,
                    approval_mode=approval_mode,
                    auto_decision=auto_decision,
                    tool_timeout=tool_timeout,
                    retry_count=retry_count,
                    retry_delay=retry_delay,
                    request=request
                )
                tool_tasks.append(task)
                tool_infos.append((idx, tc))

            # 执行所有任务（根据 enable_parallel 决定串/并行）
            if enable_parallel and len(tool_tasks) > 1:
                # 并行执行，使用 Semaphore 控制并发数
                semaphore = asyncio.Semaphore(max_parallel)
                async def run_with_semaphore(task):
                    async with semaphore:
                        return await task
                # 所有任务并发执行
                results = await asyncio.gather(
                    *[run_with_semaphore(task) for task in tool_tasks],
                    return_exceptions=False
                )
            else:
                # 串行执行
                results = []
                for task in tool_tasks:
                    results.append(await task)

            # 处理结果
            for (idx, tc), res in zip(tool_infos, results):
                result = res  # 允许后续重新赋值
                # 如果结果异常
                if isinstance(result, Exception):
                    outputs = [f"\n❌ 工具 `{tc['function']['name']}` 处理异常: {str(result)}\n"]
                    new_segments = []
                    call_id = None
                    failed = True
                    status = 'error'
                    err_msg = str(result)
                    result_str = ''
                    tool_msg = f"工具处理异常: {str(result)}"
                else:
                    # ---------- 审批特殊处理 ----------
                    if result.get('status') == 'need_approval':
                        # 立即将审批标记发送给前端
                        for out in result['outputs']:
                            yield out

                        local_call_id = result['approval_info']['local_call_id']
                        confirmed = False
                        # 轮询等待用户决定（最长 50 秒）
                        for _ in range(50):
                            if request and await request.is_disconnected():
                                break
                            status = await get_tool_call_status(local_call_id)
                            if status == "confirmed":
                                confirmed = True
                                break
                            if status == "cancelled":
                                confirmed = False
                                break
                            await asyncio.sleep(1)

                        if confirmed:
                            # 审批通过，再次调用 _process_single_tool 跳过审批直接执行
                            try:
                                result = await self._process_single_tool(
                                    idx=idx,
                                    tc=tc,
                                    tool_preview_active=tool_preview_active,
                                    segments=segments,
                                    current_messages=current_messages,
                                    chat_id=chat_id,
                                    mcp_manager=mcp_manager,
                                    approval_mode=approval_mode,
                                    auto_decision=auto_decision,
                                    tool_timeout=tool_timeout,
                                    retry_count=retry_count,
                                    retry_delay=retry_delay,
                                    request=request,
                                    skip_approval=True
                                )
                            except Exception as e:
                                # 二次调用失败时构造错误结果
                                result = {
                                    'outputs': [f"\n❌ 工具 `{tc['function']['name']}` 执行异常: {str(e)}\n"],
                                    'new_segments': [],
                                    'call_id': local_call_id,
                                    'failed': True,
                                    'status': 'error',
                                    'error_message': str(e),
                                    'result_str': '',
                                    'exec_time_ms': 0,
                                    'meta_data': {},
                                    'tool_message_content': f"工具执行异常: {str(e)}"
                                }
                        else:
                            # 用户拒绝
                            yield f"<!--tool_status:{local_call_id}:rejected-->"
                            yield f"<!--tool_preview:end:{local_call_id}-->"

                            # 更新 segments（替换原有轻量片段）
                            rejected_seg = {
                                'type': 'tool_call',
                                'content': {
                                    'id': local_call_id,
                                    'name': result['approval_info']['func_name'],
                                    'status': 'rejected',
                                    'error_message': '用户拒绝了此工具调用'
                                }
                            }
                            # 在 segments 中找到并替换，或追加
                            found = False
                            for i, existing in enumerate(segments):
                                if (existing.get('type') == 'tool_call' and
                                    existing.get('content', {}).get('id') == local_call_id):
                                    segments[i] = rejected_seg
                                    found = True
                                    break
                            if not found:
                                segments.append(rejected_seg)

                            # 更新数据库
                            await update_tool_call(
                                call_id=local_call_id,
                                arguments=result['approval_info']['args'],
                                result="用户拒绝了此工具调用",
                                status="rejected",
                                execution_time=0,
                                error_message="用户拒绝",
                                meta_data={}
                            )

                            # 清理预览状态
                            if idx in tool_preview_active:
                                del tool_preview_active[idx]

                            # 将工具结果消息加入 current_messages
                            current_messages.append({
                                "role": "tool",
                                "tool_call_id": local_call_id,
                                "content": "用户拒绝了此工具调用，请直接回答工具被拒绝，无法执行。"
                            })

                            # 拒绝不计入连续失败（根据你的业务可调整）
                            continue   # 跳过后续的通用处理，处理下一个工具

                    # ---------- 通用结果处理（原逻辑）----------
                    outputs = result['outputs']
                    new_segments = result['new_segments']
                    call_id = result['call_id']
                    failed = result['failed']
                    status = result['status']
                    err_msg = result['error_message']
                    result_str = result['result_str']
                    tool_msg = result['tool_message_content']

                # 1. 依次 yield 本工具的所有输出（保证顺序）
                for out in outputs:
                    yield out

                # 2. 更新 segments（替换或新增）
                for seg in new_segments:
                    if seg.get('type') == 'tool_call':
                        seg_id = seg['content'].get('id')
                        if seg_id:
                            # 在 segments 中查找并更新
                            found = False
                            for i, existing in enumerate(segments):
                                if existing.get('type') == 'tool_call' and existing.get('content', {}).get('id') == seg_id:
                                    segments[i] = seg
                                    found = True
                                    break
                            if not found:
                                segments.append(seg)
                    else:
                        segments.append(seg)

                # 3. 更新连续失败计数（注意：并行时仍按顺序更新，保证连续性判断正确）
                if failed:
                    consecutive_failures += 1
                else:
                    consecutive_failures = 0

                # 4. 追加工具结果消息
                if call_id and tool_msg:
                    current_messages.append({
                        "role": "tool",
                        "tool_call_id": call_id,
                        "content": tool_msg
                    })

            # 所有工具执行完成后，输出结束标记
            yield "<!--tool_calls:end-->"

            # 连续失败阈值判断
            if consecutive_failures >= max_consecutive_failures:
                # 根据失败行为配置决定处理方式
                if failure_behavior == 'stop':
                    yield f"\n❌ 工具连续失败 {consecutive_failures} 次，已停止执行（失败行为：停止）\n"
                    break
                elif failure_behavior == 'ask':
                    # 1. 创建决策记录
                    msg = f"⚠️ 工具连续失败 {consecutive_failures} 次，是否继续执行？"
                    decision_id = await create_decision(
                        chat_id=chat_id,
                        turn_index=turn_index,
                        message=msg,
                        timeout_seconds=50
                    )
                    # 2. 向前端发送询问标记
                    yield f"<!--ask_decision:{decision_id}:{msg}-->"
                    
                    # 3. 轮询等待用户响应（最多 50 秒）
                    confirmed = False
                    for _ in range(50):
                        if request and await request.is_disconnected():
                            break
                        status = await get_decision_status(decision_id)
                        if status == "continue":
                            confirmed = True
                            break
                        elif status == "stop":
                            confirmed = False
                            break
                        await asyncio.sleep(1)
                    
                    # 4. 超时或断开，视为 stop
                    if not confirmed:
                        prompt_text = "\n⚠️ 用户停止执行或未响应，已终止。\n"
                        yield f"{prompt_text}"
                        segments.append({"type": "text", "content": prompt_text})
                        break
                    
                    # 5. 用户选择继续
                    prompt_text = "\n✅ 用户选择继续执行，正在重试工具调用...\n"
                    yield f"{prompt_text}"
                    segments.append({"type": "text", "content": prompt_text})
                    consecutive_failures = 0
                    max_steps += 3  # 增加重试步骤数
                else:
                    force_final = True

        # ---------- 最终 token 统计 ----------
        if last_step_usage and last_step_usage["completion_tokens"] > 0:
            tokens = last_step_usage["completion_tokens"]
            gen_time = last_step_generation_time
            if tokens < 20 or gen_time < 0.1:
                speed_str = "⚡瞬间完成"
            else:
                speed = tokens / gen_time if gen_time > 0 else 0.0
                speed_str = f"{speed:.2f} token/s"
            token_info = {
                "final_answer_usage": last_step_usage,
                "total_usage_all_steps": total_usage_all_steps,
                "speed": speed_str
            }
            yield f"\n<!--token_usage:{json.dumps(token_info)}-->"

            # 将 token 统计加入 segments
            segments.append({
                "type": "token_usage",
                "content": token_info
            })

        # ---------- 将结构化内容写入数据库 ----------
        if chat_id and turn_index is not None:
            segments_json = json.dumps(segments, ensure_ascii=False)
            await add_message(
                chat_id=chat_id,
                role="assistant",
                content=segments_json,
                profile_id=profile_id,
                model_id=model_id,
                file_ref=None,
                turn_index=turn_index
            )
            yield f"<!--segments_complete:{segments_json}-->"
