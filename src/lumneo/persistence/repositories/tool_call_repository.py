# persistence/repositories/tool_call_repository.py
# Persistence —— Repository Implementation（§24 / §79）。
import json
import os
from typing import Dict, List, Optional

from lumneo.conversation.ports.tool_call_repository import ToolCallRepository
from lumneo.persistence.database import Database
from lumneo.persistence.models.tool_call import ToolCallModel
from lumneo.persistence.repositories._base import BaseRepository
from lumneo.kernel.config.app_config import config
from lumneo.kernel.common.logger import logger


class SQLToolCallRepository(ToolCallRepository, BaseRepository):
    """ToolCallRepository 的 SQLite 实现。"""

    def __init__(self, database: Database):
        BaseRepository.__init__(self, database)

    @staticmethod
    def _disk_files_from_meta_rows(meta_rows: List[dict]) -> List[str]:
        files = []
        for meta in meta_rows:
            if not meta:
                continue
            try:
                meta_data = json.loads(meta) if isinstance(meta, str) else meta
            except Exception:
                continue
            if meta_data.get("storage_type") == "file":
                file_path = meta_data.get("file_path")
                if file_path:
                    files.append(os.path.abspath(os.path.join(str(config.cache_dir), file_path)))
        return files

    async def create(self, chat_id: str, call_id: str, tool_name: str) -> ToolCallModel:
        async with self._session() as db:
            cursor = await db.execute(
                "INSERT INTO tool_calls (chat_id, call_id, tool_name, status) VALUES (?, ?, ?, 'calling')",
                (chat_id, call_id, tool_name),
            )
            cursor = await db.execute("SELECT * FROM tool_calls WHERE id = ?", (cursor.lastrowid,))
            return ToolCallModel.from_row(await cursor.fetchone())

    async def update_arguments(self, call_id: str, arguments: Dict) -> None:
        async with self._session() as db:
            await db.execute(
                "UPDATE tool_calls SET arguments = ?, updated_at = CURRENT_TIMESTAMP WHERE call_id = ?",
                (json.dumps(arguments, ensure_ascii=False), call_id),
            )

    async def update_status(self, call_id: str, status: str) -> None:
        async with self._session() as db:
            await db.execute(
                "UPDATE tool_calls SET status = ?, updated_at = CURRENT_TIMESTAMP WHERE call_id = ?",
                (status, call_id),
            )

    async def update_full(self, call_id: str, **fields) -> Optional[ToolCallModel]:
        async with self._session() as db:
            updates = []
            params = []
            if "arguments" in fields:
                updates.append("arguments = ?")
                params.append(json.dumps(fields["arguments"], ensure_ascii=False))
            if "result" in fields:
                updates.append("result = ?")
                params.append(fields["result"])
            if "status" in fields:
                updates.append("status = ?")
                params.append(fields["status"])
            if "execution_time" in fields:
                updates.append("execution_time = ?")
                params.append(fields["execution_time"])
            if "error_message" in fields:
                updates.append("error_message = ?")
                params.append(fields["error_message"])
            if "meta_data" in fields:
                updates.append("meta_data = ?")
                params.append(json.dumps(fields["meta_data"], ensure_ascii=False) if fields["meta_data"] else "{}")
            if not updates:
                return None
            updates.append("updated_at = CURRENT_TIMESTAMP")
            params.append(call_id)
            await db.execute(
                f"UPDATE tool_calls SET {', '.join(updates)} WHERE call_id = ?",
                tuple(params),
            )
            cursor = await db.execute("SELECT * FROM tool_calls WHERE call_id = ?", (call_id,))
            row = await cursor.fetchone()
            return ToolCallModel.from_row(row) if row else None

    async def get_status(self, call_id: str) -> Optional[str]:
        async with self._session() as db:
            cursor = await db.execute("SELECT status FROM tool_calls WHERE call_id = ?", (call_id,))
            row = await cursor.fetchone()
            return row["status"] if row else None

    async def get_by_id(self, call_id: str) -> Optional[ToolCallModel]:
        async with self._session() as db:
            cursor = await db.execute("SELECT * FROM tool_calls WHERE call_id = ?", (call_id,))
            row = await cursor.fetchone()
            return ToolCallModel.from_row(row) if row else None

    async def list_by_call_ids(self, call_ids: List[str]) -> List[ToolCallModel]:
        if not call_ids:
            return []
        async with self._session() as db:
            placeholders = ",".join(["?"] * len(call_ids))
            cursor = await db.execute(
                f"SELECT * FROM tool_calls WHERE call_id IN ({placeholders})", call_ids
            )
            rows = await cursor.fetchall()
            return [ToolCallModel.from_row(r) for r in rows]

    async def delete_by_call_ids(self, call_ids: List[str]) -> List[str]:
        if not call_ids:
            return []
        async with self._session() as db:
            placeholders = ",".join(["?"] * len(call_ids))
            cursor = await db.execute(
                f"SELECT meta_data FROM tool_calls WHERE call_id IN ({placeholders})", call_ids
            )
            meta_rows = await cursor.fetchall()
            files = self._disk_files_from_meta_rows([r["meta_data"] for r in meta_rows])
            await db.execute(
                f"DELETE FROM tool_calls WHERE call_id IN ({placeholders})", call_ids
            )
        return files

    async def delete_by_chat_id(self, chat_id: str) -> List[str]:
        async with self._session() as db:
            cursor = await db.execute(
                "SELECT meta_data FROM tool_calls WHERE chat_id = ?", (chat_id,)
            )
            meta_rows = await cursor.fetchall()
            files = self._disk_files_from_meta_rows([r["meta_data"] for r in meta_rows])
            await db.execute("DELETE FROM tool_calls WHERE chat_id = ?", (chat_id,))
        return files
