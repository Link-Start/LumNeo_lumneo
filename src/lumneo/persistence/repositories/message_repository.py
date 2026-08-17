# persistence/repositories/message_repository.py
# Persistence —— Repository Implementation（§24 / §79）。
import asyncio
import json
import os
from typing import Any, Dict, List, Optional

from lumneo.conversation.ports.message_repository import MessageRepository
from lumneo.persistence.database import Database
from lumneo.persistence.models.message import MessageModel
from lumneo.persistence.repositories._base import BaseRepository
from lumneo.kernel.config.app_config import config
from lumneo.kernel.common.logger import logger


def _collect_tool_disk_files(meta_rows: List[Any]) -> List[str]:
    """根据 tool_calls 的 meta_data 收集需要删除的磁盘文件路径（不执行 I/O）。"""
    files = []
    for meta in meta_rows:
        if not meta:
            continue
        try:
            meta_data = meta
            # 兼容双重 JSON 编码：最多尝试解析两层
            for _ in range(2):
                if isinstance(meta_data, str):
                    meta_data = json.loads(meta_data)
                else:
                    break

            if not isinstance(meta_data, dict):
                continue

            if meta_data.get("storage_type") == "file":
                file_path = meta_data.get("file_path")
                if file_path:
                    abs_path = os.path.abspath(os.path.join(str(config.cache_dir), file_path))
                    files.append(abs_path)
        except Exception:
            continue
    return files


def _extract_call_ids_from_content(content) -> List[str]:
    """从 assistant 消息内容（分段 JSON）中提取工具 call_id。"""
    if not isinstance(content, str):
        return []
    try:
        segments = json.loads(content)
    except Exception:
        return []
    if not isinstance(segments, list):
        return []
    ids = []
    for seg in segments:
        if isinstance(seg, dict) and seg.get("type") == "tool_call":
            for key in ("id", "call_id"):
                val = seg.get(key) or seg.get("content", {}).get(key)
                if val:
                    ids.append(val)
                    break
    return ids


class SQLMessageRepository(MessageRepository, BaseRepository):
    """MessageRepository 的 SQLite 实现。"""

    def __init__(self, database: Database):
        BaseRepository.__init__(self, database)

    async def get_by_chat(self, chat_id: str) -> List[MessageModel]:
        async with self._session() as db:
            cursor = await db.execute(
                """
                SELECT
                    m.id, m.chat_id, m.role, m.content,
                    m.profile_id, m.file_ref, m.turn_index, m.created_at, m.plan_id,
                    p.id AS p_id, p.name AS p_name, p.avatar AS p_avatar,
                    m.model_id,
                    md.id AS m_id, md.name AS m_name, md.type AS m_type, md.modelName AS m_modelName,
                    pl.steps AS plan_steps
                FROM messages m
                LEFT JOIN profiles p ON m.profile_id = p.id
                LEFT JOIN models md ON m.model_id = md.id
                LEFT JOIN plans pl ON m.plan_id = pl.plan_id
                WHERE m.chat_id = ?
                ORDER BY m.turn_index ASC
                """,
                (chat_id,),
            )
            rows = await cursor.fetchall()
            return [MessageModel.from_row(row) for row in rows]

    async def add(
        self,
        chat_id: str,
        role: str,
        content: Any,
        profile_id: Optional[int] = None,
        plan_id: Optional[str] = None,
        model_id: Optional[str] = None,
        file_ref: Optional[dict] = None,
        turn_index: Optional[int] = None,
    ) -> MessageModel:
        async with self._session() as db:
            if turn_index is None:
                cursor = await db.execute(
                    "SELECT IFNULL(MAX(turn_index), 0) + 1 as next_turn FROM messages WHERE chat_id = ?",
                    (chat_id,),
                )
                row = await cursor.fetchone()
                turn_index = row["next_turn"]
            content_str = json.dumps(content, ensure_ascii=False) if isinstance(content, (dict, list)) else content
            file_ref_json = json.dumps(file_ref) if file_ref else None
            cursor = await db.execute(
                """INSERT INTO messages (chat_id, role, content, profile_id, plan_id, model_id, file_ref, turn_index)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (chat_id, role, content_str, profile_id, plan_id, model_id, file_ref_json, turn_index),
            )
            cursor = await db.execute("SELECT * FROM messages WHERE id = ?", (cursor.lastrowid,))
            row = await cursor.fetchone()
            return MessageModel.from_row(row)

    async def update(
        self,
        message_id: int,
        chat_id: str,
        content: Any = None,
        profile_id: Optional[int] = None,
        plan_id: Optional[str] = None,
        model_id: Optional[str] = None,
        file_ref: Optional[dict] = None,
    ) -> bool:
        async with self._session() as db:
            updates = []
            params = []
            if content is not None:
                updates.append("content = ?")
                params.append(json.dumps(content, ensure_ascii=False) if isinstance(content, (dict, list)) else content)
            if profile_id is not None:
                updates.append("profile_id = ?")
                params.append(profile_id)
            if plan_id is not None:
                updates.append("plan_id = ?")
                params.append(plan_id)
            if model_id is not None:
                updates.append("model_id = ?")
                params.append(model_id)
            if file_ref is not None:
                updates.append("file_ref = ?")
                params.append(json.dumps(file_ref) if file_ref else None)
            if not updates:
                return True
            params.extend([message_id, chat_id])
            await db.execute(
                f"UPDATE messages SET {', '.join(updates)} WHERE id = ? AND chat_id = ?",
                tuple(params),
            )
            return db.total_changes > 0

    async def truncate(self, chat_id: str, from_turn_index: int) -> List[str]:
        """截断消息（事务内清理 messages / plans / tool_calls），返回需删除的磁盘文件。"""
        async with self._session() as db:
            cursor = await db.execute(
                "SELECT role, content, file_ref FROM messages WHERE chat_id = ? AND turn_index >= ?",
                (chat_id, from_turn_index),
            )
            rows = await cursor.fetchall()
            disk_files: List[str] = []
            call_ids: List[str] = []
            for row in rows:
                if row["file_ref"]:
                    # 上传文件 URL 已在文件引用中，留给上层按 uploads 删除（此处仅收集工具文件）
                    pass
                if row["role"] == "assistant" and row["content"]:
                    call_ids.extend(_extract_call_ids_from_content(row["content"]))

            unique_call_ids = list(set(call_ids))
            tool_files = []
            if unique_call_ids:
                placeholders = ",".join(["?"] * len(unique_call_ids))
                cursor = await db.execute(
                    f"SELECT meta_data FROM tool_calls WHERE call_id IN ({placeholders})",
                    unique_call_ids,
                )
                meta_rows = await cursor.fetchall()
                tool_files = _collect_tool_disk_files([r["meta_data"] for r in meta_rows])

            await db.execute(
                "DELETE FROM messages WHERE chat_id = ? AND turn_index >= ?",
                (chat_id, from_turn_index),
            )
            await db.execute(
                """
                DELETE FROM plans
                WHERE chat_id = ?
                AND plan_id NOT IN (
                    SELECT plan_id FROM messages WHERE chat_id = ? AND plan_id IS NOT NULL
                )
                """,
                (chat_id, chat_id),
            )
            if unique_call_ids:
                await db.execute(
                    f"DELETE FROM tool_calls WHERE call_id IN ({placeholders})",
                    unique_call_ids,
                )
        return tool_files

    async def delete_one(self, chat_id: str, turn_index: int) -> List[str]:
        """精准删除单轮消息，返回需删除的磁盘文件。"""
        async with self._session() as db:
            cursor = await db.execute(
                "SELECT role, content, file_ref FROM messages WHERE chat_id = ? AND turn_index = ?",
                (chat_id, turn_index),
            )
            row = await cursor.fetchone()
            call_ids: List[str] = []
            if row and row["role"] == "assistant" and row["content"]:
                call_ids.extend(_extract_call_ids_from_content(row["content"]))
            unique_call_ids = list(set(call_ids))
            tool_files = []
            if unique_call_ids:
                placeholders = ",".join(["?"] * len(unique_call_ids))
                cursor = await db.execute(
                    f"SELECT meta_data FROM tool_calls WHERE call_id IN ({placeholders})",
                    unique_call_ids,
                )
                meta_rows = await cursor.fetchall()
                tool_files = _collect_tool_disk_files([r["meta_data"] for r in meta_rows])

            await db.execute(
                "DELETE FROM messages WHERE chat_id = ? AND turn_index = ?",
                (chat_id, turn_index),
            )
            await db.execute(
                """
                DELETE FROM plans
                WHERE chat_id = ?
                AND plan_id NOT IN (
                    SELECT plan_id FROM messages WHERE chat_id = ? AND plan_id IS NOT NULL
                )
                """,
                (chat_id, chat_id),
            )
            if unique_call_ids:
                await db.execute(
                    f"DELETE FROM tool_calls WHERE call_id IN ({placeholders})",
                    unique_call_ids,
                )
        return tool_files
