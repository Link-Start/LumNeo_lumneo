# runtime/tools/system/lister.py
# 文件列表工具（原 backend/system_tools/lister.py）。
#
# 路径校验统一走 Infrastructure 的 path_guard（§39 / §60）。
import os
import asyncio
import fnmatch
import datetime
from typing import Optional, List, Tuple, Set
from pathlib import Path

from lumneo.kernel.config.app_config import config
from lumneo.infrastructure.filesystem.path_guard import validate_path, default_allowed_dirs
from lumneo import workspace_path


class FileReadError(Exception):
    pass


async def read_file_list(
    path: str,
    show_hidden: bool = False,
    exclude_patterns: Optional[List[str]] = None,
    follow_symlinks: bool = False,
    max_files: int = 500,
    max_depth: int = 10,
    detailed: bool = False,
) -> str:
    allowed_dirs = [Path(p) for p in [config.uploads_dir, workspace_path]]
    try:
        safe_path = validate_path(path, allowed_dirs)
    except ValueError as e:
        raise FileReadError(f"路径校验失败：{e}") from e

    if not safe_path.exists():
        raise FileReadError(f"路径不存在：{safe_path}")
    if not safe_path.is_dir():
        raise FileReadError(f"路径不是目录：{safe_path}")

    loop = asyncio.get_running_loop()

    def _parse_gitignore(root_dir: Path) -> List[str]:
        gitignore_path = root_dir / ".gitignore"
        if not gitignore_path.exists():
            return []
        patterns = []
        try:
            with open(gitignore_path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith("#"):
                        continue
                    pattern = line.lstrip("/")
                    if pattern.startswith("./"):
                        pattern = pattern[2:]
                    patterns.append(pattern)
        except OSError:
            pass
        return patterns

    def _should_exclude(rel_path: str, is_dir: bool, patterns: Set[str]) -> bool:
        if not patterns:
            return False
        rel_path_norm = rel_path.replace(os.sep, "/")
        parts = rel_path_norm.split("/")
        for pattern in patterns:
            p = pattern.rstrip("/")
            if not p:
                continue
            if "/" not in p:
                if any(fnmatch.fnmatch(part, p) for part in parts):
                    return True
            else:
                if fnmatch.fnmatch(rel_path_norm, p):
                    return True
                if pattern.endswith("/") and rel_path_norm == p and is_dir:
                    return True
        return False

    def _collect_files(current_abs, rel_prefix, exclude_set, current_depth, files_info):
        if len(files_info) >= max_files or current_depth > max_depth:
            return
        try:
            with os.scandir(current_abs) as it:
                for entry in it:
                    if len(files_info) >= max_files:
                        return
                    entry_rel_path = os.path.join(rel_prefix, entry.name) if rel_prefix else entry.name
                    if not show_hidden and entry.name.startswith(".") and entry.name != ".gitignore":
                        continue
                    if _should_exclude(entry_rel_path, entry.is_dir(follow_symlinks=False), exclude_set):
                        continue
                    if entry.is_dir(follow_symlinks=follow_symlinks):
                        if not entry.is_symlink() or follow_symlinks:
                            _collect_files(Path(entry.path), entry_rel_path, exclude_set, current_depth + 1, files_info)
                        continue
                    try:
                        stat = entry.stat(follow_symlinks=True)
                        files_info.append((entry_rel_path, stat.st_size, stat.st_mtime))
                    except OSError:
                        continue
        except OSError:
            pass

    def _sync_list() -> str:
        gitignore_patterns = _parse_gitignore(safe_path)
        all_patterns = set(gitignore_patterns)
        if exclude_patterns:
            all_patterns.update(exclude_patterns)

        files_info: List[Tuple[str, int, float]] = []
        _collect_files(safe_path, "", all_patterns, 0, files_info)
        files_info.sort(key=lambda x: x[0])

        lines = [f"Directory: {safe_path.resolve()}", ""]
        if not files_info:
            lines.append("(empty)")
            return "\n".join(lines)

        for rel_path, size, mtime in files_info:
            if detailed:
                if size < 1024:
                    size_str = f"{size}B"
                elif size < 1024 ** 2:
                    size_str = f"{size / 1024:.1f}KB"
                elif size < 1024 ** 3:
                    size_str = f"{size / 1024 ** 2:.1f}MB"
                else:
                    size_str = f"{size / 1024 ** 3:.1f}GB"
                time_str = datetime.datetime.fromtimestamp(mtime).strftime("%Y-%m-%d %H:%M")
                lines.append(f"{rel_path} | {size_str} | {time_str}")
            else:
                lines.append(rel_path)

        if len(files_info) >= max_files:
            lines.append(f"\n(Truncated: Reached max_files limit of {max_files}. Try using exclude_patterns or a more specific path.)")
        return "\n".join(lines)

    return await loop.run_in_executor(None, _sync_list)
