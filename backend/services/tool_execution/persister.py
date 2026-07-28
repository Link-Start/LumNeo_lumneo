import os
from typing import Optional, Dict, Tuple
from config_loader import config


class ToolPersister:
    def __init__(self, tool_call_repo):
        self.repo = tool_call_repo

    async def persist_tool_result(
        self,
        chat_id: Optional[str],
        call_id: str,
        args: Dict,
        result_str: str,
        failed: bool,
        exec_time_ms: int,
        error_message: Optional[str] = None
    ):
        """将工具结果写入数据库，超长结果存文件"""
        if not chat_id:
            return

        # 准备存储
        db_result, meta_data = self._prepare_db_result(result_str, chat_id, call_id)
        status = "error" if failed else "success"
        await self.repo.update_full(
            call_id=call_id,
            arguments=args,
            result=db_result,
            status=status,
            execution_time=exec_time_ms,
            error_message=error_message if failed else None,
            meta_data=meta_data
        )

    @staticmethod
    def _prepare_db_result(result_str: str, chat_id: Optional[str], call_id: str) -> Tuple[str, Dict]:
        MAX_DB_LEN = 20000
        if len(result_str) > MAX_DB_LEN:
            file_dir = f"{chat_id}/{call_id}.txt" if chat_id else f"unknown/{call_id}.txt"
            file_path = os.path.join(config.cache_dir, file_dir)
            os.makedirs(os.path.dirname(file_path), exist_ok=True)
            with open(file_path, "w", encoding="utf-8") as f:
                f.write(result_str)
            meta = {
                "storage_type": "file",
                "file_path": file_dir,
                "size": len(result_str),
                "preview": result_str[:1000]
            }
            return f"[数据量过大(共{len(result_str)}字)，完整内容已保存至本地文件]", meta
        return result_str, {}