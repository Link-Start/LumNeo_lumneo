from pathlib import Path
from backend.db.skills import get_skill_by_id


async def use_skill(skill_id) -> str:
    """
    根据技能ID 查询 file_path 读取对应的 SKILL.md 文件
    
    Args:
        skill_id: 技能ID
    
    Returns:
        SKILL.md 的完整内容，或错误信息
    """
    # 1. 空值校验
    if not skill_id or not skill_id.strip():
        return "错误：技能ID不能为空"

    skill = await get_skill_by_id(skill_id)
    
    if skill is not None:
        skill_file = Path(skill.file_path) / "SKILL.md"

        if not skill_file.exists():
            return f"错误：未找到技能 '{skill.name}'"

        try:
            content = skill_file.read_text(encoding="utf-8")
            prefix = f"""
【当前技能】：{skill.name}
【技能根目录】：{skill.file_path}
【资源文件读取规则】：当 SKILL.md 中引用 `references/xxx.md` 或 `scripts/xxx.py` 时，完整路径为 `{skill.file_path}/{{引用路径}}`。
    - 示例：引用 `references/news_sources.md` → 调用 `system_read_file("{skill.file_path}/references/news_sources.md")`
    - 示例：引用 `scripts/generate_queries.py` → 调用 `system_execute_script("{skill.file_path}/scripts/generate_queries.py")`
            """
            return prefix + content
        except Exception as e:
            return f"错误：读取技能文件失败 - {str(e)}"
    else:
        return f"错误：未找到 ID 为 '{skill_id}' 的技能"