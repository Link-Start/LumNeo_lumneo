# backend/system_tools/lister.py
import os
import asyncio
import fnmatch
import datetime
from typing import Optional, List, Tuple, Set
from pathlib import Path
from config_loader import config
from backend.utils.validators import validate_path
import backend


class FileReadError(Exception):
    """
    文件读取过程中出现的错误，将被 MCP 框架转为 isError 响应。
    """
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
    """
    递归列出目录下的所有文件，自动应用 .gitignore 规则。

    Args:
        path: 要列出的目录路径。
        show_hidden: 是否显示以点开头的隐藏文件/目录，默认 False。
        exclude_patterns: 额外的排除模式列表（通配符），与 .gitignore 规则合并。
        follow_symlinks: 是否跟随目录类型的符号链接，默认 False。
        max_files: 返回的最大文件数量（防止 LLM 上下文溢出）。默认 500。
        max_depth: 递归的最大深度，防止无限循环。默认 10。
        detailed: 是否返回详细信息的开关。默认 False，仅返回相对路径以节省 Token。
                  若为 True，返回 "path | size | modified_time" 格式。

    Returns:
        格式化后的文件列表字符串。

    Raises:
        FileReadError: 当路径校验失败、路径不存在、不是目录或发生其他错误时。
    """
    paths = [config.uploads_dir, backend.workspace_path]
    allowed_dirs = [Path(p).resolve() for p in paths]

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
        # 将路径拆分为各级目录名和文件名，用于无斜杠模式匹配
        parts = rel_path_norm.split('/')

        for pattern in patterns:
            p = pattern.rstrip('/')
            if not p:
                continue
                
            # 如果模式不含斜杠，匹配路径中的任意层级 (如 node_modules, *.log)
            if '/' not in p:
                if any(fnmatch.fnmatch(part, p) for part in parts):
                    return True
            else:
                # 锚定到根目录的模式 (如 /docs/*.md 或 docs/*.md)
                if fnmatch.fnmatch(rel_path_norm, p):
                    return True
                # 如果模式以 / 结尾，只匹配目录本身
                if pattern.endswith('/') and rel_path_norm == p and is_dir:
                    return True
        return False

    def _collect_files(
        current_abs: Path,
        rel_prefix: str,
        exclude_set: Set[str],
        current_depth: int,
        files_info: List[Tuple[str, int, float]]
    ) -> None:
        """同步递归遍历目录，收集文件信息。通过引用传递 files_info 以便提前截断。"""
        if len(files_info) >= max_files or current_depth > max_depth:
            return

        try:
            with os.scandir(current_abs) as it:
                for entry in it:
                    if len(files_info) >= max_files:
                        return

                    entry_rel_path = os.path.join(rel_prefix, entry.name) if rel_prefix else entry.name

                    if not show_hidden and entry.name.startswith('.') and entry.name != ".gitignore":
                        continue

                    if _should_exclude(entry_rel_path, entry.is_dir(follow_symlinks=False), exclude_set):
                        continue

                    if entry.is_dir(follow_symlinks=follow_symlinks):
                        # 只有在允许跟随符号链接，或者它不是符号链接时才递归
                        if not entry.is_symlink() or follow_symlinks:
                            _collect_files(
                                Path(entry.path),
                                entry_rel_path,
                                exclude_set,
                                current_depth + 1,
                                files_info
                            )
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
                # 默认只返回路径，极致节省 Token
                lines.append(rel_path)

        if len(files_info) >= max_files:
            lines.append(f"\n(Truncated: Reached max_files limit of {max_files}. Try using exclude_patterns or a more specific path.)")

        return "\n".join(lines)

    return await loop.run_in_executor(None, _sync_list)
