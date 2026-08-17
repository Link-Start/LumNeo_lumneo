# runtime/tools/execution/persister.py
# 工具结果持久化（原 backend/services/tool_execution/persister.py）。
#
# 通过注入的 ToolCallRepository Port 落库；超长结果委托 Infrastructure 的
# StoragePort 写入本地缓存文件，避免把“文件 I/O”耦合进执行逻辑（§39 / §60）。
from typing import Dict, Optional, Tuple

from lumneo.conversation.ports.tool_call_repository import ToolCallRepository
from lumneo.infrastructure.filesystem.local_storage import LocalFileStorage
from lumneo.infrastructure.filesystem.storage_port import StoragePort


class ToolPersister:
    def __init__(self, tool_call_repo: ToolCallRepository, storage: Optional[StoragePort] = None):
        self.repo = tool_call_repo
        self.storage = storage or LocalFileStorage()

    async def persist_tool_result(
        self,
        chat_id: Optional[str],
        call_id: str,
        args: Dict,
        result_str: str,
        failed: bool,
        exec_time_ms: int,
        error_message: Optional[str] = None,
    ):
        """将工具结果写入数据库，超长结果存文件（由 Storage 执行实际 I/O）。"""
        if not chat_id:
            return

        db_result, meta_data = self._prepare_db_result(result_str, chat_id, call_id)
        status = "error" if failed else "success"
        await self.repo.update_full(
            call_id=call_id,
            arguments=args,
            result=db_result,
            status=status,
            execution_time=exec_time_ms,
            error_message=error_message if failed else None,
            meta_data=meta_data,
        )

    def _prepare_db_result(self, result_str: str, chat_id: Optional[str], call_id: str) -> Tuple[str, Dict]:
        MAX_DB_LEN = 20000
        if len(result_str) > MAX_DB_LEN:
            rel = f"{chat_id}/{call_id}.txt" if chat_id else f"unknown/{call_id}.txt"
            self.storage.store_large_text(rel, result_str)
            meta = {
                "storage_type": "file",
                "file_path": rel,
                "size": len(result_str),
                "preview": result_str[:1000],
            }
            return f"[数据量过大(共{len(result_str)}字)，完整内容已保存至本地文件]", meta
        return result_str, {}
