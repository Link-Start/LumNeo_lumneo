# backend/services/llm_service.py
import os
import uuid
import json
import time
from fastapi import Request
from openai import AsyncOpenAI, APIError
from typing import List, Dict, AsyncGenerator, Optional
from backend.services.tools import get_all_tools, execute_tool
from backend.db.tool_calls import create_tool_call, update_tool_call, update_tool_call_arguments
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

        # ---------- 图像生成分支（不变） ----------
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

        MAX_STEPS = 60
        MAX_CONSECUTIVE_FAILURES = 3
        consecutive_failures = 0
        force_final = False

        for step in range(MAX_STEPS):
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
            if force_final or step == MAX_STEPS - 1:
                if force_final:
                    yield "\n⚠️ 工具连续调用失败次数过多，正在基于已收集信息生成最终总结...\n"
                else:
                    yield "\n⚠️ 工具调用次数已达上限，正在基于已收集信息生成最终总结...\n"

                current_messages.append({
                    "role": "user",
                    "content": ("【系统指令】你的工具调用已达限制或连续多次失败。"
                                "请立即放弃尝试调用工具，根据上面已经收集到的上下文信息，"
                                "直接回答我的问题并进行最终总结。")
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

                if final_answer_content:
                    segments.append({
                        "type": "text",
                        "content": final_answer_content
                    })

            if step_usage_record:
                last_step_usage = step_usage_record

            if first_token_time is not None:
                step_generation_time = time.time() - first_token_time
                last_step_generation_time = step_generation_time

            # ---------- 构建工具调用列表（内存中） ----------
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
            for idx, tc in valid_calls.items():
                if idx not in tool_preview_active:
                    logger.warning(f"跳过工具 {tc['function']['name']}，因为未找到预览状态")
                    continue

                local_call_id = tool_preview_active[idx]['call_id']
                func_name = tc["function"]["name"] or "未知工具"
                raw_args = tc["function"]["arguments"]

                if not tool_preview_active[idx].get('preview_sent', False):
                    yield f"<!--tool_preview:start:{local_call_id}:{func_name}-->"
                    tool_preview_active[idx]['preview_sent'] = True

                try:
                    args = json.loads(raw_args) if raw_args else {}
                except json.JSONDecodeError as e:
                    error_detail = f"JSON 解析失败: {e}\n原始参数: {raw_args[:200]}"
                    yield f"\n❌ 工具 `{func_name}` 参数错误：{error_detail}\n"
                    args = {"raw": raw_args, "parse_error": str(e)}

                # 更新数据库中的参数
                if chat_id:
                    try:
                        await update_tool_call_arguments(local_call_id, args)
                    except Exception as e:
                        logger.error(f"[数据库] 更新参数失败：{e}")

                # 执行工具
                start_time = time.time()
                failed = False
                try:
                    result = await execute_tool(func_name, args, mcp_manager)
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
                except Exception as e:
                    error_msg = str(e)
                    if len(error_msg) > 1000:
                        error_msg = error_msg[:1000] + "...(错误信息过长已截断)"
                    result = f"工具执行出错: {error_msg}"
                    failed = True

                exec_time_ms = int((time.time() - start_time) * 1000)

                # 统一格式化工具返回内容
                if isinstance(result, dict):
                    result_str = json.dumps(result, ensure_ascii=False)
                else:
                    result_str = str(result)

                # ===== 新增：大文件落盘逻辑 =====
                MAX_DB_LEN = 20000  # 设定一个阈值，比如超过2万字符就落盘
                meta_data = {}
                final_db_result = ""

                if len(result_str) > MAX_DB_LEN:
                    # 1. 落盘写入文件
                    file_dir = f"{chat_id}/{local_call_id}.txt"
                    file_path = f"{config.cache_dir}/{file_dir}"
                    os.makedirs(os.path.dirname(file_path), exist_ok=True)
                    with open(file_path, "w", encoding="utf-8") as f:
                        f.write(result_str)

                    # 2. 准备元数据（存入数据库的 meta_data 字段）
                    meta_data = {
                        "storage_type": "file",
                        "file_path": file_dir,
                        "size": len(result_str),
                        "preview": result_str[:1000]  # 截取前1000字用于前端展示摘要
                    }
                    # 3. 数据库实际的 result 字段只存一个简短提示，不存巨大文本
                    final_db_result = f"[数据量过大(共{len(result_str)}字)，完整内容已保存至本地文件]"
                else:
                    # 小数据直接存
                    final_db_result = result_str
                # ===================================

                # 更新结果和状态 (存入数据库，同时带上 meta_data)
                if chat_id:
                    try:
                        await update_tool_call(
                            call_id=local_call_id,
                            arguments=args,
                            result=final_db_result,    # 存入截断提示/小数据
                            status="error" if failed else "success",
                            execution_time=exec_time_ms,
                            error_message=result if failed else None,
                            meta_data=meta_data        # 🟢 关键：存入文件路径和预览
                        )
                    except Exception as e:
                        logger.error(f"[数据库] 更新结果失败：{e}")

                # ===== 将状态同步写入到 segments 列表中 =====
                status_val = "error" if failed else "success"
                err_msg = result if failed else None
                
                # 遍历已经记录在 segments 里的 tool_call 片段，把状态填进去
                for seg in segments:
                    if seg.get('type') == 'tool_call' and seg.get('content', {}).get('id') == local_call_id:
                        seg['content']['status'] = status_val
                        if err_msg:
                            seg['content']['error_message'] = err_msg  # 把失败信息也带上前端渲染
                        break

                # 更新连续失败计数
                if failed:
                    consecutive_failures += 1
                    yield f"<!--tool_status:{local_call_id}:error-->"
                else:
                    consecutive_failures = 0
                    yield f"<!--tool_status:{local_call_id}:success-->"

                yield f"<!--tool_preview:end:{local_call_id}-->"
                del tool_preview_active[idx]

                # 将工具结果加入内存（用于下一轮）
                current_messages.append({
                    "role": "tool",
                    "tool_call_id": local_call_id,
                    "content": result_str
                })

            yield "<!--tool_calls:end-->"

            if consecutive_failures >= MAX_CONSECUTIVE_FAILURES:
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
