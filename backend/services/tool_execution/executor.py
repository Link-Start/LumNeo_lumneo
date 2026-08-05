# backend/services/tool_execution/executor.py
import asyncio
import json
import time
from typing import Dict, Any, List, Tuple, Optional, Callable
from backend.schemas.llm import ToolExecutionContext, ToolResult
from backend.services.tools import execute_tool
from .approval import ApprovalHandler
from .persister import ToolPersister
from .suggestion import SuggestionGenerator


class ToolExecutor:
    def __init__(
        self,
        approval_handler: ApprovalHandler,
        persister: ToolPersister,
        suggestion_gen: SuggestionGenerator = None
    ):
        self.approval_handler = approval_handler
        self.persister = persister
        self.suggestion_gen = suggestion_gen or SuggestionGenerator()

    async def _execute_with_retry(
        self,
        func_name: str,
        args: Dict,
        context: ToolExecutionContext,
        on_retry_callback: Optional[Callable] = None
    ) -> Tuple[Any, bool, int, Optional[str]]:
        """
        执行单个工具，支持重试。
        返回：(result, failed, exec_time_ms, error_message)
        其中 failed 为 True 表示最终执行失败（含异常、超时、逻辑失败且重试耗尽）
        """
        for attempt in range(context.retry_count + 1):
            try:
                start = time.time()
                async with asyncio.timeout(context.tool_timeout):
                    result = await execute_tool(func_name, args, context.mcp_manager)
                    elapsed = int((time.time() - start) * 1000)

                # 检查逻辑失败
                if self._is_logical_failure(result) and attempt < context.retry_count:
                    reason = "逻辑执行失败"
                    if on_retry_callback:
                        on_retry_callback(attempt + 1, context.retry_count, reason)
                    await asyncio.sleep(context.retry_delay)
                    continue
                
                # 成功或逻辑失败但无重试次数
                if self._is_logical_failure(result):
                    # 最后一次尝试仍为逻辑失败，标记为失败
                    error_msg = self._extract_error_message(result)
                    return result, True, elapsed, error_msg
                else:
                    return result, False, elapsed, None

            except asyncio.TimeoutError:
                elapsed = int((time.time() - start) * 1000) if 'start' in locals() else 0
                if attempt < context.retry_count:
                    reason = f"超时({context.tool_timeout}s)"
                    if on_retry_callback:
                        on_retry_callback(attempt + 1, context.retry_count, reason)
                    await asyncio.sleep(context.retry_delay)
                    continue
                error_msg = f"工具执行超时（{context.tool_timeout}秒）"
                return error_msg, True, elapsed, error_msg

            except Exception as e:
                elapsed = int((time.time() - start) * 1000) if 'start' in locals() else 0
                if attempt < context.retry_count:
                    reason = str(e)[:50]
                    if on_retry_callback:
                        on_retry_callback(attempt + 1, context.retry_count, reason)
                    await asyncio.sleep(context.retry_delay)
                    continue
                error_msg = f"工具执行出错: {str(e)[:1000]}"
                return error_msg, True, elapsed, error_msg

        # 理论上不会到这里，但兜底
        return "未知错误", True, 0, "未知错误"

    @staticmethod
    def _is_logical_failure(result: Any) -> bool:
        """判定返回结果是否为逻辑失败（success 字段为 false）"""
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

    @staticmethod
    def _extract_error_message(result: Any) -> str:
        """从失败结果中提取错误信息"""
        if isinstance(result, dict):
            return result.get("message") or result.get("error") or "逻辑执行失败"
        if isinstance(result, str):
            try:
                parsed = json.loads(result)
                if isinstance(parsed, dict):
                    return parsed.get("message") or parsed.get("error") or "逻辑执行失败"
            except json.JSONDecodeError:
                pass
            return result[:200]  # 截断长字符串
        return "逻辑执行失败"

    async def process_single_tool(
        self,
        idx: str,
        tool_call: Dict,
        tool_preview_active: Dict,
        context: ToolExecutionContext,
        log_queue: Optional[asyncio.Queue] = None
    ) -> ToolResult:
        """处理单个工具调用（含审批检查）"""
        if idx not in tool_preview_active:
            return ToolResult(
                outputs=[f"⚠️ 跳过工具 {tool_call['function']['name']}，预览状态缺失"],
                failed=True, status="skipped"
            )

        local_call_id = tool_preview_active[idx]["call_id"]
        func_name = tool_call["function"]["name"] or "未知工具"

        if not tool_preview_active[idx].get("preview_sent"):
            tool_preview_active[idx]["preview_sent"] = True

        args = self._parse_tool_args(tool_call["function"]["arguments"])
        if isinstance(args.get("parse_error"), str):
            return ToolResult(
                outputs=[f"\n❌ 工具 `{func_name}` 参数错误：{args['parse_error']}\n"],
                failed=True, status="error"
            )

        # 更新数据库参数
        if context.chat_id:
            try:
                await self.persister.repo.update_arguments(local_call_id, args)
            except Exception:
                pass

        # 审批检查
        if context.approval_mode and not context.skip_approval:
            need_approval = self.approval_handler.need_approval(func_name, context.auto_decision)
            if need_approval:
                await self.persister.repo.update_status(local_call_id, "pending_confirmation")
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

        # 执行（带重试）
        def retry_cb(attempt, max_retries, reason):
            if log_queue:
                safe_reason = reason.replace(":", "_")
                tag = f"<!--tool_retry:{local_call_id}:{func_name}:{attempt}/{max_retries}:{safe_reason}-->"
                log_queue.put_nowait(tag)

        result, failed, exec_time_ms, error_msg = await self._execute_with_retry(
            func_name, args, context, on_retry_callback=retry_cb
        )

        # 若失败，error_msg 已由 _execute_with_retry 提供；否则取 result 中的信息（如有）
        if failed and not error_msg:
            error_msg = self._extract_error_message(result)

        result_str = json.dumps(result, ensure_ascii=False) if isinstance(result, dict) else str(result)
        # 持久化
        await self.persister.persist_tool_result(
            chat_id=context.chat_id,
            call_id=local_call_id,
            args=args,
            result_str=result_str,
            failed=failed,
            exec_time_ms=exec_time_ms,
            error_message=error_msg if failed else None
        )

        status_val = "error" if failed else "success"
        outputs = [
            f"<!--tool_status:{local_call_id}:{status_val}-->",
            f"<!--tool_preview:end:{local_call_id}-->"
        ]
        new_segments = [{
            "type": "tool_call",
            "content": {
                "id": local_call_id,
                "name": func_name,
                "status": status_val,
                "error_message": error_msg if failed else None
            }
        }]

        if idx in tool_preview_active:
            del tool_preview_active[idx]

        if log_queue:
            for out in outputs:
                await log_queue.put(out)

        return ToolResult(
            outputs=outputs,
            new_segments=new_segments,
            call_id=local_call_id,
            failed=failed,
            status=status_val,
            error_message=error_msg if failed else None,
            result_str=result_str,
            exec_time_ms=exec_time_ms,
            tool_message_content=result_str
        )

    @staticmethod
    def _parse_tool_args(raw_args: str) -> Dict:
        try:
            return json.loads(raw_args) if raw_args else {}
        except json.JSONDecodeError as e:
            return {"raw": raw_args, "parse_error": str(e)}

    async def process_multiple(
        self,
        valid_calls: Dict[str, Dict],
        tool_preview_active: Dict,
        context: ToolExecutionContext,
        enable_parallel: bool,
        max_parallel: int,
        log_queue: Optional[asyncio.Queue] = None
    ) -> List[tuple]:
        """并发执行多个工具"""
        sem = asyncio.Semaphore(max_parallel if enable_parallel else 1)

        async def run_one(idx, tc):
            async with sem:
                return idx, tc, await self.process_single_tool(
                    idx, tc, tool_preview_active, context, log_queue
                )

        return await asyncio.gather(*[run_one(idx, tc) for idx, tc in valid_calls.items()])