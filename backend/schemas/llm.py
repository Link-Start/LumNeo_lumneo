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
    request: Optional[Any]  # FastAPI Request
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