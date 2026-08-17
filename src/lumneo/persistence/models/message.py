# src/lumneo/persistence/models/message.py
# Persistence Model —— 纯持久化数据结构（§21）。无数据库行为。
import json
from dataclasses import dataclass, field
from typing import Any, Dict, Optional


@dataclass
class MessageModel:
    """消息（messages 表）持久化模型。可携带关联 profile/model/plan 的只读快照。"""

    id: Any
    chat_id: str
    role: str
    content: Any = None
    profile_id: Optional[int] = None
    model_id: Optional[str] = None
    file_ref: Any = None
    turn_index: int = 0
    plan_id: Optional[str] = None
    created_at: Any = None

    # 关联快照（由 JOIN 查询填充，非独立字段）
    profile: Optional[Dict[str, Any]] = None
    model: Optional[Dict[str, Any]] = None
    plan: Optional[Any] = None

    @staticmethod
    def _parse_json(val):
        if val is None:
            return None
        try:
            return json.loads(val)
        except Exception:
            return val

    @classmethod
    def from_row(cls, row) -> "MessageModel":
        content = row["content"]
        # assistant 的 content 可能是 JSON 字符串（分段结构），尝试解析
        if isinstance(content, str) and content.strip().startswith("{"):
            try:
                content = json.loads(content)
            except Exception:
                pass

        file_ref = cls._parse_json(row["file_ref"])
        plan_id = None if (row["plan_id"] in (None, "")) else row["plan_id"]

        profile = None
        if "p_id" in row.keys() and row["p_id"] is not None:
            profile = {
                "id": row["p_id"],
                "name": row["p_name"] or "",
                "avatar": row["p_avatar"] or "",
            }

        model = None
        if "m_id" in row.keys() and row["m_id"] is not None:
            model = {
                "id": row["m_id"],
                "name": row["m_name"] or "",
                "type": row["m_type"] or "",
                "modelName": row["m_modelName"] or "",
            }

        plan = None
        if "plan_steps" in row.keys() and row["plan_steps"] is not None:
            try:
                plan = json.loads(row["plan_steps"])
            except Exception:
                plan = None

        return cls(
            id=row["id"],
            chat_id=row["chat_id"],
            role=row["role"],
            content=content,
            profile_id=row["profile_id"],
            model_id=row["model_id"],
            file_ref=file_ref,
            turn_index=row["turn_index"],
            plan_id=plan_id,
            created_at=row["created_at"],
            profile=profile,
            model=model,
            plan=plan,
        )

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "chat_id": self.chat_id,
            "role": self.role,
            "content": self.content,
            "profile_id": self.profile_id,
            "profile": self.profile,
            "plan_id": self.plan_id,
            "plan": self.plan if self.role != "user" else None,
            "model_id": self.model_id,
            "model": self.model,
            "file_ref": self.file_ref,
            "turn_index": self.turn_index,
            "created_at": self.created_at,
        }
