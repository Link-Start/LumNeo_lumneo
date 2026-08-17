# src/lumneo/persistence/repositories/plan_repository.py
# Persistence —— Repository Implementation（§24 / §79）。
import aiosqlite
import json
from typing import List, Optional

from lumneo.conversation.ports.plan_repository import PlanRepository
from lumneo.persistence.database import Database
from lumneo.persistence.repositories._base import BaseRepository


class SQLPlanRepository(PlanRepository, BaseRepository):
    """PlanRepository 的 SQLite 实现。"""

    def __init__(self, database: Database):
        BaseRepository.__init__(self, database)

    async def create(self, plan_id: str, chat_id: str, steps: List[dict]) -> bool:
        async with self._session() as db:
            try:
                await db.execute(
                    "INSERT INTO plans (plan_id, chat_id, steps) VALUES (?, ?, ?)",
                    (plan_id, chat_id, json.dumps(steps, ensure_ascii=False)),
                )
                return True
            except aiosqlite.IntegrityError:
                return False

    async def update(self, plan_id: str, steps: List[dict]) -> bool:
        async with self._session() as db:
            cursor = await db.execute(
                "UPDATE plans SET steps = ?, updated_at = CURRENT_TIMESTAMP WHERE plan_id = ?",
                (json.dumps(steps, ensure_ascii=False), plan_id),
            )
            return cursor.rowcount > 0

    async def get(self, plan_id: str) -> Optional[List[dict]]:
        async with self._session() as db:
            cursor = await db.execute("SELECT steps FROM plans WHERE plan_id = ?", (plan_id,))
            row = await cursor.fetchone()
            if not row:
                return None
            try:
                return json.loads(row["steps"]) if row["steps"] else []
            except Exception:
                return []
