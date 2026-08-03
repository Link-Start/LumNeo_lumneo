# backend/services/tool_execution/approval.py
import asyncio
from typing import Optional
from backend.services.tools import is_dangerous_tool


class ApprovalHandler:
    @staticmethod
    def need_approval(func_name: str, auto_decision: bool) -> bool:
        """判断是否需要用户审批"""
        if auto_decision:
            return is_dangerous_tool(func_name)
        return True  # 手动模式全部需要审批

    @staticmethod
    async def wait_for_tool_approval(
        decision_id: str,
        repo,  # ToolCallRepository
        request=None,
        timeout=50,
        poll_interval=1
    ) -> Optional[bool]:
        """轮询工具调用状态，返回 True(批准)、False(拒绝)、None(超时/断开)"""
        for _ in range(timeout):
            if request and await request.is_disconnected():
                return None
            status = await repo.get_status(decision_id)
            if status == "confirmed":
                return True
            if status == "cancelled":
                return False
            await asyncio.sleep(poll_interval)
        return None

    @staticmethod
    async def wait_for_decision(
        decision_id: str,
        repo,  # DecisionRepository
        request=None,
        timeout=50,
        poll_interval=1
    ) -> Optional[str]:
        """轮询用户决策（continue / stop）"""
        for _ in range(timeout):
            if request and await request.is_disconnected():
                return None
            status = await repo.get_status(decision_id)
            if status in ("continue", "stop"):
                return status
            await asyncio.sleep(poll_interval)
        return None