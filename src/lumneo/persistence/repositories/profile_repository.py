# src/lumneo/persistence/repositories/profile_repository.py
# Persistence —— Repository Implementation（§24 / §79）。
import json
from typing import List, Optional

from lumneo.conversation.ports.profile_repository import ProfileRepository
from lumneo.persistence.database import Database
from lumneo.persistence.models.profile import ProfileModel
from lumneo.persistence.repositories._base import BaseRepository


class SQLProfileRepository(ProfileRepository, BaseRepository):
    """ProfileRepository 的 SQLite 实现。"""

    def __init__(self, database: Database):
        BaseRepository.__init__(self, database)

    async def create(self, **fields) -> ProfileModel:
        async with self._session() as db:
            tools_json = json.dumps(fields.get("tools", []), ensure_ascii=False)
            cursor = await db.execute(
                """INSERT INTO profiles
                   (name, avatar, tools, profile_prompt, temperature, top_p, top_k, frequency_penalty, presence_penalty)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    fields["name"],
                    fields.get("avatar", ""),
                    tools_json,
                    fields.get("profile_prompt", ""),
                    fields.get("temperature", 1.0),
                    fields.get("top_p", 0.95),
                    fields.get("top_k", 40),
                    fields.get("frequency_penalty", 0.0),
                    fields.get("presence_penalty", 0.0),
                ),
            )
            cursor = await db.execute("SELECT * FROM profiles WHERE id = ?", (cursor.lastrowid,))
            return ProfileModel.from_row(await cursor.fetchone())

    async def update(self, profile_id: int, **fields) -> Optional[ProfileModel]:
        async with self._session() as db:
            updates = []
            params = []
            mapping = {
                "name": "name", "avatar": "avatar", "profile_prompt": "profile_prompt",
                "temperature": "temperature", "top_p": "top_p", "top_k": "top_k",
                "frequency_penalty": "frequency_penalty", "presence_penalty": "presence_penalty",
            }
            if "tools" in fields:
                updates.append("tools = ?")
                params.append(json.dumps(fields["tools"], ensure_ascii=False))
            for key, col in mapping.items():
                if key in fields:
                    updates.append(f"{col} = ?")
                    params.append(fields[key])
            if not updates:
                cursor = await db.execute("SELECT * FROM profiles WHERE id = ?", (profile_id,))
                row = await cursor.fetchone()
                return ProfileModel.from_row(row) if row else None
            params.append(profile_id)
            await db.execute(f"UPDATE profiles SET {', '.join(updates)} WHERE id = ?", tuple(params))
            if db.total_changes == 0:
                return None
            cursor = await db.execute("SELECT * FROM profiles WHERE id = ?", (profile_id,))
            return ProfileModel.from_row(await cursor.fetchone())

    async def list(self) -> List[ProfileModel]:
        async with self._session() as db:
            cursor = await db.execute(
                "SELECT id, name, avatar, tools, profile_prompt, temperature, top_p, top_k, "
                "frequency_penalty, presence_penalty FROM profiles"
            )
            rows = await cursor.fetchall()
            return [ProfileModel.from_row(row) for row in rows]

    async def delete(self, profile_id: int) -> bool:
        async with self._session() as db:
            await db.execute("DELETE FROM profiles WHERE id = ?", (profile_id,))
            return True

    async def get_by_id(self, profile_id: int) -> Optional[ProfileModel]:
        async with self._session() as db:
            cursor = await db.execute("SELECT * FROM profiles WHERE id = ?", (profile_id,))
            row = await cursor.fetchone()
            return ProfileModel.from_row(row) if row else None
