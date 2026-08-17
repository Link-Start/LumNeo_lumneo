# infrastructure/filesystem/path_guard.py
# 路径安全边界（§39 / §60）。
#
# 领域（runtime/tools）不得直接做 I/O，但路径“校验”属于纯函数式安全原语，
# 放在基础设施层统一提供。任何需要落盘的工具都必须先经过 validate_path，
# 防止路径遍历（Path Traversal）攻击。
import os
from pathlib import Path
from typing import List, Optional

from lumneo.kernel.config.app_config import config
import lumneo


def validate_path(path: str, allowed_dirs: Optional[List[Path]] = None) -> Path:
    """
    验证并解析文件路径，防止路径遍历攻击。

    1. 将输入路径解析为绝对路径，并规范化（解析符号链接）。
    2. 如果提供了 allowed_dirs，确保最终路径位于其中一个允许的目录内。

    Args:
        path: 用户提供的文件路径字符串。
        allowed_dirs: 允许访问的目录列表（已解析的 Path 对象），
                      若为 None 则跳过目录限制检查。

    Returns:
        解析并验证后的绝对路径 Path 对象。

    Raises:
        ValueError: 路径不在允许的目录内，或路径不合法。
    """
    try:
        p = Path(path).resolve(strict=False)
    except (OSError, RuntimeError) as e:
        raise ValueError(f"无效的路径 '{path}': {e}") from e

    if allowed_dirs:
        normalized_allowed = [d.resolve(strict=False) for d in allowed_dirs]
        if not any(p == d or d in p.parents for d in normalized_allowed):
            raise ValueError(
                f"访问被拒绝：'{path}' 解析后的路径 '{p}' 不在允许的目录内。"
                f"允许的目录：{', '.join(str(d) for d in normalized_allowed)}"
            )

    return p


def default_allowed_dirs() -> List[Path]:
    """返回系统默认允许访问的目录（上传目录 / 技能目录 / 工作区）。

    供文件类系统工具在不显式指定时复用，保证越权校验一致。
    """
    raw = [config.uploads_dir, config.skills_dir, Path(lumneo.workspace_path)]
    return [Path(p).resolve(strict=False) for p in raw if p]


def sanitize_filename(name: str) -> str:
    """清洗文件名，移除非法字符，避免路径注入。"""
    import re
    cleaned = re.sub(r'[\\/:*?"<>|]', "_", name)
    return cleaned.strip().strip(".") or "unnamed"


def resolve_safe_path(path: str, allowed_dirs: Optional[List[Path]] = None) -> tuple:
    """校验并解析路径，返回 (safe_path, error_message)。

    成功时 error_message 为 None；失败时 safe_path 为 None。
    供文件类系统工具（write / delete / reader 等）统一复用。
    """
    if not Path(path).is_absolute():
        path = f"{os.getcwd()}/{path}"
    try:
        safe_path = validate_path(path, allowed_dirs)
        return safe_path, None
    except ValueError as e:
        return None, str(e)
