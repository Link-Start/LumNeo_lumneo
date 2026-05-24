# backend/system_tools/file_lister.py
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
) -> str:
    """
    递归列出目录下的所有文件（包括子目录中的文件），自动应用 .gitignore 规则。

    该工具会：
    - 根据配置文件中的 allowed_paths 白名单进行路径安全校验。
    - 检查路径是否为目录，若不是则报错。
    - 递归遍历目录和子目录，收集所有文件（不包含目录本身）。
    - 自动读取目标目录下的 .gitignore 文件，解析其中的排除规则（支持通配符 *、?，忽略注释和空行）。
    - 支持额外传入的 exclude_patterns 排除模式（与 .gitignore 规则合并）。
    - 支持是否显示隐藏文件（以 '.' 开头，.gitignore 本身例外）。
    - 支持是否跟随符号链接（默认不跟随，避免循环或逃逸）。

    Args:
        path: 要列出的目录路径。
        show_hidden: 是否显示以点开头的隐藏文件/目录，默认 False。
                     注意：若 .gitignore 明确排除隐藏文件，会优先排除。
        exclude_patterns: 额外的排除模式列表（通配符），与 .gitignore 规则合并。
        follow_symlinks: 是否跟随目录类型的符号链接，默认 False（避免潜在循环）。

    Returns:
        格式化后的文件列表字符串，每个文件一行，包含文件相对路径、大小、修改时间。

    Raises:
        FileReadError: 当路径校验失败、路径不存在、不是目录或发生其他错误时。
    """
    # 加载配置
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
        """解析根目录下的 .gitignore 文件，返回排除模式列表（已去除空行和注释）"""
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
                    # 去掉开头的 ./ 或 / 以便统一匹配相对路径
                    pattern = line.lstrip("/")
                    if pattern.startswith("./"):
                        pattern = pattern[2:]
                    # 如果模式末尾有 /，表示仅匹配目录，这里保留但匹配时需特殊处理
                    patterns.append(pattern)
        except OSError:
            # 忽略读取错误（如权限），继续执行
            pass
        return patterns

    def _should_exclude(rel_path: str, is_dir: bool, patterns: Set[str]) -> bool:
        """
        判断相对路径是否应被排除
        rel_path: 相对于根目录的路径（如 "subdir/file.txt"）
        is_dir: 是否为目录
        patterns: 排除模式集合（已合并 .gitignore 和用户定义的模式）
        """
        if not patterns:
            return False

        # 统一使用正斜杠匹配
        rel_path_norm = rel_path.replace(os.sep, "/")

        for pattern in patterns:
            # 处理目录专属模式（以 / 结尾）
            if pattern.endswith("/"):
                if not is_dir:
                    continue
                pattern = pattern[:-1]  # 去掉尾部斜杠再匹配
            # fnmatch 匹配
            if fnmatch.fnmatch(rel_path_norm, pattern):
                return True
            # 补充：匹配模式为目录下任意文件的情况，如 "*.log" 应匹配 "a/b/c.log"
            # fnmatch 已经可以处理跨目录，因为 pattern 不包含斜杠时也能匹配到带有斜杠的相对路径
        return False

    def _collect_files(
        root_abs: Path,
        current_abs: Path,
        rel_prefix: str,
        exclude_set: Set[str],
    ) -> List[Tuple[str, int, float]]:
        """
        同步递归遍历目录，收集文件信息。
        返回列表，每个元素为 (相对路径, 文件大小(字节), 修改时间戳)
        """
        results = []
        try:
            with os.scandir(current_abs) as it:
                for entry in it:
                    # 计算相对路径
                    entry_rel_path = os.path.join(rel_prefix, entry.name) if rel_prefix else entry.name

                    # 是否隐藏文件（以 . 开头），且 .gitignore 本身不因隐藏而过滤
                    if not show_hidden and entry.name.startswith('.') and entry.name != ".gitignore":
                        continue

                    # 应用排除规则（基于相对路径）
                    if _should_exclude(entry_rel_path, entry.is_dir(), exclude_set):
                        continue

                    # 处理目录
                    if entry.is_dir():
                        is_symlink_dir = entry.is_symlink() and entry.is_dir()
                        if not is_symlink_dir or follow_symlinks:
                            sub_results = _collect_files(
                                root_abs,
                                Path(entry.path),
                                entry_rel_path,
                                exclude_set
                            )
                            results.extend(sub_results)
                        # 目录本身不加入文件列表
                        continue

                    # 处理文件
                    try:
                        stat = entry.stat(follow_symlinks=True)
                        size = stat.st_size
                        mtime = stat.st_mtime
                        results.append((entry_rel_path, size, mtime))
                    except OSError:
                        continue
        except OSError:
            # 忽略不可读目录
            pass
        return results

    def _sync_list() -> str:
        # 1. 解析 .gitignore 获得基础排除模式
        gitignore_patterns = _parse_gitignore(safe_path)
        # 2. 合并用户传入的额外排除模式
        all_patterns = set(gitignore_patterns)
        if exclude_patterns:
            all_patterns.update(exclude_patterns)

        # 3. 递归收集文件
        files_info = _collect_files(safe_path, safe_path, "", all_patterns)

        # 4. 排序并格式化
        files_info.sort(key=lambda x: x[0])

        lines = [f"Directory: {safe_path.resolve()}", ""]

        if not files_info:
            lines.append("(empty)")
        else:
            for rel_path, size, mtime in files_info:
                if size < 1024:
                    size_str = f"{size} B"
                elif size < 1024 ** 2:
                    size_str = f"{size / 1024:.1f} KB"
                elif size < 1024 ** 3:
                    size_str = f"{size / 1024 ** 2:.1f} MB"
                else:
                    size_str = f"{size / 1024 ** 3:.1f} GB"

                time_str = datetime.datetime.fromtimestamp(mtime).strftime("%Y-%m-%d %H:%M:%S")
                line = f"FILE   {rel_path:<40} {size_str:>10}  {time_str}"
                lines.append(line)

        return "\n".join(lines)

    return await loop.run_in_executor(None, _sync_list)