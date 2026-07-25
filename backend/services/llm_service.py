# backend/services/llm_service.py
import os
import uuid
import json
import time
import asyncio
from dataclasses import dataclass, field
from typing import List, Dict, Any, AsyncGenerator, Optional
from fastapi import Request
from openai import AsyncOpenAI, APIError
from backend.services.tools import get_all_tools, execute_tool, is_dangerous_tool
from backend.db.decisions import create_decision, get_decision_status
from backend.db.tool_calls import (
    create_tool_call, update_tool_call, update_tool_call_arguments,
    update_tool_call_status, get_tool_call_status
)
from backend.db.messages import add_message
from config_loader import config
from backend.bootstrap import logger


# ---------- 数据类 ----------
@dataclass
class ToolExecutionContext:
    chat_id: Optional[str]
    mcp_manager: Any
    approval_mode: bool
    auto_decision: bool
    tool_timeout: int
    retry_count: int
    retry_delay: int
    request: Optional[Request]
    skip_approval: bool = False
    is_retry: bool = False


@dataclass
class ToolResult:
    outputs: List[str] = field(default_factory=list)
    new_segments: List[Dict] = field(default_factory=list)
    call_id: Optional[str] = None
    failed: bool = False
    status: str = "unknown"
    error_message: Optional[str] = None
    result_str: str = ""
    exec_time_ms: int = 0
    meta_data: Dict = field(default_factory=dict)
    tool_message_content: Optional[str] = None
    approval_info: Optional[Dict] = None


# ---------- 主服务类 ----------
class LLMService:
    instance: Optional["LLMService"] = None

    def __init__(self, model_type: str, model_name: str, api_key: str = "",
                 base_url: str = None, thinking: str = 'enabled', reasoning_effort: str = 'high'):
        self.model_type = model_type
        self.model_name = model_name
        self.thinking = thinking
        self.reasoning_effort = reasoning_effort if thinking == 'enabled' else None
        self.client = AsyncOpenAI(api_key=api_key or 'none', base_url=base_url)

    # ==================== 工具调用辅助方法 ====================
    @staticmethod
    def _parse_tool_args(raw_args: str) -> Dict:
        try:
            return json.loads(raw_args) if raw_args else {}
        except json.JSONDecodeError as e:
            return {"raw": raw_args, "parse_error": str(e)}

    @staticmethod
    def _is_logical_failure(result: Any) -> bool:
        if isinstance(result, dict) and result.get("success") is False:
            return True
        if isinstance(result, str):
            try:
                parsed = json.loads(result)
                if isinstance(parsed, dict) and parsed.get("success") is False:
                    return True
            except json.JSONDecodeError:
                pass
        return False

    async def _execute_with_retry(
        self, func_name: str, args: Dict, context: ToolExecutionContext,
        on_retry_callback=None
    ) -> tuple:
        """执行工具调用，支持重试和实时回调"""
        for attempt in range(context.retry_count + 1):
            try:
                start = time.time()
                async with asyncio.timeout(context.tool_timeout):
                    result = await execute_tool(func_name, args, context.mcp_manager)
                    elapsed = int((time.time() - start) * 1000)
                
                # 检查逻辑失败并重试
                if self._is_logical_failure(result) and attempt < context.retry_count:
                    reason = "逻辑执行失败"
                    if on_retry_callback:
                        on_retry_callback(attempt + 1, context.retry_count, reason)
                    await asyncio.sleep(context.retry_delay)
                    continue
                
                return result, False, elapsed
                
            except asyncio.TimeoutError:
                if attempt < context.retry_count:
                    reason = f"执行超时({context.tool_timeout}s)"
                    if on_retry_callback:
                        on_retry_callback(attempt + 1, context.retry_count, reason)
                    await asyncio.sleep(context.retry_delay)
                    continue
                return f"工具执行超时（{context.tool_timeout}秒）", True, 0
                
            except Exception as e:
                if attempt < context.retry_count:
                    reason = str(e)[:50]
                    if on_retry_callback:
                        on_retry_callback(attempt + 1, context.retry_count, reason)
                    await asyncio.sleep(context.retry_delay)
                    continue
                return f"工具执行出错: {str(e)[:1000]}", True, 0
                
        return "未知错误", True, 0

    @staticmethod
    def _prepare_db_result(result_str: str, chat_id: Optional[str], call_id: str) -> tuple:
        MAX_DB_LEN = 20000
        if len(result_str) > MAX_DB_LEN:
            file_dir = f"{chat_id}/{call_id}.txt" if chat_id else f"unknown/{call_id}.txt"
            file_path = os.path.join(config.cache_dir, file_dir)
            os.makedirs(os.path.dirname(file_path), exist_ok=True)
            with open(file_path, "w", encoding="utf-8") as f:
                f.write(result_str)
            meta = {
                "storage_type": "file",
                "file_path": file_dir,
                "size": len(result_str),
                "preview": result_str[:1000]
            }
            return f"[数据量过大(共{len(result_str)}字)，完整内容已保存至本地文件]", meta
        return result_str, {}

    async def _update_db_tool_result(
        self, chat_id: Optional[str], call_id: str, args: Dict,
        result_str: str, failed: bool, exec_time_ms: int,
        error_message: Optional[str], meta_data: Dict
    ):
        if not chat_id:
            return
        status = "error" if failed else "success"
        try:
            db_result, _ = self._prepare_db_result(result_str, chat_id, call_id)
            await update_tool_call(
                call_id=call_id,
                arguments=args,
                result=db_result,
                status=status,
                execution_time=exec_time_ms,
                error_message=error_message if failed else None,
                meta_data=meta_data
            )
        except Exception as e:
            logger.error(f"[数据库] 更新工具调用结果失败：{e}")

    async def _handle_approval_flow(
        self, idx: str, tc: dict, tool_preview_active: dict, context: ToolExecutionContext
    ) -> Optional[ToolResult]:
        local_call_id = tool_preview_active[idx]['call_id']
        func_name = tc["function"]["name"]
        args = self._parse_tool_args(tc["function"]["arguments"])

        if context.approval_mode and not context.skip_approval:
            need_approval = is_dangerous_tool(func_name) if context.auto_decision else True
            if need_approval:
                await update_tool_call_status(local_call_id, "pending_confirmation")
                args_preview = json.dumps(args, ensure_ascii=False)[:2000]
                return ToolResult(
                    outputs=[f"<!--tool_confirm_required:{local_call_id}:{func_name}:{args_preview}-->"],
                    call_id=local_call_id,
                    status="need_approval",
                    approval_info={
                        "local_call_id": local_call_id,
                        "func_name": func_name,
                        "args_preview": args_preview,
                        "args": args
                    }
                )
        return None

    async def _process_single_tool(
        self, idx: str, tc: dict, tool_preview_active: dict,
        segments: list, context: ToolExecutionContext,
        log_queue: asyncio.Queue = None
    ) -> ToolResult:
        outputs = []
        new_segments = []

        if idx not in tool_preview_active:
            return ToolResult(
                outputs=[f"⚠️ 跳过工具 {tc['function']['name']}，预览状态缺失"],
                failed=True, status="skipped"
            )

        local_call_id = tool_preview_active[idx]['call_id']
        func_name = tc["function"]["name"] or "未知工具"

        if not tool_preview_active[idx].get('preview_sent'):
            outputs.append(f"<!--tool_preview:start:{local_call_id}:{func_name}-->")
            tool_preview_active[idx]['preview_sent'] = True

        args = self._parse_tool_args(tc["function"]["arguments"])
        if isinstance(args.get("parse_error"), str):
            outputs.append(f"\n❌ 工具 `{func_name}` 参数错误：{args['parse_error']}\n")

        if context.chat_id:
            try:
                await update_tool_call_arguments(local_call_id, args)
            except Exception as e:
                logger.error(f"[数据库] 更新参数失败：{e}")

        # 审批
        approval = await self._handle_approval_flow(idx, tc, tool_preview_active, context)
        if approval:
            return approval

        # 定义实时重试回调
        def send_retry_log(attempt: int, max_retries: int, reason: str):
            if log_queue:
                safe_reason = reason.replace(':', '_')
                tag = f"<!--tool_retry:{local_call_id}:{func_name}:{attempt}/{max_retries}:{safe_reason}-->"
                log_queue.put_nowait(tag)

        # 执行 (传入回调)
        result, failed, exec_time_ms = await self._execute_with_retry(
            func_name, args, context, 
            on_retry_callback=send_retry_log
        )

        result_str = json.dumps(result, ensure_ascii=False) if isinstance(result, dict) else str(result)
        db_result, meta_data = self._prepare_db_result(result_str, context.chat_id, local_call_id)

        await self._update_db_tool_result(
            context.chat_id, local_call_id, args, result_str, failed, exec_time_ms,
            result_str if failed else None, meta_data
        )

        status_val = "error" if failed else "success"
        outputs.append(f"<!--tool_status:{local_call_id}:{status_val}-->")
        outputs.append(f"<!--tool_preview:end:{local_call_id}-->")

        new_segments.append({
            'type': 'tool_call',
            'content': {
                'id': local_call_id, 'name': func_name, 'status': status_val,
                'error_message': result_str if failed else None
            }
        })

        if idx in tool_preview_active:
            del tool_preview_active[idx]

        return ToolResult(
            outputs=outputs,
            new_segments=new_segments,
            call_id=local_call_id,
            failed=failed,
            status=status_val,
            error_message=result_str if failed else None,
            result_str=result_str,
            exec_time_ms=exec_time_ms,
            meta_data=meta_data,
            tool_message_content=result_str
        )

    # ==================== 流式响应处理 ====================
    async def _stream_llm_chunk(
        self, response, state: dict, segments: list,
        tool_preview_active: dict, chat_id: Optional[str]
    ) ->  AsyncGenerator[str, None]:
        final_content = ""
        tool_calls_by_index = {}
        first_token_time = None

        async for chunk in response:
            if state['request'] and await state['request'].is_disconnected():
                break

            if hasattr(chunk, 'usage') and chunk.usage:
                # 累积 token 统计到 state
                su = chunk.usage.model_dump() if hasattr(chunk.usage, 'model_dump') else dict(chunk.usage)
                state['total_usage']['prompt_tokens'] += su.get('prompt_tokens', 0) or 0
                state['total_usage']['completion_tokens'] += su.get('completion_tokens', 0) or 0
                state['total_usage']['total_tokens'] += su.get('total_tokens', 0) or 0
                details = su.get('completion_tokens_details') or {}
                for k, v in details.items():
                    state['total_usage']['completion_tokens_details'][k] = \
                        state['total_usage']['completion_tokens_details'].get(k, 0) + (v or 0)
                state['last_usage'] = {
                    'prompt_tokens': su.get('prompt_tokens', 0) or 0,
                    'completion_tokens': su.get('completion_tokens', 0) or 0,
                    'total_tokens': su.get('total_tokens', 0) or 0,
                    'completion_tokens_details': details
                }

            if not chunk.choices:
                continue

            delta = chunk.choices[0].delta
            reasoning = getattr(delta, 'reasoning_content', None)
            tool_calls_data = getattr(delta, 'tool_calls', None)
            delta_content = getattr(delta, 'content', None)

            if first_token_time is None and (reasoning or delta_content or tool_calls_data):
                first_token_time = time.time()

            # 推理处理
            if reasoning:
                if not state.get('in_reasoning'):
                    state['in_reasoning'] = True
                    state['reasoning_start_time'] = time.time()
                    yield "<!--reasoning:start-->"
                state['reasoning_buffer'] += reasoning
                yield reasoning
                continue

            if state.get('in_reasoning') and (delta_content or tool_calls_data):
                duration = time.time() - state['reasoning_start_time']
                segments.append({
                    "type": "reasoning",
                    "content": state['reasoning_buffer'],
                    "duration": f"{duration:.2f}"
                })
                yield f"<!--reasoning:end:{duration:.2f}-->"
                state['in_reasoning'] = False
                state['reasoning_buffer'] = ""

            # 工具调用
            if tool_calls_data:
                if not state.get('tool_calls_started'):
                    state['tool_calls_started'] = True
                    yield "\n<!--tool_calls:start-->"

                for tc_delta in tool_calls_data:
                    idx = tc_delta.index if tc_delta.index is not None else (tc_delta.id or str(uuid.uuid4()))
                    if idx not in tool_preview_active and tc_delta.function and tc_delta.function.name:
                        call_id = tc_delta.id or str(uuid.uuid4())
                        func_name = tc_delta.function.name
                        tool_preview_active[idx] = {
                            'call_id': call_id, 'name': func_name,
                            'db_created': False, 'preview_sent': True
                        }
                        yield f"<!--tool_preview:start:{call_id}:{func_name}-->"
                        if chat_id:
                            try:
                                await create_tool_call(chat_id=chat_id, call_id=call_id, tool_name=func_name)
                                tool_preview_active[idx]['db_created'] = True
                            except Exception as e:
                                logger.error(f"[数据库] 创建工具调用记录失败：{e}")
                        segments.append({
                            "type": "tool_call",
                            "content": {"id": call_id, "name": func_name}
                        })
                    # 累积参数
                    if idx not in tool_calls_by_index:
                        tool_calls_by_index[idx] = {
                            "id": tc_delta.id,
                            "type": "function",
                            "function": {"name": "", "arguments": ""}
                        }
                    target = tool_calls_by_index[idx]
                    if tc_delta.id:
                        target["id"] = tc_delta.id
                    if tc_delta.function:
                        if tc_delta.function.name and not target["function"]["name"]:
                            target["function"]["name"] = tc_delta.function.name
                        target["function"]["arguments"] += tc_delta.function.arguments or ""
            elif delta_content:
                final_content += delta_content
                yield delta_content

        # 流结束后闭合推理
        if state.get('in_reasoning'):
            duration = time.time() - state['reasoning_start_time']
            segments.append({
                "type": "reasoning",
                "content": state['reasoning_buffer'],
                "duration": f"{duration:.2f}"
            })
            yield f"<!--reasoning:end:{duration:.2f}-->"
            state['in_reasoning'] = False
            state['reasoning_buffer'] = ""

        if final_content.strip():
            segments.append({"type": "text", "content": final_content})

        state['first_token_time'] = first_token_time
        state['final_content'] = final_content
        state['tool_calls_by_index'] = tool_calls_by_index

    @staticmethod
    def _merge_segment(segments: list, new_seg: dict):
        if new_seg.get('type') == 'tool_call' and 'id' in new_seg.get('content', {}):
            seg_id = new_seg['content']['id']
            for i, seg in enumerate(segments):
                if seg.get('type') == 'tool_call' and seg.get('content', {}).get('id') == seg_id:
                    segments[i] = new_seg
                    return
        segments.append(new_seg)

    async def _execute_tool_calls(
        self, valid_calls: dict, tool_preview_active: dict, segments: list,
        context: ToolExecutionContext, enable_parallel: bool, max_parallel: int,
        log_queue: asyncio.Queue = None
    ) -> list:
        sem = asyncio.Semaphore(max_parallel if enable_parallel else 1)
        async def run_one(idx, tc):
            async with sem:
                # 当AI尝试新工具时，发送中间反馈
                if log_queue and context.is_retry:
                    log_queue.put_nowait(f"<!--tool_retry:start:{tc['function']['name']}-->")
                res = await self._process_single_tool(
                    idx, tc, tool_preview_active, segments, context, log_queue
                )
                if log_queue and not res.failed and context.is_retry:
                    log_queue.put_nowait(f"<!--tool_retry:end:{tc['function']['name']}-->")
                return idx, tc, res
        return await asyncio.gather(*[run_one(idx, tc) for idx, tc in valid_calls.items()])

    # ==================== 主响应生成 ====================
    async def generate_response(
        self,
        messages: List[Dict[str, str]],
        enable_tools: bool = False,
        tools: Optional[List[Dict]] = None,
        request: Optional[Request] = None,
        mcp_manager=None,
        params: Dict = None,
        profile_id: int = None,
        model_id: str = None,
        chat_id: Optional[str] = None,
        turn_index: Optional[int] = None,
    ) -> AsyncGenerator[str, None]:
        params = params or {}
    
        # 图像生成分支
        if "image" in self.model_name.lower():
            async for out in self._generate_image_response(messages, params):
                yield out
            return

        current_messages = messages.copy()
        if tools is None and enable_tools:
            tools = await get_all_tools(mcp_manager)

        # 提取参数
        max_steps = params.get('max_iterations', 10)
        max_consecutive_failures = params.get('failure_threshold', 3)
        tool_timeout = params.get('tool_timeout', 30)
        retry_count = params.get('retry_count', 2)
        retry_delay = params.get('retry_delay', 1)
        failure_behavior = params.get('failure_behavior', 'continue')
        max_parallel = params.get('max_parallel', 5)
        approval_mode = params.get('approval_mode', True)
        auto_decision = params.get('auto_decision', False)
        enable_parallel = not approval_mode and max_parallel > 1

        context = ToolExecutionContext(
            chat_id=chat_id, mcp_manager=mcp_manager,
            approval_mode=approval_mode, auto_decision=auto_decision,
            tool_timeout=tool_timeout, retry_count=retry_count, retry_delay=retry_delay,
            request=request, is_retry=False
        )

        segments = []
        state = {
            'request': request,
            'total_usage': {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0, "completion_tokens_details": {}},
            'last_usage': None,
            'in_reasoning': False,
            'reasoning_buffer': '',
            'reasoning_start_time': 0.0,
            'tool_calls_started': False,
        }
        consecutive_failures = 0
        force_final = False

        start_time = time.time()
        last_failed_tool = None
        last_failed_reason = ""
        last_failed_attempts = 0
        last_failed_elapsed = 0.0

        step = 0
        while step < max_steps:
            if request and await request.is_disconnected():
                break

            tool_preview_active = {}
            # 强制总结
            if force_final or step == max_steps - 1:
                msg = ("工具调用遇到了一些阻碍，暂时无法继续执行。请基于目前已获取的信息，为用户提供最有帮助的回答。"
                       if force_final else "已达到最大交互轮次，无法继续探索。请综合已经收集到的上下文，为用户提供全面、准确的最终回应。")
                current_messages.append({"role": "user", "content": f"【系统提示】{msg}"})
                tools = None
                force_final = False

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
                "extra_body": {
                    "top_k": params.get('top_k', 20),
                    "chat_template_kwargs": {},
                    "thinking": {"type": self.thinking},
                }
            }
            if self.thinking == "enabled":
                kwargs["extra_body"].update({
                    "enable_thinking": True,
                    "preserve_thinking": True,
                    "chat_template_kwargs": {"enable_thinking": True, "preserve_thinking": True}
                })
            elif self.thinking == "disabled":
                kwargs["extra_body"].update({
                    "enable_thinking": False,
                    "preserve_thinking": False,
                    "chat_template_kwargs": {"enable_thinking": False, "preserve_thinking": False}
                })
            if tools and not (force_final or step == max_steps - 1):
                kwargs["tools"] = tools
                kwargs["tool_choice"] = "auto"

            try:
                response = await self.client.chat.completions.create(**kwargs)
            except APIError as e:
                yield f"\n❌ 模型服务错误：{e.message}"
                segments.append({"type": "error", "content": f"❌ {e.message}"})
                break

            # 流式处理
            state['final_content'] = ''
            state['tool_calls_by_index'] = {}
            async for chunk_text in self._stream_llm_chunk(response, state, segments, tool_preview_active, chat_id):
                yield chunk_text   # 将流式内容原样输出

            tool_calls_by_index = state['tool_calls_by_index']

            if state.get('in_reasoning'):  # 安全闭合
                duration = time.time() - state['reasoning_start_time']
                yield f"<!--reasoning:end:{duration:.2f}-->"
                segments.append({
                    "type": "reasoning",
                    "content": state['reasoning_buffer'],
                    "duration": f"{duration:.2f}"
                })
                state['in_reasoning'] = False
                state['reasoning_buffer'] = ""

            # 有效工具调用
            valid_calls = {idx: tc for idx, tc in tool_calls_by_index.items() if tc["function"]["name"].strip()}
            if not valid_calls:
                break

            # 添加 assistant 消息
            assistant_msg = {
                "role": "assistant",
                "content": None,
                "tool_calls": list({tc["id"]: tc for tc in tool_calls_by_index.values() if tc.get("id")}.values())
            }
            if state.get('reasoning_buffer'):  # 保存当前步骤推理
                assistant_msg["reasoning_content"] = state['reasoning_buffer']
            current_messages.append(assistant_msg)

            # =================== 执行工具（实时重试日志修改部分） ===================
            log_queue = asyncio.Queue()
            
            # 启动任务
            exec_task = asyncio.create_task(
                self._execute_tool_calls(
                    valid_calls, tool_preview_active, segments, context,
                    enable_parallel, max_parallel, log_queue
                )
            )
            
            # 实时消费日志并 yield
            while True:
                try:
                    # 非阻塞获取日志
                    log_msg = log_queue.get_nowait()
                    yield log_msg
                except asyncio.QueueEmpty:
                    # 队列为空，检查任务是否结束
                    if exec_task.done():
                        break
                    # 短暂休眠避免 CPU 空转
                    await asyncio.sleep(0.05)
            
            # 获取执行结果
            results = exec_task.result()
            # ===================================================================

            # 处理每个工具结果
            for idx, tc, res in results:
                # 审批等待
                if res.status == 'need_approval':
                    for out in res.outputs:
                        yield out
                    decision_id = res.approval_info['local_call_id']
                    # 轮询审批结果
                    confirmed = None
                    for _ in range(50):
                        if request and await request.is_disconnected():
                            break
                        status = await get_tool_call_status(decision_id)
                        if status == "confirmed":
                            confirmed = True
                            break
                        if status == "cancelled":
                            confirmed = False
                            break
                        await asyncio.sleep(1)
                    
                    if confirmed:
                        context.skip_approval = True
                        
                        # === 审批通过后，手动执行工具并监听重试日志 ===
                        approval_queue = asyncio.Queue()
                        approval_task = asyncio.create_task(
                            self._process_single_tool(idx, tc, tool_preview_active, segments, context, approval_queue)
                        )
                        
                        while True:
                            try:
                                log_msg = approval_queue.get_nowait()
                                yield log_msg
                            except asyncio.QueueEmpty:
                                if approval_task.done():
                                    break
                                await asyncio.sleep(0.05)
                                
                        res = approval_task.result()
                        # ========================================================
                        
                        context.skip_approval = False
                    else:
                        yield f"<!--tool_status:{decision_id}:rejected-->"
                        yield f"<!--tool_preview:end:{decision_id}-->"
                        self._merge_segment(segments, {
                            'type': 'tool_call',
                            'content': {
                                'id': decision_id, 'name': res.approval_info['func_name'],
                                'status': 'rejected', 'error_message': '用户拒绝'
                            }
                        })
                        await update_tool_call(
                            call_id=decision_id,
                            arguments=res.approval_info['args'],
                            result="用户拒绝了此工具调用",
                            status="rejected",
                            execution_time=0,
                            error_message="用户拒绝",
                            meta_data={}
                        )
                        current_messages.append({
                            "role": "tool",
                            "tool_call_id": decision_id,
                            "content": "用户拒绝了此工具调用，请直接回答工具被拒绝，无法执行。"
                        })
                        continue

                # 输出通用结果
                for out in res.outputs:
                    yield out
                for seg in res.new_segments:
                    self._merge_segment(segments, seg)

                if res.failed:
                    consecutive_failures += 1
                    # 记录失败信息用于决策弹窗
                    last_failed_tool = tc["function"]["name"] or "未知工具"
                    last_failed_reason = res.error_message or "执行失败"
                    last_failed_attempts = context.retry_count + 1  # 总尝试次数
                    last_failed_elapsed = res.exec_time_ms / 1000.0  # 转换为秒
                else:
                    consecutive_failures = 0

                if res.call_id and res.tool_message_content:
                    current_messages.append({
                        "role": "tool",
                        "tool_call_id": res.call_id,
                        "content": res.tool_message_content
                    })

            yield "<!--tool_calls:end-->"

            # 连续失败处理
            if consecutive_failures >= max_consecutive_failures:
                if failure_behavior == 'stop':
                    yield f"\n❌ 工具调用失败 {consecutive_failures} 次，已停止\n"
                    break
                elif failure_behavior == 'ask':
                    # 构建丰富的决策信息
                    decision_info = {
                        "reason": last_failed_reason or f"连续失败 {consecutive_failures} 次",
                        "tool_name": last_failed_tool or "未知工具",
                        "attempts": last_failed_attempts or consecutive_failures,
                        "elapsed": round(last_failed_elapsed, 1) or round(time.time() - start_time, 1),
                        "suggestion": "检查网络或考虑延长工具超时时间",
                        "threshold": max_consecutive_failures,
                        "total_attempts": consecutive_failures
                    }
                    info_json = json.dumps(decision_info, ensure_ascii=False)
                    decision_id = await create_decision(
                        chat_id=chat_id,
                        turn_index=turn_index,
                        message=info_json,   # 存储 JSON 字符串
                        timeout_seconds=50
                    )
                    yield f"<!--ask_decision:{decision_id}:{info_json}-->"
                    
                    # 轮询用户决策
                    status = None
                    for _ in range(50):
                        if request and await request.is_disconnected():
                            break
                        status = await get_decision_status(decision_id)
                        if status in ("continue", "stop"):
                            break
                        await asyncio.sleep(1)
                    if status != "continue":
                        break
                    consecutive_failures = 0
                    max_steps += 3
                    context.is_retry = True
                    force_final = False
                else:
                    force_final = True
                
            # 循环计数器自增
            step += 1

        # 最终统计
        if state['last_usage'] and state['last_usage']['completion_tokens'] > 0:
            gen_time = time.time() - state.get('first_token_time', 0)
            tokens = state['last_usage']['completion_tokens']
            speed = f"{tokens / gen_time:.2f} token/s" if gen_time > 0 else "⚡瞬间完成"
            token_info = {
                "final_answer_usage": state['last_usage'],
                "total_usage_all_steps": state['total_usage'],
                "speed": speed
            }
            yield f"\n<!--token_usage:{json.dumps(token_info)}-->"
            segments.append({"type": "token_usage", "content": token_info})

        # 落库
        if chat_id and turn_index is not None:
            segments_json = json.dumps(segments, ensure_ascii=False)
            await add_message(
                chat_id=chat_id, role="assistant", content=segments_json,
                profile_id=profile_id, model_id=model_id, file_ref=None, turn_index=turn_index
            )
            yield f"<!--segments_complete:{segments_json}-->"

    # ==================== 图像生成分支 ====================
    async def _generate_image_response(self, messages, params) -> AsyncGenerator[str, None]:
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
                model=self.model_name, prompt=prompt, size=size, quality=quality, n=n
            )
            if not response.data:
                yield "❌ 图像生成服务未返回有效结果。"
                return
            img = response.data[0]
            if hasattr(img, 'url') and img.url:
                yield f"![生成的图片]({img.url})"
            else:
                yield "❌ 图像生成服务未返回可用的图片链接。"
        except APIError as e:
            yield f"❌ 图像生成 API 错误：{e.message}"
        except Exception as e:
            yield f"❌ 图像生成失败：{str(e)}"
