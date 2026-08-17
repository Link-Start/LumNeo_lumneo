# src/lumneo/persistence/models/profile.py
# Persistence Model —— 纯持久化数据结构（§21）。无数据库行为。
import json
from dataclasses import dataclass
from typing import Any, List, Optional


@dataclass
class ProfileModel:
    """角色配置（profiles 表）持久化模型。"""

    id: int
    name: str
    avatar: str = ""
    profile_prompt: str = ""
    tools: List[str] = None  # type: ignore
    temperature: float = 1.0
    top_p: float = 0.95
    top_k: int = 40
    frequency_penalty: float = 0.0
    presence_penalty: float = 0.0

    def __post_init__(self):
        if self.tools is None:
            self.tools = []

    @staticmethod
    def _parse_json(val):
        if val is None:
            return []
        try:
            return json.loads(val)
        except Exception:
            return []

    @classmethod
    def from_row(cls, row) -> "ProfileModel":
        return cls(
            id=row["id"],
            name=row["name"],
            avatar=row["avatar"],
            profile_prompt=row["profile_prompt"] or "",
            tools=cls._parse_json(row["tools"]),
            temperature=row["temperature"] if row["temperature"] is not None else 1.0,
            top_p=row["top_p"] if row["top_p"] is not None else 0.95,
            top_k=row["top_k"] if row["top_k"] is not None else 40,
            frequency_penalty=row["frequency_penalty"] if row["frequency_penalty"] is not None else 0.0,
            presence_penalty=row["presence_penalty"] if row["presence_penalty"] is not None else 0.0,
        )

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "avatar": self.avatar,
            "tools": self.tools,
            "profile_prompt": self.profile_prompt,
            "temperature": self.temperature,
            "top_p": self.top_p,
            "top_k": self.top_k,
            "frequency_penalty": self.frequency_penalty,
            "presence_penalty": self.presence_penalty,
        }
