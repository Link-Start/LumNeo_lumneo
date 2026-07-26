# backend/db/decisions.py
import aiosqlite
from datetime import datetime
from typing import Optional
from backend.database import get_db
from backend.bootstrap import logger


class DecisionRecord:
    """决策记录封装类"""
    def __init__(self, row: aiosqlite.Row):
        self.id = row['id']
        self.chat_id = row['chat_id']
        self.turn_index = row['turn_index']
        self.message = row['message']
        self.status = row['status']
        self.timeout_seconds = row['timeout_seconds']
        self.created_at = row['created_at']
        self.updated_at = row['updated_at']
    
    def to_dict(self):
        return {
            'id': self.id,
            'chat_id': self.chat_id,
            'turn_index': self.turn_index,
            'message': self.message,
            'status': self.status,
            'timeout_seconds': self.timeout_seconds,
            'created_at': self.created_at,
            'updated_at': self.updated_at,
        }


async def create_decision(
    chat_id: str,
    turn_index: int,
    message: str = "",
    timeout_seconds: int = 60
) -> int:
    """创建一条用户决策记录，返回决策 ID"""
    db = await get_db()
    try:
        cursor = await db.execute(
            """
            INSERT INTO user_decisions (chat_id, turn_index, message, timeout_seconds, status, created_at, updated_at)
            VALUES (?, ?, ?, ?, 'pending', ?, ?)
            """,
            (chat_id, turn_index, message, timeout_seconds, datetime.utcnow().isoformat(), datetime.utcnow().isoformat())
        )
        await db.commit()
        return cursor.lastrowid
    finally:
        await db.close()


async def get_decision_status(decision_id: int) -> Optional[str]:
    """获取决策状态（pending/continue/stop）"""
    db = await get_db()
    try:
        async with db.execute(
            "SELECT status FROM user_decisions WHERE id = ?",
            (decision_id,)
        ) as cursor:
            row = await cursor.fetchone()
            return row[0] if row else None
    finally:
        await db.close()


async def update_decision_status(decision_id: int, status: str) -> bool:
    """更新决策状态，返回是否成功"""
    if status not in ('continue', 'stop'):
        return False
    
    db = await get_db()
    try:
        await db.execute(
            "UPDATE user_decisions SET status = ?, updated_at = ? WHERE id = ?",
            (status, datetime.utcnow().isoformat(), decision_id)
        )
        await db.commit()
        return True
    finally:
        await db.close()


async def get_decision(decision_id: int) -> Optional[DecisionRecord]:
    """获取完整的决策记录"""
    db = await get_db()
    try:
        async with db.execute(
            "SELECT id, chat_id, turn_index, message, status, timeout_seconds, created_at, updated_at FROM user_decisions WHERE id = ?",
            (decision_id,)
        ) as cursor:
            row = await cursor.fetchone()
            return DecisionRecord(row) if row else None
    finally:
        await db.close()


async def delete_decision(decision_id: int):
    """删除决策记录（可选，用于清理）"""
    db = await get_db()
    try:
        await db.execute("DELETE FROM user_decisions WHERE id = ?", (decision_id,))
        await db.commit()
    finally:
        await db.close()


async def cleanup_stale_decisions(older_than_hours: int = 24):
    """清理过期的决策记录（可选维护任务）"""
    db = await get_db()
    try:
        cutoff = datetime.utcnow().timestamp() - older_than_hours * 3600
        await db.execute(
            "DELETE FROM user_decisions WHERE updated_at < datetime(?, 'unixepoch') AND status != 'pending'",
            (cutoff,)
        )
        await db.commit()
    finally:
        await db.close()


async def list_decisions_by_chat(chat_id: str, limit: int = 50) -> list[DecisionRecord]:
    """获取某个对话的所有决策记录（按时间倒序）"""
    db = await get_db()
    try:
        async with db.execute(
            "SELECT id, chat_id, turn_index, message, status, timeout_seconds, created_at, updated_at FROM user_decisions WHERE chat_id = ? ORDER BY created_at DESC LIMIT ?",
            (chat_id, limit)
        ) as cursor:
            rows = await cursor.fetchall()
            return [DecisionRecord(row) for row in rows]
    finally:
        await db.close()