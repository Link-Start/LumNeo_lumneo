# backend/services/orchestrator.py
import asyncio
import json
import time
import re
import uuid
from typing import List, Dict, AsyncGenerator, Optional
from fastapi import Request

from backend.services.tools import get_all_tools
from backend.schemas.llm import ToolExecutionContext, StreamState
from backend.services.llm.client import LLMClient
from backend.services.llm.stream_parser import StreamParser
from backend.services.tool_execution.executor import ToolExecutor
from backend.services.tool_execution.approval import ApprovalHandler
from backend.services.tool_execution.persister import ToolPersister
from backend.services.tool_execution.suggestion import SuggestionGenerator
from backend.repositories import DecisionRepository, MessageRepository
from backend.repositories.plan_repo import PlanRepository


class LLMOrchestrator:
    def __init__(
        self,
        llm_client: LLMClient,
        tool_executor: ToolExecutor,
        stream_parser: StreamParser,
        approval_handler: ApprovalHandler,
        persister: ToolPersister,
        decision_repo: DecisionRepository,
        message_repo: MessageRepository,
        suggestion_gen: SuggestionGenerator,
    ):
        self.llm_client = llm_client
        self.tool_executor = tool_executor
        self.stream_parser = stream_parser
        self.approval_handler = approval_handler
        self.persister = persister
        self.decision_repo = decision_repo
        self.message_repo = message_repo
        self.suggestion_gen = suggestion_gen

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
        blueprint_mode: bool = False,
    ) -> AsyncGenerator[str, None]:
        params = params or {}
        plan_id_saved = None
        current_messages = messages.copy()
        if tools is None and enable_tools:
            tools = await get_all_tools(mcp_manager)

        # 提取参数
        max_steps = params.get("max_iterations", 10)
        max_consecutive_failures = params.get("failure_threshold", 3)
        tool_timeout = params.get("tool_timeout", 30)
        retry_count = params.get("retry_count", 2)
        retry_delay = params.get("retry_delay", 1)
        failure_behavior = params.get("failure_behavior", "continue")
        max_parallel = params.get("max_parallel", 5)
        approval_mode = params.get("approval_mode", True)
        auto_decision = params.get("auto_decision", False)
        enable_parallel = not approval_mode and max_parallel > 1

        context = ToolExecutionContext(
            chat_id=chat_id,
            mcp_manager=mcp_manager,
            approval_mode=approval_mode,
            auto_decision=auto_decision,
            tool_timeout=tool_timeout,
            retry_count=retry_count,
            retry_delay=retry_delay,
            request=request,
            is_retry=False
        )

        segments = []
        state = StreamState(request=request)
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

            if force_final or step == max_steps - 1:
                msg = ("工具调用遇到了一些阻碍，暂时无法继续执行。请基于目前已获取的信息，为用户提供最有帮助的回答。"
                       if force_final else "已达到最大交互轮次，无法继续探索。请综合已经收集到的上下文，为用户提供全面、准确的最终回应。")
                current_messages.append({"role": "user", "content": f"【系统提示】{msg}"})
                tools = None
                force_final = False

            # 调用 LLM
            try:
                response = await self.llm_client.chat_completion(
                    messages=current_messages,
                    tools=tools,
                    tool_choice="auto",
                    temperature=params.get("temperature", 1.0),
                    top_p=params.get("top_p", 0.95),
                    frequency_penalty=params.get("frequency_penalty", 0.0),
                    presence_penalty=params.get("presence_penalty", 0.0),
                    top_k=params.get("top_k", 20),
                    force_final=force_final or step == max_steps - 1
                )
            except Exception as e:
                yield f"\n❌ 模型服务错误：{str(e)}"
                segments.append({"type": "error", "content": f"❌ {str(e)}"})
                break

            state.first_token_time = None

            # 流式解析
            async for chunk in self.stream_parser.parse(
                response, state, segments, tool_preview_active, chat_id, self.persister.repo
            ):
                yield chunk

            # 闭合推理（如果未闭合）
            if state.in_reasoning:
                duration = time.time() - state.reasoning_start_time
                yield f"<!--reasoning:end:{duration:.2f}-->"
                segments.append({
                    "type": "reasoning",
                    "content": state.reasoning_buffer,
                    "duration": f"{duration:.2f}"
                })
                state.in_reasoning = False
                state.reasoning_buffer = ""

            # ========== 蓝图模式：检测并执行计划 ==========
            if blueprint_mode:
                plan = self._extract_plan_from_content(state.final_content)
                print(f"提取到的计划: {plan}")
                if plan is not None:
                    # 1. 生成一个唯一的 Plan ID（用于后续追踪）
                    plan_id = f"plan_{uuid.uuid4().hex[:12]}"
                    plan_id_saved = plan_id

                    await PlanRepository.create_plan(plan_id, chat_id, plan)
                    
                    # 2. 构建一个特殊的 segment，类型为 'plan'
                    #    这个 segment 包含了完整的计划结构，前端拿到后可以渲染成编辑器
                    plan_segment = {
                        "type": "plan",
                        "id": plan_id,
                        "content": plan,  # 这里是具体的步骤列表
                        # "status": "pending" # 状态：等待执行
                    }
                    # segments.append(plan_segment)
                    
                    # 3. 发送一个特殊事件给前端，告诉前端“计划已就绪，请展示编辑器”
                    #    前端收到这个事件后，应该停止loading，渲染计划编辑界面
                    plan_json_str = json.dumps(plan_segment, ensure_ascii=False)
                    yield f"<!--plan_ready:{plan_json_str}-->"

                    # 4. 结束当前轮次，等待用户前端操作
                    break 

            # ========== 普通模式：执行工具调用 ==========
            valid_calls = {
                idx: tc for idx, tc in state.tool_calls_by_index.items()
                if tc["function"]["name"].strip()
            }
            if not valid_calls:
                break

            # 添加 assistant 消息
            assistant_msg = {
                "role": "assistant",
                "content": None,
                "tool_calls": list({tc["id"]: tc for tc in state.tool_calls_by_index.values() if tc.get("id")}.values())
            }
            if state.reasoning_buffer:
                assistant_msg["reasoning_content"] = state.reasoning_buffer
            current_messages.append(assistant_msg)

            # 执行工具（带实时日志队列）
            log_queue = asyncio.Queue()
            exec_task = asyncio.create_task(
                self.tool_executor.process_multiple(
                    valid_calls, tool_preview_active, context,
                    enable_parallel, max_parallel, log_queue
                )
            )

            # 实时吐出日志
            while True:
                try:
                    log_msg = log_queue.get_nowait()
                    yield log_msg
                except asyncio.QueueEmpty:
                    if exec_task.done():
                        break
                    await asyncio.sleep(0.05)
            results = exec_task.result()

            # 处理每个工具结果
            for idx, tc, res in results:
                # 审批等待
                if res.status == "need_approval":
                    for out in res.outputs:
                        yield out
                    decision_id = res.approval_info["local_call_id"]
                    confirmed = await self.approval_handler.wait_for_tool_approval(
                        decision_id, self.persister.repo, request, timeout=50
                    )
                    if confirmed:
                        context.skip_approval = True
                        approval_queue = asyncio.Queue()
                        approval_task = asyncio.create_task(
                            self.tool_executor.process_single_tool(
                                idx, tc, tool_preview_active, context, approval_queue
                            )
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
                        context.skip_approval = False
                    else:
                        # 拒绝
                        yield f"<!--tool_status:{decision_id}:rejected-->"
                        yield f"<!--tool_preview:end:{decision_id}-->"
                        self._merge_segment(segments, {
                            "type": "tool_call",
                            "content": {
                                "id": decision_id,
                                "name": res.approval_info["func_name"],
                                "status": "rejected",
                                "error_message": "用户拒绝"
                            }
                        })
                        await self.persister.repo.update_full(
                            call_id=decision_id,
                            arguments=res.approval_info["args"],
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

                # 正常处理结果
                for out in res.outputs:
                    yield out
                for seg in res.new_segments:
                    self._merge_segment(segments, seg)

                if res.failed:
                    consecutive_failures += 1
                    last_failed_tool = tc["function"]["name"] or "未知工具"
                    last_failed_reason = res.error_message or "执行失败"
                    last_failed_attempts = context.retry_count + 1
                    last_failed_elapsed = res.exec_time_ms / 1000.0
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
                if failure_behavior == "stop":
                    yield f"\n❌ 工具调用失败 {consecutive_failures} 次，已停止\n"
                    break
                elif failure_behavior == "ask":
                    suggestion = self.suggestion_gen.generate(last_failed_reason or "")
                    decision_info = {
                        "reason": last_failed_reason or f"连续失败 {consecutive_failures} 次",
                        "tool_name": last_failed_tool or "未知工具",
                        "attempts": last_failed_attempts or consecutive_failures,
                        "elapsed": round(last_failed_elapsed, 1) or round(time.time() - start_time, 1),
                        "suggestion": suggestion,
                        "threshold": max_consecutive_failures,
                        "total_attempts": consecutive_failures
                    }
                    info_json = json.dumps(decision_info, ensure_ascii=False)
                    decision_id = await self.decision_repo.create(
                        chat_id=chat_id,
                        turn_index=turn_index,
                        message=info_json,
                        timeout_seconds=50
                    )
                    yield f"<!--ask_decision:{decision_id}:{info_json}-->"

                    status = await self.approval_handler.wait_for_decision(
                        decision_id, self.decision_repo, request, timeout=50
                    )
                    if status != "continue":
                        break
                    consecutive_failures = 0
                    max_steps += 3
                    context.is_retry = True
                    force_final = False
                else:  # continue
                    force_final = True

            step += 1

        # 最终 token 统计
        if state.last_usage and state.last_usage.get("completion_tokens", 0) > 0:
            gen_time = time.time() - (state.first_token_time or time.time())
            tokens = state.last_usage["completion_tokens"]
            speed = f"{tokens / gen_time:.2f} token/s" if gen_time > 0 else "⚡瞬间完成"
            token_info = {
                "final_answer_usage": state.last_usage,
                "total_usage_all_steps": state.total_usage,
                "speed": speed
            }
            yield f"\n<!--token_usage:{json.dumps(token_info)}-->"
            segments.append({"type": "token_usage", "content": token_info})


        # 落库
        if chat_id and turn_index is not None:
            segments = self._clean_plan_tags_from_segments(segments)
            yield f"<!--segments_complete:{json.dumps(segments, ensure_ascii=False)}-->"
            segments_json = json.dumps(segments, ensure_ascii=False)
            await self.message_repo.add_assistant_message(
                chat_id=chat_id,
                content=segments_json,
                profile_id=profile_id,
                plan_id=plan_id_saved,
                model_id=model_id,
                turn_index=turn_index,
                file_ref=None
            )

    @staticmethod
    def _merge_segment(segments: list, new_seg: dict):
        if new_seg.get("type") == "tool_call" and "id" in new_seg.get("content", {}):
            seg_id = new_seg["content"]["id"]
            for i, seg in enumerate(segments):
                if seg.get("type") == "tool_call" and seg.get("content", {}).get("id") == seg_id:
                    segments[i] = new_seg
                    return
        segments.append(new_seg)

    def _extract_plan_from_content(self, content: str) -> Optional[List[Dict]]:
        """从模型输出的内容中提取计划 JSON 数组"""
        if not content:
            return None
        # 匹配 <<<PLAN_START>>> ... <<<PLAN_END>>>
        pattern = r'<<<PLAN_START>>>\s*([\s\S]*?)\s*<<<PLAN_END>>>'
        match = re.search(pattern, content)
        if not match:
            return None
        json_str = match.group(1).strip()
        try:
            plan = json.loads(json_str)
            if isinstance(plan, list):
                return plan
        except json.JSONDecodeError:
            pass
        return None

    @staticmethod
    def _clean_plan_tags_from_segments(segments: List[Dict]) -> List[Dict]:
        """移除 segments 中文本内容里的 PLAN_START/END 标签"""
        pattern = re.compile(r'<<<PLAN_START>>>[\s\S]*?<<<PLAN_END>>>')
        
        cleaned = []
        for seg in segments:
            if seg.get("type") in ("text", "reasoning") and isinstance(seg.get("content"), str):
                new_content = pattern.sub('', seg["content"]).strip()
                if new_content:  # 只保留非空内容
                    seg_copy = {**seg, "content": new_content}
                    cleaned.append(seg_copy)
                # 如果移除后为空，直接丢弃该 segment
            else:
                cleaned.append(seg)
        return cleaned