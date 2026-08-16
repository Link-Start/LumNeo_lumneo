# persistence/repositories/provider_repository.py
# Persistence —— Repository Implementation（§24 / §79）。对应原 models 表。
import json
import uuid
from typing import List, Optional

from lumneo.conversation.ports.provider_repository import ProviderRepository
from lumneo.persistence.database import Database
from lumneo.persistence.models.provider import ProviderModel
from lumneo.persistence.repositories._base import BaseRepository


class SQLProviderRepository(ProviderRepository, BaseRepository):
    """ProviderRepository 的 SQLite 实现。"""

    def __init__(self, database: Database):
        BaseRepository.__init__(self, database)

    async def list(self) -> List[ProviderModel]:
        async with self._session() as db:
            cursor = await db.execute(
                "SELECT id, name, type, modelName, baseUrl, apiKey FROM models ORDER BY name"
            )
            rows = await cursor.fetchall()
            return [ProviderModel.from_row(row) for row in rows]

    async def create(self, **fields) -> ProviderModel:
        async with self._session() as db:
            model_id = str(uuid.uuid4())
            final_model_name = fields.get("model_name") or ""
            cursor = await db.execute(
                "INSERT INTO models (id, name, type, modelName, baseUrl, apiKey) VALUES (?, ?, ?, ?, ?, ?)",
                (
                    model_id, fields["name"], fields["type"],
                    final_model_name, fields["base_url"], fields["api_key"],
                ),
            )
            cursor = await db.execute("SELECT * FROM models WHERE id = ?", (model_id,))
            return ProviderModel.from_row(await cursor.fetchone())

    async def update(self, model_id: str, **fields) -> Optional[ProviderModel]:
        async with self._session() as db:
            updates = []
            params = []
            mapping = {
                "name": "name", "type": "type", "model_name": "modelName",
                "base_url": "baseUrl", "api_key": "apiKey",
            }
            for key, col in mapping.items():
                if key in fields:
                    updates.append(f"{col} = ?")
                    params.append(fields[key])
            if not updates:
                cursor = await db.execute("SELECT * FROM models WHERE id = ?", (model_id,))
                row = await cursor.fetchone()
                return ProviderModel.from_row(row) if row else None
            params.append(model_id)
            await db.execute(f"UPDATE models SET {', '.join(updates)} WHERE id = ?", tuple(params))
            if db.total_changes == 0:
                return None
            cursor = await db.execute("SELECT * FROM models WHERE id = ?", (model_id,))
            return ProviderModel.from_row(await cursor.fetchone())

    async def delete(self, model_id: str) -> bool:
        async with self._session() as db:
            await db.execute("DELETE FROM models WHERE id = ?", (model_id,))
            return True
