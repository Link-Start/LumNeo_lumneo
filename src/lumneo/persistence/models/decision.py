# persistence/models/decision.py
# Persistence Model —— 用户决策记录（user_decisions 表）持久化模型（§21）。无数据库行为。
from dataclasses import dataclass
from typing import Any, Optional


@dataclass
class DecisionModel:
    """用户决策记录（user_decisions 表）持久化模型。"""

    id: int
    chat_id: str
    turn_index: int
    message: Optional[str] = None
    status: str = "pending"
    timeout_seconds: int = 60
    created_at: Any = None
    updated_at: Any = None

    @classmethod
    def from_row(cls, row) -> "DecisionModel":
        return cls(
            id=row["id"],
            chat_id=row["chat_id"],
            turn_index=row["turn_index"],
            message=row["message"],
            status=row["status"],
            timeout_seconds=row["timeout_seconds"] if row["timeout_seconds"] is not None else 60,
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "chat_id": self.chat_id,
            "turn_index": self.turn_index,
            "message": self.message,
            "status": self.status,
            "timeout_seconds": self.timeout_seconds,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }
