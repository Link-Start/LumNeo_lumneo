# backend/system_tools/delete.py
import asyncio
from pathlib import Path
from typing import Any, Dict
from backend.utils.base import _validate


async def file_delete(path: str, force: bool = False) -> Dict[str, Any]:
    """
    删除指定路径的文件。

    该工具安全地删除位于允许写入目录内的文件，支持强制忽略不存在的文件。

    Args:
        path:  目标文件路径（相对或绝对路径），需位于 backend.workspace_path 配置的目录内。
        force: 若为 True，当文件不存在时不会报错，返回成功状态；默认为 False。

    Returns:
        Dict[str, Any]: 包含以下字段：
            - success: bool，操作是否成功。
            - path: str，被操作文件的绝对路径（如有）。
            - error: str，失败时的错误信息（仅失败时存在）。
            - message: str，成功或忽略时的描述信息。
    """
    safe_path, err = _validate(path)
    if err:
        return {"success": False, "error": f"路径校验失败：{err}"}

    # 文件不存在时的处理
    if not safe_path.exists():
        if force:
            return {"success": True, "path": str(safe_path), "message": "文件不存在，已忽略"}
        else:
            return {"success": False, "error": f"文件不存在：{safe_path}"}

    # 检查是否为目录
    if safe_path.is_dir():
        return {"success": False, "error": f"目标路径是一个目录，无法删除：{safe_path}"}

    # 执行删除（阻塞 I/O 放入线程池）
    try:
        await asyncio.to_thread(_delete_sync, safe_path)
        return {"success": True, "path": str(safe_path), "message": "文件删除成功"}
    except PermissionError:
        return {"success": False, "error": f"没有删除权限：{safe_path}"}
    except Exception as e:
        return {"success": False, "error": f"删除文件时发生未知错误：{e}"}


# ──────────────────────── 内部实现 ────────────────────────

def _delete_sync(path: Path) -> None:
    """同步删除文件（用于在线程池中调用）。"""
    path.unlink()