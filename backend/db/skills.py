import json
import os
import aiosqlite
from typing import List, Optional, Dict, Any
from backend.database import get_db
from backend.utils.skill_parser import parse_skill_markdown
from backend.utils.skill_cache import skill_cache

class SkillRecord:
    def __init__(self, row: aiosqlite.Row):
        self.id = row['id']
        self.name = row['name']
        self.description = row['description'] or ''
        self.file_path = row['file_path']
        self.enabled = bool(row['enabled'])
        self.is_global = bool(row['is_global'])
        self.metadata = json.loads(row['metadata'])
        # 从 metadata 中提取简短描述（用于轻量注入 System Prompt）
        self.short_description = self.description or self.metadata.get('description', '')
        # prompt_content 保留但默认不加载（懒加载）
        self.prompt_content = ""

    async def load_full_content(self) -> str:
        """
        按需加载完整的 SKILL.md 正文内容（用于需要完整指令的场景）
        返回内容字符串，若失败返回空字符串
        """
        # 检查缓存
        cached = skill_cache.get(self.id, self.file_path)
        if cached is not None:
            self.prompt_content = cached
            return cached

        if not self.file_path:
            return ""

        skill_md_path = os.path.join(self.file_path, "SKILL.md")
        if not os.path.exists(skill_md_path):
            return ""

        try:
            with open(skill_md_path, 'r', encoding='utf-8') as f:
                content = f.read()
            # 去除 YAML 头部（仅保留正文）
            _, body = parse_skill_markdown(content)
            self.prompt_content = body
            skill_cache.set(self.id, self.file_path, body)
            return body
        except Exception as e:
            print(f"读取技能文件失败 {self.id}: {e}")
            return ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "description": self.short_description,
            "enabled": self.enabled,
            "is_global": self.is_global,
            "metadata": self.metadata,
            "short_description": self.short_description,
        }

async def create_skill(
    skill_id: str,
    name: str,
    file_path: str = "",
    metadata: dict = None,
    is_global: bool = False
) -> Optional[SkillRecord]:
    """创建或更新技能（Upsert）"""
    db = await get_db()
    try:
        metadata_json = json.dumps(metadata or {}, ensure_ascii=False)
        await db.execute(
            """INSERT INTO skills (id, name, file_path, metadata, is_global, updated_at)
               VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
               ON CONFLICT(id) DO UPDATE SET
               name=excluded.name,
               file_path=excluded.file_path,
               metadata=excluded.metadata,
               is_global=excluded.is_global,
               updated_at=CURRENT_TIMESTAMP""",
            (skill_id, name, file_path, metadata_json, 1 if is_global else 0)
        )
        await db.commit()
        return await get_skill_by_id(skill_id)
    finally:
        await db.close()

async def update_skill(
    skill_id: str,
    name: str = None,
    description: str = None,
    is_global: bool = None
) -> Optional[SkillRecord]:
    """更新技能信息"""
    db = await get_db()
    try:
        # 构建动态更新
        fields = []
        params = []
        if name is not None:
            fields.append("name = ?")
            params.append(name)
        if description is not None:
            fields.append("description = ?")
            params.append(description)
        if is_global is not None:
            fields.append("is_global = ?")
            params.append(1 if is_global else 0)
        if not fields:
            return await get_skill_by_id(skill_id)
        fields.append("updated_at = CURRENT_TIMESTAMP")
        params.append(skill_id)
        await db.execute(
            f"UPDATE skills SET {', '.join(fields)} WHERE id = ?",
            params
        )
        await db.commit()
        return await get_skill_by_id(skill_id)
    finally:
        await db.close()

async def delete_skill(skill_id: str) -> bool:
    """删除技能（级联删除关联记录）"""
    db = await get_db()
    try:
        await db.execute("DELETE FROM skills WHERE id = ?", (skill_id,))
        await db.commit()
        return True
    except Exception as e:
        print(f"删除技能失败: {e}")
        return False
    finally:
        await db.close()


async def get_skill_by_id(skill_id: str) -> Optional[SkillRecord]:
    db = await get_db()
    try:
        cursor = await db.execute("SELECT * FROM skills WHERE id = ?", (skill_id,))
        row = await cursor.fetchone()
        return SkillRecord(row) if row else None
    finally:
        await db.close()


async def link_skill_to_profile(profile_id: int, skill_id: str, config_overrides: dict = None):
    """将技能与角色关联，若已关联则忽略"""
    db = await get_db()
    try:
        config_json = json.dumps(config_overrides or {}, ensure_ascii=False)
        await db.execute(
            """INSERT INTO profile_skills (profile_id, skill_id, config_overrides)
               VALUES (?, ?, ?)""",
            (profile_id, skill_id, config_json)
        )
        await db.commit()
    except Exception as e:
        print(f"关联技能失败(可能已存在): {e}")
    finally:
        await db.close()


async def get_skills_by_profile(profile_id: int) -> List[SkillRecord]:
    """
    获取指定角色拥有的所有技能（已启用且被选中）
    注意：不再自动加载文件内容，仅返回元数据。
    如需完整指令，调用方应通过 system_read_file 工具或 SkillRecord.load_full_content() 按需获取。
    """
    db = await get_db()
    try:
        cursor = await db.execute(
            """SELECT s.* FROM skills s
               INNER JOIN profile_skills ps ON s.id = ps.skill_id
               WHERE ps.profile_id = ? AND s.enabled = 1 AND ps.is_selected = 1
               ORDER BY s.created_at DESC""",
            (profile_id,)
        )
        rows = await cursor.fetchall()
        skills = [SkillRecord(row) for row in rows]
        # 不加载文件内容，只返回元数据
        return skills
    finally:
        await db.close()

async def get_profiles_using_skill(skill_id: str) -> list:
    db = await get_db()
    try:
        cursor = await db.execute(
            """SELECT p.id, p.name FROM profiles p
               INNER JOIN profile_skills ps ON p.id = ps.profile_id
               WHERE ps.skill_id = ?""",
            (skill_id,)
        )
        rows = await cursor.fetchall()
        return [{"id": row[0], "name": row[1]} for row in rows]
    finally:
        await db.close()

async def list_all_skills() -> List[SkillRecord]:
    db = await get_db()
    try:
        cursor = await db.execute("SELECT * FROM skills ORDER BY created_at DESC")
        rows = await cursor.fetchall()
        return [SkillRecord(row) for row in rows]
    finally:
        await db.close()


async def replace_profile_skills(profile_id: int, skill_ids: List[str]) -> None:
    """
    全量替换角色的技能关联：先删除旧记录，再批量插入新记录。
    若 skill_ids 为空，则清空该角色的所有技能。
    """
    db = await get_db()
    try:
        await db.execute("BEGIN TRANSACTION")
        await db.execute("DELETE FROM profile_skills WHERE profile_id = ?", (profile_id,))
        for skill_id in set(skill_ids):
            await db.execute(
                "INSERT INTO profile_skills (profile_id, skill_id, config_overrides) VALUES (?, ?, ?)",
                (profile_id, skill_id, "{}")
            )
        await db.commit()
    except Exception:
        await db.rollback()
        raise
    finally:
        await db.close()


async def batch_set_selected_skills(profile_id: int, selected_skill_ids: List[str]) -> None:
    """
    批量设置指定角色下技能的选中状态。
    - 先将该角色所有技能的 is_selected 重置为 0
    - 再将传入的 selected_skill_ids 设为 1（无记录时自动创建关联）
    """
    db = await get_db()
    try:
        await db.execute("BEGIN TRANSACTION")
        await db.execute(
            "UPDATE profile_skills SET is_selected = 0 WHERE profile_id = ?",
            (profile_id,)
        )
        for skill_id in selected_skill_ids:
            await db.execute(
                """INSERT INTO profile_skills (profile_id, skill_id, is_selected, config_overrides)
                   VALUES (?, ?, 1, '{}')
                   ON CONFLICT(profile_id, skill_id) DO UPDATE SET
                   is_selected = excluded.is_selected""",
                (profile_id, skill_id)
            )
        await db.commit()
    except Exception:
        await db.rollback()
        raise
    finally:
        await db.close()


async def get_available_skills_for_profile(profile_id: int) -> List[SkillRecord]:
    """
    获取指定角色可用的技能列表：
    所有 is_global = 1 的技能，以及该角色已关联的非全局技能。
    """
    db = await get_db()
    try:
        cursor = await db.execute(
            """SELECT s.* FROM skills s
               WHERE s.is_global = 1
                  OR s.id IN (SELECT skill_id FROM profile_skills WHERE profile_id = ?)
               ORDER BY s.created_at DESC""",
            (profile_id,)
        )
        rows = await cursor.fetchall()
        return [SkillRecord(row) for row in rows]
    finally:
        await db.close()