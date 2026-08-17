# src/lumneo/runtime/tools/system/writer.py
# 文件写入工具（原 backend/system_tools/writer.py）。
#
# 路径校验统一走 Infrastructure 的 path_guard（§39 / §60）。
import asyncio
import os
import tempfile
from pathlib import Path
from typing import Any, Dict, Optional

from lumneo.infrastructure.filesystem.path_guard import resolve_safe_path

MAX_FILE_SIZE = 100 * 1024 * 1024  # 100 MB


async def file_write(
    path: str,
    content: str,
    encoding: Optional[str] = "UTF-8",
    overwrite: bool = True,
    create_dirs: bool = True,
) -> Dict[str, Any]:
    """将文本内容写入指定路径的文件（全量覆盖或追加）。"""
    return await _write_impl(
        path=path, content=content, encoding=encoding, overwrite=overwrite,
        create_dirs=create_dirs, offset=None, truncate_after=True,
    )


async def file_patch(
    path: str,
    search: str,
    replace: str,
    replace_all: bool = False,
    encoding: Optional[str] = "UTF-8",
    dry_run: bool = False,
) -> Dict[str, Any]:
    enc = encoding or "utf-8"
    safe_path, err = resolve_safe_path(path)
    if err:
        return {"success": False, "error": f"路径校验失败：{err}"}
    return await asyncio.to_thread(_do_patch, safe_path, search, replace, replace_all, enc, dry_run)


async def _write_impl(
    path: str, content: str, encoding: Optional[str], overwrite: bool,
    create_dirs: bool, offset: Optional[int], truncate_after: bool,
) -> Dict[str, Any]:
    enc = encoding or "utf-8"
    safe_path, err = resolve_safe_path(path)
    if err:
        return {"success": False, "error": f"路径校验失败：{err}"}
    if safe_path.exists() and safe_path.is_dir():
        return {"success": False, "error": f"目标路径是一个目录，无法写入：{safe_path}"}
    return await asyncio.to_thread(
        _write_sync, safe_path=safe_path, content=content, enc=enc,
        overwrite=overwrite, create_dirs=create_dirs, offset=offset, truncate_after=truncate_after,
    )


def _do_patch(safe_path: Path, search: str, replace: str, replace_all: bool,
              enc: str, dry_run: bool = False) -> Dict[str, Any]:
    if not safe_path.exists():
        return {"success": False, "error": f"文件不存在，无法应用补丁：{safe_path}"}
    if safe_path.is_dir():
        return {"success": False, "error": f"目标路径是一个目录，无法作为文件修改：{safe_path}"}
    if not search:
        return {"success": False, "error": "`search` 不能为空字符串"}

    try:
        old_content = safe_path.read_text(encoding=enc)
    except Exception as e:
        return {"success": False, "error": f"读取原文件失败：{e}"}

    occurrences = old_content.count(search)
    if occurrences == 0:
        stripped_search = search.strip()
        stripped_occurrences = old_content.count(stripped_search)
        if stripped_occurrences > 0:
            return {
                "success": False,
                "error": "未找到严格匹配的 `search` 代码块，但发现去除首尾空白后有匹配。请确保缩进和换行符与原文件完全一致。",
            }
    if occurrences == 0:
        return {"success": False, "error": "未在文件中找到匹配的 `search` 代码块。请确保空格、缩进和换行符与原文件完全一致。"}
    if occurrences > 1 and not replace_all:
        return {"success": False, "error": f"在文件中找到了 {occurrences} 处匹配的 `search` 代码块。请提供更丰富的上下文代码以确保修改的唯一性。"}

    new_content = old_content.replace(search, replace)
    if dry_run:
        return {
            "success": True, "dry_run": True,
            "message": "预览成功，未实际写入文件。",
            "preview_diff": f"--- Original\n+++ Patched\n{new_content}",
        }

    write_res = _write_sync(
        safe_path=safe_path, content=new_content, enc=enc,
        overwrite=True, create_dirs=False, offset=None, truncate_after=True,
    )
    if write_res.get("success"):
        idx = new_content.find(replace)
        if idx != -1:
            lines_before = new_content[:idx].count("\n")
            all_lines = new_content.splitlines()
            start_line = max(0, lines_before - 3)
            end_line = min(len(all_lines), lines_before + replace.count("\n") + 3)
            snippet = "\n".join(all_lines[start_line:end_line])
            write_res["context_snippet"] = snippet
            write_res["modified_at_line"] = lines_before + 1
    return write_res


def _write_sync(safe_path: Path, content: str, enc: str, overwrite: bool,
                create_dirs: bool, offset: Optional[int], truncate_after: bool) -> Dict[str, Any]:
    try:
        content_bytes = content.encode(enc)
    except UnicodeEncodeError:
        return {"success": False, "error": f"内容无法使用 {enc} 编码，请指定其他编码。"}

    if len(content_bytes) > MAX_FILE_SIZE:
        return {"success": False, "error": f"内容大小（{len(content_bytes)} 字节）超过限制（{MAX_FILE_SIZE} 字节）"}

    if create_dirs:
        try:
            safe_path.parent.mkdir(parents=True, exist_ok=True)
        except PermissionError:
            return {"success": False, "error": f"没有权限创建父目录：{safe_path.parent}"}
        except OSError as e:
            return {"success": False, "error": f"创建父目录失败：{e}"}

    try:
        if safe_path.exists() and not overwrite:
            with open(safe_path, "a", encoding=enc) as f:
                f.write(content)
            return _ok(safe_path, enc, len(content_bytes))

        if offset is None:
            _atomic_write(safe_path, content, enc)
            return _ok(safe_path, enc, len(content_bytes))

        if offset < 0:
            return {"success": False, "error": "偏移量不能为负数"}

        if not safe_path.exists():
            safe_path.touch()

        with open(safe_path, "r+b") as f:
            f.seek(offset)
            f.write(content_bytes)
            if truncate_after:
                f.truncate()
        return _ok(safe_path, enc, len(content_bytes))

    except PermissionError:
        return {"success": False, "error": f"没有写入权限：{safe_path}"}
    except Exception as e:
        return {"success": False, "error": f"写入文件时发生未知错误：{e}"}


def _ok(safe_path: Path, enc: str, n: int) -> Dict[str, Any]:
    return {"success": True, "path": str(safe_path), "bytes_written": n, "encoding": enc}


def _atomic_write(path: Path, content: str, enc: str) -> None:
    tmp_fd, tmp_path = tempfile.mkstemp(dir=str(path.parent), prefix=f".{path.name}.", suffix=".tmp")
    try:
        with os.fdopen(tmp_fd, "w", encoding=enc) as f:
            f.write(content)
            f.flush()
            os.fsync(f.fileno())
        if path.exists():
            os.chmod(tmp_path, path.stat().st_mode)
        os.replace(tmp_path, str(path))
    except Exception:
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)
        raise
