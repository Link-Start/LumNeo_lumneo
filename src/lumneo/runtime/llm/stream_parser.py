# src/lumneo/runtime/llm/stream_parser.py
# 流式响应解析器（原 backend/services/llm/stream_parser.py）。
#
# 负责解析 OpenAI 兼容的流式 chunk，提取思考过程、正文与工具调用，并通过注入的
# ToolCallRepository Port 创建工具调用预览记录。解析器本身不持有数据库/文件 I/O。
import time
import uuid
from dataclasses import dataclass, field
from typing import AsyncGenerator, Dict, List, Optional, Any

from lumneo.conversation.ports.tool_call_repository import ToolCallRepository


@dataclass
class StreamState:
    """流式解析过程中的状态"""
    in_reasoning: bool = False
    reasoning_buffer: str = ""
    reasoning_start_time: float = 0.0
    tool_calls_started: bool = False
    tool_calls_by_index: Dict[str, Dict] = field(default_factory=dict)
    final_content: str = ""
    first_token_time: Optional[float] = None
    total_usage: Dict[str, Any] = field(default_factory=lambda: {
        "prompt_tokens": 0,
        "completion_tokens": 0,
        "total_tokens": 0,
        "completion_tokens_details": {}
    })
    last_usage: Optional[Dict[str, Any]] = None
    request: Optional[Any] = None


class StreamParser:
    """负责解析流式 chunk，提取内容、推理和工具调用"""

    @staticmethod
    async def parse(
        response,
        state: StreamState,
        segments: List[Dict],
        tool_preview_active: Dict[str, Dict],
        chat_id: Optional[str],
        tool_call_repo: ToolCallRepository,  # 注入 repository port
    ) -> AsyncGenerator[str, None]:
        """解析流式响应，yield 文本和标记，同时填充 state"""
        state.tool_calls_by_index = {}
        state.tool_calls_started = False
        state.final_content = ""

        async for chunk in response:
            if state.request and await state.request.is_disconnected():
                break

            if hasattr(chunk, "usage") and chunk.usage:
                su = chunk.usage.model_dump() if hasattr(chunk.usage, "model_dump") else dict(chunk.usage)
                state.total_usage["prompt_tokens"] += su.get("prompt_tokens", 0) or 0
                state.total_usage["completion_tokens"] += su.get("completion_tokens", 0) or 0
                state.total_usage["total_tokens"] += su.get("total_tokens", 0) or 0
                details = su.get("completion_tokens_details") or {}
                for k, v in details.items():
                    state.total_usage["completion_tokens_details"][k] = \
                        state.total_usage["completion_tokens_details"].get(k, 0) + (v or 0)
                state.last_usage = {
                    "prompt_tokens": su.get("prompt_tokens", 0) or 0,
                    "completion_tokens": su.get("completion_tokens", 0) or 0,
                    "total_tokens": su.get("total_tokens", 0) or 0,
                    "completion_tokens_details": details
                }

            if not chunk.choices:
                continue

            delta = chunk.choices[0].delta
            reasoning = getattr(delta, "reasoning_content", None)
            tool_calls_data = getattr(delta, "tool_calls", None)
            delta_content = getattr(delta, "content", None)

            if state.first_token_time is None and (reasoning or delta_content or tool_calls_data):
                state.first_token_time = time.time()

            # 推理内容
            if reasoning:
                if not state.in_reasoning:
                    state.in_reasoning = True
                    state.reasoning_start_time = time.time()
                    yield "<!--reasoning:start-->"
                state.reasoning_buffer += reasoning
                yield reasoning
                continue

            # 推理结束，切换到内容或工具
            if state.in_reasoning and (delta_content or tool_calls_data):
                duration = time.time() - state.reasoning_start_time
                segments.append({
                    "type": "reasoning",
                    "content": state.reasoning_buffer,
                    "duration": f"{duration:.2f}"
                })
                yield f"<!--reasoning:end:{duration:.2f}-->"
                state.in_reasoning = False
                state.reasoning_buffer = ""

            # 工具调用
            if tool_calls_data:
                if not state.tool_calls_started:
                    state.tool_calls_started = True
                    yield "\n<!--tool_calls:start-->"

                for tc_delta in tool_calls_data:
                    idx = tc_delta.index if tc_delta.index is not None else (tc_delta.id or str(uuid.uuid4()))
                    # 初始化预览
                    if idx not in tool_preview_active and tc_delta.function and tc_delta.function.name:
                        call_id = tc_delta.id or str(uuid.uuid4())
                        func_name = tc_delta.function.name
                        tool_preview_active[idx] = {
                            "call_id": call_id,
                            "name": func_name,
                            "db_created": False,
                            "preview_sent": True
                        }
                        yield f"<!--tool_preview:start:{call_id}:{func_name}-->"
                        if chat_id:
                            try:
                                await tool_call_repo.create(chat_id, call_id, func_name)
                                tool_preview_active[idx]["db_created"] = True
                            except Exception:
                                # 记录失败不应中断流式解析
                                pass
                        segments.append({
                            "type": "tool_call",
                            "content": {"id": call_id, "name": func_name}
                        })
                    # 累积参数
                    if idx not in state.tool_calls_by_index:
                        state.tool_calls_by_index[idx] = {
                            "id": tc_delta.id,
                            "type": "function",
                            "function": {"name": "", "arguments": ""}
                        }
                    target = state.tool_calls_by_index[idx]
                    if tc_delta.id:
                        target["id"] = tc_delta.id
                    if tc_delta.function:
                        if tc_delta.function.name and not target["function"]["name"]:
                            target["function"]["name"] = tc_delta.function.name
                        target["function"]["arguments"] += tc_delta.function.arguments or ""

            elif delta_content:
                state.final_content += delta_content
                yield delta_content

        # 流结束时处理未闭合的推理
        if state.in_reasoning:
            duration = time.time() - state.reasoning_start_time
            segments.append({
                "type": "reasoning",
                "content": state.reasoning_buffer,
                "duration": f"{duration:.2f}"
            })
            yield f"<!--reasoning:end:{duration:.2f}-->"
            state.in_reasoning = False
            state.reasoning_buffer = ""

        if state.final_content.strip():
            segments.append({"type": "text", "content": state.final_content})
