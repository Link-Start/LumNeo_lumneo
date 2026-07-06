# backend/db/skills.py
import json
import os
import asyncio
import aiosqlite
from typing import List, Optional
from backend.database import get_db
from backend.utils.skill_parser import parse_skill_markdown
from backend.utils.skill_cache import skill_cache

class SkillRecord:
    def __init__(self, row: aiosqlite.Row):
        self.id = row['id']
        self.name = row['name']
        self.file_path = row['file_path']
        self.enabled = bool(row['enabled'])
        self.is_global = bool(row['is_global'])
        self.metadata = json.loads(row['metadata'])
        # 动态属性，稍后加载
        self.prompt_content = "" 

    async def load_content(self):
        """读取文件系统中的 SKILL.md 内容"""
        cached = skill_cache.get(self.id, self.file_path)
        if cached is not None:
            self.prompt_content = cached
            return
        skill_md_path = os.path.join(self.file_path, "SKILL.md")
        if os.path.exists(skill_md_path):
            try:
                # 使用异步读取如果可能，但 Python 标准库文件 IO 是阻塞的
                # 为了简单和兼容性，这里使用标准 open，在 gather 中运行即可
                with open(skill_md_path, 'r', encoding='utf-8') as f:
                    content = f.read()
                _, body = parse_skill_markdown(content)
                self.prompt_content = body
                skill_cache.set(self.id, self.file_path, body)
            except Exception as e:
                print(f"读取技能文件失败 {self.id}: {e}")
                self.prompt_content = f"Error loading skill: {e}"
        else:
            self.prompt_content = ""

    def to_dict(self):
        return {
            "id": self.id,
            "name": self.name,
            "enabled": self.enabled,
            "is_global": self.is_global,
            "metadata": self.metadata
        }

async def create_skill(
    skill_id: str,
    name: str,
    file_path: str = "",
    metadata: dict = None,
    is_global: bool = False
) -> SkillRecord:
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
    print(f"关联技能 {skill_id} 到角色 {profile_id}，配置: {config_overrides}")
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
    获取指定角色拥有的所有技能
    关键：并发加载文件内容，避免 IO 阻塞主流程
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
        
        # 并发加载所有技能的文件内容
        if skills:
            await asyncio.gather(*[s.load_content() for s in skills])
        
        return skills
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
        # 1. 删除旧关联
        await db.execute("DELETE FROM profile_skills WHERE profile_id = ?", (profile_id,))
        # 2. 插入新关联（去重）
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
        # 重置全部为非选中
        await db.execute(
            "UPDATE profile_skills SET is_selected = 0 WHERE profile_id = ?",
            (profile_id,)
        )
        # 将列表中的技能设为选中（UPSERT 确保关联存在）
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