# src/lumneo/persistence/models/tool_call.py
# Persistence Model —— 工具调用记录（tool_calls 表）持久化模型（§21）。无数据库行为。
import json
from dataclasses import dataclass, field
from typing import Any, Dict, Optional


@dataclass
class ToolCallModel:
    """工具调用记录（tool_calls 表）持久化模型。"""

    call_id: str
    chat_id: str
    tool_name: str
    id: Optional[int] = None
    arguments: Any = None
    result: Optional[str] = None
    meta_data: Any = None
    status: str = "calling"
    execution_time: Optional[int] = None
    error_message: Optional[str] = None
    created_at: Any = None
    updated_at: Any = None

    @staticmethod
    def _parse_json(val):
        if val is None:
            return None
        try:
            return json.loads(val)
        except Exception:
            return val

    @classmethod
    def from_row(cls, row) -> "ToolCallModel":
        return cls(
            id=row["id"],
            call_id=row["call_id"],
            chat_id=row["chat_id"],
            tool_name=row["tool_name"],
            arguments=cls._parse_json(row["arguments"]),
            result=row["result"],
            meta_data=cls._parse_json(row["meta_data"]),
            status=row["status"],
            execution_time=row["execution_time"],
            error_message=row["error_message"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "chat_id": self.chat_id,
            "call_id": self.call_id,
            "tool_name": self.tool_name,
            "arguments": self.arguments,
            "result": self.result,
            "meta_data": self.meta_data,
            "status": self.status,
            "execution_time": self.execution_time,
            "error_message": self.error_message,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }
