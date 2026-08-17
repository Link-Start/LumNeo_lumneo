# src/lumneo/persistence/models/provider.py
# Persistence Model —— LLM Provider 配置（models 表）持久化模型（§21）。无数据库行为。
#
# 注意：表名为 "models"，为避免与 persistence/models/ 包名冲突，这里命名为 ProviderModel，
# 表示“一个 LLM 提供方/模型配置记录”。Domain 模型见 conversation/domain（如有需要）。
from dataclasses import dataclass
from typing import Any


@dataclass
class ProviderModel:
    """LLM Provider 配置（models 表）持久化模型。"""

    id: str
    name: str
    type: str
    model_name: str
    base_url: str
    api_key: str

    @classmethod
    def from_row(cls, row) -> "ProviderModel":
        return cls(
            id=row["id"],
            name=row["name"],
            type=row["type"],
            model_name=row["modelName"],
            base_url=row["baseUrl"],
            api_key=row["apiKey"],
        )

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "type": self.type,
            "modelName": self.model_name,
            "baseUrl": self.base_url,
            "apiKey": self.api_key,
        }
