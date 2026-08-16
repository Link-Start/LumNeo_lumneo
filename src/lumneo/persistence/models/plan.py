# persistence/models/plan.py
# Persistence Model —— 计划记录（plans 表）持久化模型（§21）。无数据库行为。
import json
from dataclasses import dataclass
from typing import Any, List, Optional


@dataclass
class PlanModel:
    """计划记录（plans 表）持久化模型。"""

    plan_id: str
    chat_id: str
    steps: List[dict] = None  # type: ignore
    created_at: Any = None
    updated_at: Any = None

    def __post_init__(self):
        if self.steps is None:
            self.steps = []

    @classmethod
    def from_row(cls, row) -> "PlanModel":
        try:
            steps = json.loads(row["steps"]) if row["steps"] else []
        except Exception:
            steps = []
        return cls(
            plan_id=row["plan_id"],
            chat_id=row["chat_id"],
            steps=steps,
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    def to_dict(self) -> dict:
        return {
            "plan_id": self.plan_id,
            "chat_id": self.chat_id,
            "steps": self.steps,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }
