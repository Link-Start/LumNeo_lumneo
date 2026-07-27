# backend/system_tools/writer.py
import asyncio
import os
import tempfile
from pathlib import Path
from typing import Any, Dict, Optional
from backend.utils.base import _validate

# 最大允许写入的文件大小，防止误写超大内容撑爆磁盘
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
        path=path,
        content=content,
        encoding=encoding,
        overwrite=overwrite,
        create_dirs=create_dirs,
        offset=None,
        truncate_after=True,
    )


async def file_patch(
    path: str,
    search: str,
    replace: str,
    replace_all: bool = False,
    encoding: Optional[str] = "UTF-8",
    dry_run: bool = False
) -> Dict[str, Any]:
    """
    基于 Search-and-Replace（查找与替换）逻辑，对指定文件进行局部的精准修改、插入或删除。

    该工具专门适配 AI 编程场景，通过严格的唯一性校验防止代码被错误覆盖。它会：
    - 安全校验路径并读取目标文件。
    - 检查文件中 `search` 代码块的数量。若未找到或存在多处匹配，则拒绝操作并返回错误。
    - 精准替换唯一的代码块，并复用底层的安全落盘逻辑。

    💡 操作指南：
    - 【修改代码】：在 search 填入旧代码，replace 填入新代码。
    - 【插入代码】：本函数不支持基于行号或空 search 插入。请将 search 作为"锚点"上下文，
      在 replace 中填入 "原代码 + 新代码"（即追加）或 "新代码 + 原代码"（即前置）。
    - 【删除代码】：在 search 填入要删除的代码，replace 填入空字符串。

    Args:
        path:        目标文件路径（相对或绝对路径）。
        search:      作为定位锚点的原有代码块（必须在文件中严格匹配且唯一存在）。
        replace:     准备替换进去的新代码块。
        replace_all: 是否允许批量替换多处匹配项。默认为 False。
        encoding:    文件编码，默认为 UTF-8。
        dry_run:     若为 True，仅进行校验和匹配测试，不实际修改文件。默认为 False。

    Returns:
        包含 success、path、bytes_written 等状态的字典。
    """
    enc = encoding or "utf-8"

    # 1. 路径校验（只做一次）
    safe_path, err = _validate(path)
    if err:
        return {"success": False, "error": f"路径校验失败：{err}"}

    # 2. 将「读取 + 替换 + 写入」放在同一个线程中执行，消除 TOCTOU 竞态
    return await asyncio.to_thread(_do_patch, safe_path, search, replace, replace_all, enc, dry_run)


# ──────────────────────── 内部实现 ────────────────────────

async def _write_impl(
    path: str,
    content: str,
    encoding: Optional[str],
    overwrite: bool,
    create_dirs: bool,
    offset: Optional[int],
    truncate_after: bool,
) -> Dict[str, Any]:
    """内部统一实现，供 file_write、file_modify 和 file_patch 调用。"""
    enc = encoding or "utf-8"

    safe_path, err = _validate(path)
    if err:
        return {"success": False, "error": f"路径校验失败：{err}"}

    if safe_path.exists() and safe_path.is_dir():
        return {"success": False, "error": f"目标路径是一个目录，无法写入：{safe_path}"}

    # 阻塞 I/O 交给线程池，不卡事件循环
    return await asyncio.to_thread(
        _write_sync,
        safe_path=safe_path,
        content=content,
        enc=enc,
        overwrite=overwrite,
        create_dirs=create_dirs,
        offset=offset,
        truncate_after=truncate_after,
    )

def _do_patch(
    safe_path: Path,
    search: str,
    replace: str,
    replace_all: bool,
    enc: str,
    dry_run: bool = False,
) -> Dict[str, Any]:
    """file_patch 的同步核心逻辑（在线程池中执行）。"""
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
    
    # 【微调】：对大模型常见的尾部换行符差异进行一次宽容尝试
    if occurrences == 0:
        # 尝试去除两端空字符再匹配
        stripped_search = search.strip()
        stripped_occurrences = old_content.count(stripped_search)
        if stripped_occurrences > 0:
            # 提示大模型注意空格
            return {
                "success": False,
                "error": "未找到严格匹配的 `search` 代码块，但发现去除首尾空白后有匹配。请确保缩进和换行符与原文件完全一致。"
            }

    if occurrences == 0:
        return {"success": False, "error": "未在文件中找到匹配的 `search` 代码块。请确保空格、缩进和换行符与原文件完全一致。"}
    if occurrences > 1 and not replace_all:
        return {"success": False, "error": f"在文件中找到了 {occurrences} 处匹配的 `search` 代码块。请提供更丰富的上下文代码以确保修改的唯一性。"}

    new_content = old_content.replace(search, replace)
    
    # 支持预览模式
    if dry_run:
        return {
            "success": True,
            "dry_run": True,
            "message": "预览成功，未实际写入文件。",
            "preview_diff": f"--- Original\n+++ Patched\n{new_content}" # 简单示意，真实场景可生成 unified diff
        }

    # 正式写入
    write_res = _write_sync(
        safe_path=safe_path, content=new_content, enc=enc,
        overwrite=True, create_dirs=False, offset=None, truncate_after=True,
    )
    
    # 成功后返回修改处的上下文，避免大模型再次调用 read_file
    if write_res.get("success"):
        # 找到替换发生的位置，截取前后 3 行作为上下文
        idx = new_content.find(replace)
        if idx != -1:
            lines_before = new_content[:idx].count('\n')
            all_lines = new_content.splitlines()
            start_line = max(0, lines_before - 3)
            end_line = min(len(all_lines), lines_before + replace.count('\n') + 3)
            snippet = "\n".join(all_lines[start_line:end_line])
            write_res["context_snippet"] = snippet
            write_res["modified_at_line"] = lines_before + 1

    return write_res



def _write_sync(
    safe_path: Path,
    content: str,
    enc: str,
    overwrite: bool,
    create_dirs: bool,
    offset: Optional[int],
    truncate_after: bool,
) -> Dict[str, Any]:
    """同步写入实现（在线程池中调用）。"""
    # 编码 + 大小检查（提前失败）
    try:
        content_bytes = content.encode(enc)
    except UnicodeEncodeError:
        return {"success": False, "error": f"内容无法使用 {enc} 编码，请指定其他编码。"}

    if len(content_bytes) > MAX_FILE_SIZE:
        return {
            "success": False,
            "error": f"内容大小（{len(content_bytes)} 字节）超过限制（{MAX_FILE_SIZE} 字节）",
        }

    # 创建父目录
    if create_dirs:
        try:
            safe_path.parent.mkdir(parents=True, exist_ok=True)
        except PermissionError:
            return {"success": False, "error": f"没有权限创建父目录：{safe_path.parent}"}
        except OSError as e:
            return {"success": False, "error": f"创建父目录失败：{e}"}

    try:
        # ── 追加模式 ──
        if safe_path.exists() and not overwrite:
            with open(safe_path, "a", encoding=enc) as f:
                f.write(content)
            return _ok(safe_path, enc, len(content_bytes))

        # ── 全量覆盖（无偏移）—— 原子写入 ──
        if offset is None:
            _atomic_write(safe_path, content, enc)
            return _ok(safe_path, enc, len(content_bytes))

        # ── 偏移量修改模式 ──
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


# ──────────────────────── 工具函数 ────────────────────────

def _ok(safe_path: Path, enc: str, n: int) -> Dict[str, Any]:
    """构造成功返回值。"""
    return {"success": True, "path": str(safe_path), "bytes_written": n, "encoding": enc}


def _atomic_write(path: Path, content: str, enc: str) -> None:
    """
    原子写入：先写到同目录临时文件，fsync 后再 rename 覆盖原文件。
    保证写入中途崩溃不会损坏原文件。
    """
    tmp_fd, tmp_path = tempfile.mkstemp(
        dir=str(path.parent),
        prefix=f".{path.name}.",
        suffix=".tmp",
    )
    try:
        with os.fdopen(tmp_fd, "w", encoding=enc) as f:
            f.write(content)
            f.flush()
            os.fsync(f.fileno())
        # 保留原文件权限（如果原文件存在）
        if path.exists():
            os.chmod(tmp_path, path.stat().st_mode)
        os.replace(tmp_path, str(path))
    except Exception:
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)
        raise
