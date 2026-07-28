# backend/services/llm/__init__.py
from backend.services.llm.client import LLMClient
from backend.services.llm.stream_parser import StreamParser
from backend.services.tool_execution.executor import ToolExecutor
from backend.services.tool_execution.approval import ApprovalHandler
from backend.services.tool_execution.persister import ToolPersister
from backend.services.tool_execution.suggestion import SuggestionGenerator
from backend.services.orchestrator import LLMOrchestrator
from backend.repositories import DBoolCallRepository, DBDecisionRepository, DBMessageRepository


def create_orchestrator(
    model_type: str,
    model_name: str,
    api_key: str = "",
    base_url: str = None,
    thinking: str = "enabled",
    reasoning_effort: str = "high"
) -> LLMOrchestrator:
    # 初始化客户端
    llm_client = LLMClient(model_type, model_name, api_key, base_url, thinking, reasoning_effort)

    # 初始化 Repositories
    tool_call_repo = DBoolCallRepository()
    decision_repo = DBDecisionRepository()
    message_repo = DBMessageRepository()

    # 初始化工具服务
    persister = ToolPersister(tool_call_repo)
    approval_handler = ApprovalHandler()
    suggestion_gen = SuggestionGenerator()
    tool_executor = ToolExecutor(approval_handler, persister, suggestion_gen)


    stream_parser = StreamParser()

    return LLMOrchestrator(
        llm_client=llm_client,
        tool_executor=tool_executor,
        stream_parser=stream_parser,
        approval_handler=approval_handler,
        persister=persister,
        decision_repo=decision_repo,
        message_repo=message_repo,
        suggestion_gen=suggestion_gen,
    )