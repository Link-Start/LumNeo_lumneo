# runtime/tools/system/delete.py
# 文件删除工具（原 backend/system_tools/delete.py）。
#
# 路径校验统一走 Infrastructure 的 path_guard（§39 / §60）。
import asyncio
from pathlib import Path
from typing import Any, Dict

from lumneo.infrastructure.filesystem.path_guard import resolve_safe_path


async def file_delete(path: str, force: bool = False) -> Dict[str, Any]:
    """删除指定路径的文件（位于允许目录内）。"""
    safe_path, err = resolve_safe_path(path)
    if err:
        return {"success": False, "error": f"路径校验失败：{err}"}

    if not safe_path.exists():
        if force:
            return {"success": True, "path": str(safe_path), "message": "文件不存在，已忽略"}
        return {"success": False, "error": f"文件不存在：{safe_path}"}

    if safe_path.is_dir():
        return {"success": False, "error": f"目标路径是一个目录，无法删除：{safe_path}"}

    try:
        await asyncio.to_thread(_delete_sync, safe_path)
        return {"success": True, "path": str(safe_path), "message": "文件删除成功"}
    except PermissionError:
        return {"success": False, "error": f"没有删除权限：{safe_path}"}
    except Exception as e:
        return {"success": False, "error": f"删除文件时发生未知错误：{e}"}


def _delete_sync(path: Path) -> None:
    path.unlink()
