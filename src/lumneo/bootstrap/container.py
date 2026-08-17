# src/lumneo/bootstrap/container.py
# 组合根（Composition Root，§91-92）。
#
# 整个应用唯一允许“new”出具体实现并把依赖装配起来的地方。所有跨层依赖通过
# 构造函数注入（Constructor Injection）完成；模块内部不再自行实例化具体类。
from typing import Optional

from lumneo.kernel.config.app_config import config
from lumneo.persistence.database import Database, set_database
from lumneo.persistence.repositories import (
    SQLConversationRepository,
    SQLMessageRepository,
    SQLProfileRepository,
    SQLProviderRepository,
    SQLSkillRepository,
    SQLToolCallRepository,
    SQLDecisionRepository,
    SQLPlanRepository,
)
from lumneo.infrastructure.filesystem.local_storage import LocalFileStorage
from lumneo.runtime.tools.execution.persister import ToolPersister
from lumneo.runtime.tools.execution.approval import ApprovalHandler
from lumneo.runtime.tools.execution.suggestion import SuggestionGenerator
from lumneo.runtime.tools.execution.executor import ToolExecutor
from lumneo.runtime.llm.stream_parser import StreamParser
from lumneo.runtime.tools.system.skill_lookup import set_skill_lookup
from lumneo.runtime.mcp.mcp_client import MCPClientManager
from lumneo.conversation.service.chat_service import ChatService
from lumneo.conversation.facade.conversation_facade import ConversationFacade
from lumneo.application.facade import ApplicationFacade


class Container:
    """应用容器：持有所有已装配的组件实例（单例）。"""

    def __init__(self):
        self.database: Optional[Database] = None
        self.repos: dict = {}
        self.storage: Optional[LocalFileStorage] = None
        self.tool_executor: Optional[ToolExecutor] = None
        self.stream_parser: Optional[StreamParser] = None
        self.chat_service: Optional[ChatService] = None
        self.facade: Optional[ConversationFacade] = None
        self.resource_facade: Optional[ApplicationFacade] = None
        self.mcp_manager: Optional[MCPClientManager] = None

    async def init(self) -> None:
        # 1. 数据库（基础设施）——统一放在 data 子目录下（config.db_path）
        db_path = str(config.db_path)
        self.database = Database(db_path)
        await self.database.init()
        set_database(self.database)

        # 2. Repository 实现（注入 Database）
        self.repos = {
            "conversation": SQLConversationRepository(self.database),
            "message": SQLMessageRepository(self.database),
            "profile": SQLProfileRepository(self.database),
            "provider": SQLProviderRepository(self.database),
            "skill": SQLSkillRepository(self.database),
            "tool_call": SQLToolCallRepository(self.database),
            "decision": SQLDecisionRepository(self.database),
            "plan": SQLPlanRepository(self.database),
        }

        # 3. 文件存储（基础设施）
        self.storage = LocalFileStorage()

        # 4. 技能查询注入点（§60：工具不直接查库）
        skill_repo = self.repos["skill"]

        async def _lookup_skill_file_path(skill_id: str):
            skill = await skill_repo.get_by_id(skill_id)
            return skill.file_path if skill else None

        set_skill_lookup(_lookup_skill_file_path)

        # 5. 工具执行共享组件（运行时）
        persister = ToolPersister(tool_call_repo=self.repos["tool_call"], storage=self.storage)
        approval_handler = ApprovalHandler()
        suggestion_gen = SuggestionGenerator()
        self.tool_executor = ToolExecutor(approval_handler, persister, suggestion_gen)
        self.stream_parser = StreamParser()

        # 6. MCP 客户端（运行时，外部连接）
        self.mcp_manager = MCPClientManager()
        try:
            await self.mcp_manager.connect_from_config(str(config.mcp_config_path))
        except Exception:
            # MCP 连接失败不应阻断启动；前台无 MCP 工具时只是少几个工具
            pass

        # 7. 对话服务（领域服务）
        self.chat_service = ChatService(
            tool_executor=self.tool_executor,
            stream_parser=self.stream_parser,
            approval_handler=approval_handler,
            persister=persister,
            suggestion_gen=suggestion_gen,
            decision_repo=self.repos["decision"],
            message_repo=self.repos["message"],
            plan_repo=self.repos["plan"],
            profile_repo=self.repos["profile"],
            provider_repo=self.repos["provider"],
            skill_repo=self.repos["skill"],
        )

        # 8. 对话门面（对外边界）
        self.facade = ConversationFacade(
            chat_service=self.chat_service,
            decision_repo=self.repos["decision"],
        )

        # 9. 应用层管理门面（聊天/画像/模型/技能/工具调用/计划/文件/工作区/协作）
        self.resource_facade = ApplicationFacade(
            chat_repo=self.repos["conversation"],
            message_repo=self.repos["message"],
            profile_repo=self.repos["profile"],
            provider_repo=self.repos["provider"],
            skill_repo=self.repos["skill"],
            tool_call_repo=self.repos["tool_call"],
            plan_repo=self.repos["plan"],
            storage=self.storage,
        )


async def build_container() -> Container:
    """构建并初始化应用容器。"""
    container = Container()
    await container.init()
    return container
