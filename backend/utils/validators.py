# backend/utils/validators.py
"""基于 JSON Schema 的参数校验工具。"""
import jsonschema
from typing import Optional
from pathlib import Path
from typing import List, Optional


def format_validation_error(error: jsonschema.ValidationError) -> str:
    """将 jsonschema 异常格式化为用户友好的错误信息。"""
    path = " -> ".join(str(p) for p in error.path) if error.path else "根对象"
    return f"参数校验失败 [{path}]: {error.message}"

def validate_path(path: str, allowed_dirs: Optional[List[Path]] = None) -> Path:
    """
    验证并解析文件路径，防止路径遍历攻击。

    该函数会：
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
        FileNotFoundError: 可选，如果 strict 参数为 True 且路径不存在。
    """
    try:
        # 将输入转为 Path 对象，并解析为绝对路径（包含符号链接解析）
        p = Path(path).resolve(strict=False)
    except (OSError, RuntimeError) as e:
        raise ValueError(f"无效的路径 '{path}': {e}") from e

    if allowed_dirs:
        # 确保所有允许的目录也都是绝对且规范化的
        normalized_allowed = [d.resolve(strict=False) for d in allowed_dirs]
        
        # 检查 p 是否位于任一允许目录内（包括子目录）
        # 使用 Path.parents 进行精确匹配，避免字符串前缀欺骗
        if not any(p == d or d in p.parents for d in normalized_allowed):
            raise ValueError(
                f"访问被拒绝：'{path}' 解析后的路径 '{p}' 不在允许的目录内。"
                f"允许的目录：{', '.join(str(d) for d in normalized_allowed)}"
            )
    
    return p