# persistence/models/skill.py
# Persistence Model —— 技能记录（skills 表）持久化模型（§21）。无数据库行为。
import json
from dataclasses import dataclass, field
from typing import Any, Dict, Optional


@dataclass
class SkillModel:
    """技能记录（skills 表）持久化模型。"""

    id: str
    name: str
    file_path: str
    description: str = ""
    enabled: bool = True
    is_global: bool = False
    metadata: Dict[str, Any] = field(default_factory=dict)
    created_at: Any = None
    updated_at: Any = None

    @classmethod
    def from_row(cls, row) -> "SkillModel":
        try:
            meta = json.loads(row["metadata"]) if row["metadata"] else {}
        except Exception:
            meta = {}
        return cls(
            id=row["id"],
            name=row["name"],
            file_path=row["file_path"],
            description=row["description"] or "",
            enabled=bool(row["enabled"]),
            is_global=bool(row["is_global"]),
            metadata=meta,
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    def to_dict(self, *, with_description: bool = True) -> dict:
        data = {
            "id": self.id,
            "name": self.name,
            "enabled": self.enabled,
            "is_global": self.is_global,
            "metadata": self.metadata,
            "file_path": self.file_path,
        }
        if with_description:
            data["description"] = self.description or self.metadata.get("description", "")
        return data
