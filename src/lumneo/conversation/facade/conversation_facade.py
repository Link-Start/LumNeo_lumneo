# conversation/facade/conversation_facade.py
# 对话领域对外的门面边界（§46-47）。
#
# API 层只通过本门面访问对话领域；领域内部的 Repository / Service 不直接暴露给外层。
# 门面聚合 ChatService（流式对话）与少量直接查询（工具清单、用户决策、系统信息）。
from typing import List, Dict, Any

from lumneo.runtime.tools.registry import get_local_tools, get_mcp_tools, get_all_tools
from lumneo.runtime.context import disabled_tools
from lumneo.conversation.ports.decision_repository import DecisionRepository
from lumneo.conversation.service.chat_service import ChatService
from lumneo.kernel.common.util import get_local_ip
from lumneo.kernel.config.app_config import config
import lumneo


class ConversationFacade:
    def __init__(self, chat_service: ChatService, decision_repo: DecisionRepository):
        self.chat_service = chat_service
        self.decision_repo = decision_repo

    async def generate_chat(self, **kwargs) -> Any:
        """流式生成对话响应（yield 字符串）。"""
        return self.chat_service.generate_chat(**kwargs)

    async def list_tools(self, mcp_manager=None) -> Dict:
        """返回当前可用（启用）工具清单。

        无 Profile 上下文时枚举全部本地工具（默认启用 + 需 Profile 授权的工具）
        以及 MCP 工具，与 get_tools_info 保持一致。各工具最终是否对 LLM 开放，
        由 ChatService 依据 Profile 的 allowed_tools / default_tools / disabled_tools
        在每轮对话中动态裁决（见 chat_service.generate_chat）。
        """
        local_tools = get_local_tools()
        enable_tools = [t for t in local_tools if t["function"]["name"] in disabled_tools]
        mcp_tools = await get_mcp_tools(mcp_manager)
        enable_tools.extend(mcp_tools)
        return {"tools": enable_tools}

    async def get_tools_info(self, mcp_manager=None) -> Dict:
        """返回所有工具的标题与描述。"""
        all_tools = await get_all_tools(mcp_manager)
        tool_json = {}
        for tool in all_tools:
            tool_json[tool["function"]["name"]] = {
                'title': tool["function"].get("title", ""),
                'description': tool["function"]["description"],
            }
        return tool_json

    async def update_decision(self, decision_id: int, choice: str) -> Dict:
        """用户决策回写。"""
        if choice not in ['continue', 'stop']:
            raise ValueError("无效的选择")
        status = await self.decision_repo.get_status(decision_id)
        if status is None:
            raise LookupError("决策不存在")
        if status != 'pending':
            raise ValueError("该决策已被处理")
        success = await self.decision_repo.update_status(decision_id, choice)
        if not success:
            raise RuntimeError("更新失败")
        return {"success": True}

    async def get_decisions(self, chat_id: str) -> List[Dict]:
        """获取某对话的所有决策记录（按时间倒序）。"""
        records = await self.decision_repo.list_by_chat(chat_id)
        return [r.to_dict() for r in records]

    async def get_system_info(self) -> Dict:
        """返回系统基础信息（工作区、上传目录、本地 IP）。"""
        return {
            "workspace_dir": str(lumneo.workspace_path),
            "upload_dir": str(config.uploads_dir),
            "local_ip": get_local_ip(),
        }
