# backend/services/llm_service.py
import uuid
import json
import time
from fastapi import Request
from openai import AsyncOpenAI, APIError
from typing import List, Dict, AsyncGenerator, Optional
from backend.services.tools import get_all_tools, execute_tool
from backend.db.tool_calls import create_tool_call, update_tool_call, update_tool_call_arguments
from backend.db.chats import add_message, update_message


class LLMService:
    instance: Optional["LLMService"] = None

    def __init__(self,
                 model_type: str,
                 model_name: str,
                 api_key: str = "",
                 base_url: str = None,
                 thinking: str = 'enabled'):
        self.model_type = model_type
        self.model_name = model_name
        self.thinking = thinking
        self.client = AsyncOpenAI(api_key=api_key or None, base_url=base_url)

    async def generate_response(
        self,
        messages: List[Dict[str, str]],
        enable_tools: bool = False,
        tools: Optional[List[Dict]] = None,
        request: Optional[Request] = None,
        mcp_manager=None,
        params: Dict = None,
        message_id: Optional[int] = None,
        chat_id: Optional[str] = None,
    ) -> AsyncGenerator[str, None]:
        params = params or {}

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

        # ---------- 原有文本生成 + 工具调用分支 ----------
        current_messages = messages.copy()

        if tools is None and enable_tools:
            tools = await get_all_tools(mcp_manager)

        reasoning_start_time = None

        # 全步骤累计 token（计费总量）
        total_usage_all_steps = {
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "total_tokens": 0,
            "completion_tokens_details": {}
        }

        # 最后一步的 token 和生成耗时（用于展示最终回答速度）
        last_step_usage = None
        last_step_generation_time = 0.0

        MAX_STEPS = 60
        MAX_CONSECUTIVE_FAILURES = 3
        consecutive_failures = 0
        force_final = False

        for step in range(MAX_STEPS):
            if request and await request.is_disconnected():
                break

            tool_calls_by_index = {}
            reasoning_buffer = ""
            in_reasoning = False

            step_usage_record = None
            step_generation_time = 0.0

            kwargs = {
                "model": self.model_name,
                "messages": current_messages,
                "stream": True,
                "temperature": params.get('temperature', 1.0),
                "top_p": params.get('top_p', 0.95),
                "frequency_penalty": params.get('frequency_penalty', 0.0),
                "presence_penalty": params.get('presence_penalty', 0.0),
                "stream_options": {"include_usage": True},
            }

            extra_body = {
                "top_k": params.get('top_k', 20),
                "chat_template_kwargs": {
                    "add_generation_prompt": True,
                }
            }

            if self.thinking == "enabled":
                extra_body["enable_thinking"] = True
                extra_body["preserve_thinking"] = True
                extra_body["chat_template_kwargs"]["enable_thinking"] = True
                extra_body["chat_template_kwargs"]["preserve_thinking"] = True

            kwargs["extra_body"] = extra_body

            # 连续失败上限或达到最大步数，都强制让模型直接总结
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

                if reasoning:
                    if not in_reasoning:
                        in_reasoning = True
                        reasoning_start_time = time.time()
                        yield "<!--reasoning:start-->"
                    reasoning_buffer += reasoning
                    yield reasoning
                    continue

                if in_reasoning and (delta_content or tool_calls_data):
                    reasoning_time = time.time() - reasoning_start_time
                    yield f"<!--reasoning:end:{reasoning_time:.2f}-->"
                    in_reasoning = False

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

                            # 创建数据库记录
                            if message_id:
                                try:
                                    await create_tool_call(
                                        message_id=message_id,
                                        call_id=call_id,
                                        tool_name=func_name
                                    )
                                    tool_preview_active[idx]['db_created'] = True
                                except Exception as e:
                                    print(f"[DB] Failed to create tool call record: {e}")

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

                elif delta_content:
                    final_answer_content += delta_content
                    yield delta_content

            if in_reasoning:
                reasoning_time = time.time() - reasoning_start_time
                yield f"<!--reasoning:end:{reasoning_time:.2f}-->"

            if step_usage_record:
                last_step_usage = step_usage_record

            # 记录本步骤生成时间
            if first_token_time is not None:
                step_generation_time = time.time() - first_token_time
                last_step_generation_time = step_generation_time

            # ---------- 构建工具调用字典 (用于 assistant_msg) ----------
            tool_calls = {}
            for idx, tc in tool_calls_by_index.items():
                tool_calls[tc["id"]] = tc

            if tool_calls and request and await request.is_disconnected():
                break

            if not tool_calls:
                break

            # ---------- 构建 valid_calls (用于执行工具，保留 idx) ----------
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

            assistant_msg = {
                "role": "assistant",
                "content": None,
                "tool_calls": list(tool_calls.values())
            }
            current_messages.append(assistant_msg)

            if message_id and chat_id:
                try:
                    await update_message(message_id, chat_id, None, None, list(tool_calls.values()))
                except Exception as e:
                    print(f"[DB] Failed to update assistant tool_calls: {e}")

            # ---------- 执行工具 ----------
            for idx, tc in valid_calls.items():
                if idx not in tool_preview_active:
                    print(f"[WARN] 跳过工具 {tc['function']['name']}，因为未找到预览状态")
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
                if message_id:
                    try:
                        await update_tool_call_arguments(local_call_id, args)
                    except Exception as e:
                        print(f"[DB] Failed to update arguments: {e}")

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

                # 统一格式化 tool 返回的内容
                if isinstance(result, dict):
                    tool_content = json.dumps(result, ensure_ascii=False)
                else:
                    tool_content = str(result)

                if chat_id and message_id:
                    await add_message(
                        chat_id=chat_id,
                        role='tool',
                        content=tool_content,
                        tool_calls=None,  # tool 消息不需要这个字段
                        tool_call_id=local_call_id,
                        file_ref=None
                    )

                # 更新结果和状态 (存入数据库)
                if message_id:
                    try:
                        result_str = str(result)[:50000]
                        await update_tool_call(
                            call_id=local_call_id,
                            result=result_str,
                            status="error" if failed else "success",
                            execution_time=exec_time_ms,
                            error_message=result if failed else None
                        )
                    except Exception as e:
                        print(f"[DB] Failed to update result: {e}")

                tool_info = {
                    "call_id": local_call_id,
                    "name": func_name,
                    "arguments": raw_args,
                    # 限制 result 长度，防止流式数据过大导致前端卡顿
                    "result": tool_content[:8000] 
                }
                yield f"<!--tool_data:{local_call_id}:{json.dumps(tool_info, ensure_ascii=False)}-->"
                
                # 更新连续失败计数
                if failed:
                    consecutive_failures += 1
                    yield f"<!--tool_status:{local_call_id}:error-->"
                else:
                    consecutive_failures = 0
                    yield f"<!--tool_status:{local_call_id}:success-->"

                yield f"<!--tool_preview:end:{local_call_id}-->"
                del tool_preview_active[idx]

                current_messages.append({
                    "role": "tool",
                    "tool_call_id": local_call_id,
                    "content": tool_content
                })

            yield "<!--tool_calls:end-->"

            if consecutive_failures >= MAX_CONSECUTIVE_FAILURES:
                force_final = True

        # ---------- 最终 token 统计输出 ----------
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
