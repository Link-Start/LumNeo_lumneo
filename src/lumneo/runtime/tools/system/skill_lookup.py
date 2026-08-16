# runtime/tools/system/skill_lookup.py
# 技能路径查询的注入点（§60：工具不得直接访问数据库）。
#
# use_skill 工具在运行时根据 skill_id 查找技能根目录，但该查询属于持久化访问，
# 不应出现在工具函数内部。此处提供一个模块级的可替换查找函数，由 Bootstrap 注入
# 一个由 SkillRepository 支撑的实现。
from typing import Callable, Optional

# 默认返回 None：未注入时退化为“找不到”，由调用方给出友好错误。
_skill_lookup_fn: Callable[[str], Optional[str]] = lambda skill_id: None


def set_skill_lookup(fn: Callable[[str], Optional[str]]) -> None:
    """由 Bootstrap 注入技能路径查询实现（基于 SkillRepository）。"""
    global _skill_lookup_fn
    _skill_lookup_fn = fn


async def get_skill_file_path(skill_id: str) -> Optional[str]:
    """返回技能根目录（绝对路径字符串），找不到返回 None。

    注入的查找函数可以是同步或异步（依赖 Repository Port），此处统一 await 之。
    """
    result = _skill_lookup_fn(skill_id)
    if hasattr(result, "__await__"):
        result = await result
    return result
