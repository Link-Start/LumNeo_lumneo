# src/lumneo/persistence/repositories/conversation_repository.py
# Persistence —— Repository Implementation（§24 / §79）。
#
# 实现 conversation/ports 的 ConversationRepository。只负责数据库访问（CRUD / 查询），
# 不负责文件 I/O：删除对话时，仅返回需要清理的磁盘路径，由上层（Service + Infrastructure）
# 执行真正的文件删除（§39 / §60：文件 I/O 属于 Infrastructure）。
import json
import os
import uuid
from datetime import datetime
from typing import List, Optional

from lumneo.conversation.ports.conversation_repository import ConversationRepository
from lumneo.persistence.database import Database
from lumneo.persistence.models.chat import ChatModel
from lumneo.persistence.repositories._base import BaseRepository
from lumneo.kernel.config.app_config import config


def _extract_uploaded_paths(file_ref_json: Optional[str]) -> List[str]:
    """从 file_ref JSON 中提取需要删除的上传文件绝对路径（不执行 I/O）。"""
    if not file_ref_json:
        return []
    try:
        ref_data = json.loads(file_ref_json)
    except Exception:
        return []
    if isinstance(ref_data, dict):
        ref_data = [ref_data]
    paths = []
    for item in ref_data:
        url = item.get("url") if isinstance(item, dict) else None
        if not url:
            continue
        if "/uploads/" in url:
            filename = url.split("/uploads/")[-1]
            phys = os.path.join(str(config.uploads_dir), filename)
            paths.append(phys)
    return paths


class SQLConversationRepository(ConversationRepository, BaseRepository):
    """ConversationRepository 的 SQLite 实现。"""

    def __init__(self, database: Database):
        BaseRepository.__init__(self, database)

    async def create(self, title: str = "新对话") -> ChatModel:
        async with self._session() as db:
            chat_id = str(uuid.uuid4())
            now = datetime.now().isoformat()
            await db.execute(
                "INSERT INTO chats (id, title, created_at) VALUES (?, ?, ?)",
                (chat_id, title, now),
            )
            return ChatModel(id=chat_id, title=title, created_at=now)

    async def list(self) -> List[ChatModel]:
        async with self._session() as db:
            cursor = await db.execute(
                "SELECT id, title, created_at FROM chats ORDER BY created_at DESC"
            )
            rows = await cursor.fetchall()
            return [ChatModel.from_row(row) for row in rows]

    async def update_title(self, chat_id: str, title: str) -> None:
        async with self._session() as db:
            await db.execute("UPDATE chats SET title = ? WHERE id = ?", (title, chat_id))

    async def get(self, chat_id: str) -> Optional[ChatModel]:
        async with self._session() as db:
            cursor = await db.execute(
                "SELECT id, title, created_at FROM chats WHERE id = ?", (chat_id,)
            )
            row = await cursor.fetchone()
            return ChatModel.from_row(row) if row else None

    async def delete(self, chat_id: str) -> List[str]:
        """删除对话，返回需要清理磁盘的路径（上传文件 + 工具目录）。"""
        async with self._session() as db:
            # 1. 取出关联上传文件引用，便于删除物理文件
            cursor = await db.execute(
                "SELECT file_ref FROM messages WHERE chat_id = ?", (chat_id,)
            )
            msg_rows = await cursor.fetchall()
            file_paths: List[str] = []
            for row in msg_rows:
                file_paths.extend(_extract_uploaded_paths(row["file_ref"]))

            # 2. 触发数据库级联删除（messages / tool_calls 自动移除）
            await db.execute("DELETE FROM chats WHERE id = ?", (chat_id,))

        # 3. 工具关联目录（绝对路径，交给 Infrastructure 删除）
        tool_dir = os.path.join(str(config.cache_dir), chat_id)
        file_paths.append(f"dir::{tool_dir}")
        return file_paths
