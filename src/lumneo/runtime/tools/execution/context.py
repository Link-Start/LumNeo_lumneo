# runtime/tools/execution/context.py
# 工具执行的上下文与结果数据契约（原 backend/schemas/llm.py 中相关定义）。
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional


@dataclass
class ToolExecutionContext:
    chat_id: Optional[str]
    mcp_manager: Any
    approval_mode: bool
    auto_decision: bool
    tool_timeout: int
    retry_count: int
    retry_delay: int
    request: Optional[Any]
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
