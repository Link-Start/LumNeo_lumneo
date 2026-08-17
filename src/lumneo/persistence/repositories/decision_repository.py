# persistence/repositories/decision_repository.py
# Persistence —— Repository Implementation（§24 / §79）。
from typing import List, Optional

from lumneo.conversation.ports.decision_repository import DecisionRepository
from lumneo.persistence.database import Database
from lumneo.persistence.models.decision import DecisionModel
from lumneo.persistence.repositories._base import BaseRepository
from lumneo.kernel.common.ids import now_iso

# 合法的状态集合（保持与原实现一致：pending / continue / stop / timeout）。
_VALID_STATUSES = ("pending", "continue", "stop", "timeout")


class SQLDecisionRepository(DecisionRepository, BaseRepository):
    """DecisionRepository 的 SQLite 实现。"""

    def __init__(self, database: Database):
        BaseRepository.__init__(self, database)

    async def create(self, chat_id: Optional[str], turn_index: Optional[int],
                     message: str, timeout_seconds: int) -> int:
        async with self._session() as db:
            cursor = await db.execute(
                """INSERT INTO user_decisions (chat_id, turn_index, message, timeout_seconds, status, created_at, updated_at)
                   VALUES (?, ?, ?, ?, 'pending', ?, ?)""",
                (chat_id, turn_index, message, timeout_seconds, now_iso(), now_iso()),
            )
            return cursor.lastrowid

    async def get_status(self, decision_id: int) -> Optional[str]:
        async with self._session() as db:
            cursor = await db.execute("SELECT status FROM user_decisions WHERE id = ?", (decision_id,))
            row = await cursor.fetchone()
            return row["status"] if row else None

    async def update_status(self, decision_id: int, status: str) -> bool:
        if status not in _VALID_STATUSES:
            return False
        async with self._session() as db:
            cursor = await db.execute(
                "UPDATE user_decisions SET status = ?, updated_at = ? WHERE id = ?",
                (status, now_iso(), decision_id),
            )
            return cursor.rowcount > 0

    async def get(self, decision_id: int) -> Optional[DecisionModel]:
        async with self._session() as db:
            cursor = await db.execute("SELECT * FROM user_decisions WHERE id = ?", (decision_id,))
            row = await cursor.fetchone()
            return DecisionModel.from_row(row) if row else None

    async def list_by_chat(self, chat_id: str, limit: int = 50) -> List[DecisionModel]:
        async with self._session() as db:
            cursor = await db.execute(
                "SELECT * FROM user_decisions WHERE chat_id = ? ORDER BY created_at DESC LIMIT ?",
                (chat_id, limit),
            )
            rows = await cursor.fetchall()
            return [DecisionModel.from_row(r) for r in rows]
