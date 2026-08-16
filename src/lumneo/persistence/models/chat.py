# persistence/models/chat.py
# Persistence Model —— 纯持久化数据结构 / ORM 映射（§21）。
#
# 根据规范：Persistence Model 只负责字段定义、类型声明、纯数据转换（to_dict/from_row），
# 不得拥有任何数据库行为（§22）：禁止 session.add / commit / query / save / delete。
from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass
class ChatModel:
    """对话（chats 表）持久化模型。"""

    id: str
    title: str = "新对话"
    created_at: Any = None

    @classmethod
    def from_row(cls, row) -> "ChatModel":
        return cls(
            id=row["id"],
            title=row["title"],
            created_at=row["created_at"],
        )

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "title": self.title,
            "created_at": self.created_at,
        }
