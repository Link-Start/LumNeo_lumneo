# backend/system_tools/writer.py
import os
from pathlib import Path
from typing import Any, Dict, Optional

from backend.utils.validators import validate_path
from backend.utils.base import is_absolute
import backend


async def file_write(
    path: str,
    content: str,
    encoding: Optional[str] = "UTF-8",
    overwrite: bool = True,
    create_dirs: bool = True,
) -> Dict[str, Any]:
    """
    将文本内容写入指定路径的文件（全量覆盖或追加）。
    """
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
) -> Dict[str, Any]:
    """
    基于 Search-and-Replace（查找与替换）逻辑，对指定文件进行局部的精准修改、插入或删除。

    该工具专门适配 AI 编程场景，通过严格的唯一性校验防止代码被错误覆盖。它会：
    - 安全校验路径并读取目标文件。
    - 检查文件中 `search` 代码块的数量。若未找到或存在多处匹配，则拒绝操作并返回错误。
    - 精准替换唯一的代码块，并复用底层的安全落盘逻辑。

    💡 操作指南：
    - 【修改代码】：在 search 填入旧代码，replace 填入新代码。
    - 【插入代码】：本函数不支持基于行号或空 search 插入。请将 search 作为“锚点”上下文，在 replace 中填入 “原代码 + 新代码”（即追加）或 “新代码 + 原代码”（即前置）。
    - 【删除代码】：在 search 填入要删除的代码，replace 填入空字符串。

    Args:
        path:           目标文件路径（相对或绝对路径）。
        search:         作为定位锚点的原有代码块（必须在文件中严格匹配且唯一存在，注意空格、缩进和换行符需完全一致）。
        replace:        准备替换进去的新代码块（若为插入操作，需包含 search 中的原有代码以保留原内容）。
        replace_all:    是否允许批量替换多处匹配项。默认为 False。
        encoding:       文件编码，默认为 UTF-8。

    Returns:
        包含 success、path、bytes_written 等状态的字典。
    """
    # 1. 路径与编码安全初始化
    paths = [backend.workspace_path]
    allowed_dirs = [Path(p).resolve() for p in paths]
    enc = encoding or "utf-8"

    if not is_absolute(path):
        path = f'{os.getcwd()}/{path}'

    try:
        safe_path = validate_path(path, allowed_dirs)
    except ValueError as e:
        return {"success": False, "error": f"路径校验失败：{e}"}

    # 2. 基础边界条件检查
    if not safe_path.exists():
        return {"success": False, "error": f"文件不存在，无法应用补丁：{safe_path}"}
    
    if safe_path.is_dir():
        return {"success": False, "error": f"目标路径是一个目录，无法作为文件修改：{safe_path}"}

    # 3. 读取并尝试匹配补丁
    try:
        old_content = safe_path.read_text(encoding=enc)
    except Exception as e:
        return {"success": False, "error": f"读取原文件失败：{e}"}

    # 核心安全机制：检查 search 块的唯一性，防止大模型由于幻觉错误覆盖代码
    occurrences = old_content.count(search)
    if occurrences == 0:
        return {
            "success": False,
            "error": "未在文件中找到匹配的 `search` 代码块。请确保空格、缩进和换行符与原文件完全一致。"
        }
    elif occurrences > 1 and not replace_all:
        return {
            "success": False,
            "error": f"在文件中找到了 {occurrences} 处匹配的 `search` 代码块。请提供更丰富的上下文代码以确保修改的唯一性。"
        }

    # 4. 执行文本替换并调用底层统一写入
    new_content = old_content.replace(search, replace)
    
    return await _write_impl(
        path=str(safe_path),
        content=new_content,
        encoding=enc,
        overwrite=True,
        create_dirs=False,
        offset=None,
        truncate_after=True,
    )


async def _write_impl(
    path: str,
    content: str,
    encoding: Optional[str],
    overwrite: bool,
    create_dirs: bool,
    offset: Optional[int],
    truncate_after: bool,
) -> Dict[str, Any]:
    """
    内部统一实现，供 file_write、file_modify 和 file_patch 调用。
    """
    # 加载配置
    paths = [backend.workspace_path]
    allowed_dirs = [Path(p).resolve() for p in paths]

    # 参数处理
    enc = encoding or "utf-8"

    if not is_absolute(path):
        path = f'{os.getcwd()}/{path}'

    # 路径安全校验
    try:
        safe_path = validate_path(path, allowed_dirs)
    except ValueError as e:
        return {
            "success": False,
            "error": f"路径校验失败：{e}",
        }

    # 检查路径是否指向一个已存在的目录（不允许写入目录）
    if safe_path.exists() and safe_path.is_dir():
        return {
            "success": False,
            "error": f"目标路径是一个目录，无法写入：{safe_path}",
        }

    # 自动创建父目录
    if create_dirs:
        try:
            safe_path.parent.mkdir(parents=True, exist_ok=True)
        except PermissionError:
            return {
                "success": False,
                "error": f"没有权限创建父目录：{safe_path.parent}",
            }
        except OSError as e:
            return {
                "success": False,
                "error": f"创建父目录失败：{e}",
            }

    # 写入或修改文件内容
    try:
        content_bytes = content.encode(enc)
        actual_bytes = 0

        # 追加模式（仅写入场景，offset 无效）
        if safe_path.exists() and not overwrite:
            with open(safe_path, 'a', encoding=enc) as f:
                f.write(content)
                actual_bytes = len(content_bytes)
        else:
            # 全量覆盖（未指定偏移量时）
            if offset is None:
                safe_path.write_text(content, encoding=enc)
                actual_bytes = len(content_bytes)
            else:
                # 指定偏移量的修改模式
                if offset < 0:
                    return {"success": False, "error": "偏移量不能为负数"}

                if not safe_path.exists():
                    safe_path.touch()

                with open(safe_path, 'r+b') as f:
                    f.seek(offset)
                    f.write(content_bytes)
                    if truncate_after:
                        f.truncate()
                actual_bytes = len(content_bytes)

    except PermissionError:
        return {
            "success": False,
            "error": f"没有写入权限：{safe_path}",
        }
    except UnicodeEncodeError:
        return {
            "success": False,
            "error": f"内容无法使用 {enc} 编码，请指定其他编码。",
        }
    except Exception as e:
        return {
            "success": False,
            "error": f"写入文件时发生未知错误：{e}",
        }

    # 成功返回
    return {
        "success": True,
        "path": str(safe_path),
        "bytes_written": actual_bytes,
        "encoding": enc,
    }