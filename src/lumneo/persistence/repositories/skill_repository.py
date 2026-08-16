# persistence/repositories/skill_repository.py
# Persistence —— Repository Implementation（§24 / §79）。
import json
from typing import Dict, List, Optional

from lumneo.conversation.ports.skill_repository import SkillRepository
from lumneo.persistence.database import Database
from lumneo.persistence.models.skill import SkillModel
from lumneo.persistence.repositories._base import BaseRepository


class SQLSkillRepository(SkillRepository, BaseRepository):
    """SkillRepository 的 SQLite 实现。"""

    def __init__(self, database: Database):
        BaseRepository.__init__(self, database)

    # ───────────────────────── 写 ─────────────────────────
    async def create_or_update(self, skill_id: str, name: str, **fields) -> Optional[SkillModel]:
        file_path = fields.get("file_path", "") or ""
        description = fields.get("description", "") or ""
        is_global = 1 if bool(fields.get("is_global", False)) else 0
        enabled = 1 if bool(fields.get("enabled", True)) else 0
        metadata = fields.get("metadata")
        metadata_json = json.dumps(metadata if metadata is not None else {}, ensure_ascii=False)
        async with self._session() as db:
            await db.execute(
                """INSERT INTO skills (id, name, file_path, description, enabled, is_global, metadata, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                   ON CONFLICT(id) DO UPDATE SET
                       name=excluded.name,
                       file_path=excluded.file_path,
                       description=excluded.description,
                       enabled=excluded.enabled,
                       is_global=excluded.is_global,
                       metadata=excluded.metadata,
                       updated_at=CURRENT_TIMESTAMP""",
                (skill_id, name, file_path, description, enabled, is_global, metadata_json),
            )
            cursor = await db.execute("SELECT * FROM skills WHERE id = ?", (skill_id,))
            row = await cursor.fetchone()
            return SkillModel.from_row(row) if row else None

    async def update(self, skill_id: str, **fields) -> Optional[SkillModel]:
        updatable = {
            "name": fields.get("name"),
            "description": fields.get("description"),
            "file_path": fields.get("file_path"),
            "enabled": (1 if bool(fields["enabled"]) else 0) if "enabled" in fields else None,
            "is_global": (1 if bool(fields["is_global"]) else 0) if "is_global" in fields else None,
            "metadata": (
                json.dumps(fields["metadata"], ensure_ascii=False) if fields.get("metadata") is not None else None
            ),
        }
        sets, params = [], []
        for col, val in updatable.items():
            if val is not None:
                sets.append(f"{col} = ?")
                params.append(val)
        if not sets:
            return await self.get_by_id(skill_id)
        sets.append("updated_at = CURRENT_TIMESTAMP")
        params.append(skill_id)
        async with self._session() as db:
            await db.execute(f"UPDATE skills SET {', '.join(sets)} WHERE id = ?", tuple(params))
            cursor = await db.execute("SELECT * FROM skills WHERE id = ?", (skill_id,))
            row = await cursor.fetchone()
            return SkillModel.from_row(row) if row else None

    async def delete(self, skill_id: str) -> bool:
        async with self._session() as db:
            cursor = await db.execute("DELETE FROM skills WHERE id = ?", (skill_id,))
            return cursor.rowcount > 0

    # ───────────────────────── 读 ─────────────────────────
    async def get_by_id(self, skill_id: str) -> Optional[SkillModel]:
        async with self._session() as db:
            cursor = await db.execute("SELECT * FROM skills WHERE id = ?", (skill_id,))
            row = await cursor.fetchone()
            return SkillModel.from_row(row) if row else None

    async def list_all(self) -> List[SkillModel]:
        async with self._session() as db:
            cursor = await db.execute("SELECT * FROM skills ORDER BY created_at DESC")
            rows = await cursor.fetchall()
            return [SkillModel.from_row(r) for r in rows]

    async def list_by_profile(self, profile_id: int) -> List[SkillModel]:
        """角色已启用且被选中的技能（注入 System Prompt 用）。"""
        async with self._session() as db:
            cursor = await db.execute(
                """SELECT s.* FROM skills s
                   INNER JOIN profile_skills ps ON s.id = ps.skill_id
                   WHERE ps.profile_id = ? AND s.enabled = 1 AND ps.is_selected = 1
                   ORDER BY s.created_at DESC""",
                (profile_id,),
            )
            rows = await cursor.fetchall()
            return [SkillModel.from_row(r) for r in rows]

    async def list_available_for_profile(self, profile_id: int) -> List[SkillModel]:
        """角色可用技能：全部全局技能 + 已关联的（含未选中的）非全局技能。"""
        async with self._session() as db:
            cursor = await db.execute(
                """SELECT s.* FROM skills s
                   WHERE s.is_global = 1
                      OR s.id IN (SELECT skill_id FROM profile_skills WHERE profile_id = ?)
                   ORDER BY s.created_at DESC""",
                (profile_id,),
            )
            rows = await cursor.fetchall()
            return [SkillModel.from_row(r) for r in rows]

    async def get_profiles_using_skill(self, skill_id: str) -> list:
        async with self._session() as db:
            cursor = await db.execute(
                """SELECT p.id, p.name FROM profiles p
                   INNER JOIN profile_skills ps ON p.id = ps.profile_id
                   WHERE ps.skill_id = ?""",
                (skill_id,),
            )
            rows = await cursor.fetchall()
            return [{"id": row["id"], "name": row["name"]} for row in rows]

    # ───────────────────────── 关联管理 ─────────────────────────
    async def link_to_profile(self, profile_id: int, skill_id: str, config_overrides: dict = None) -> None:
        config_json = json.dumps(config_overrides or {}, ensure_ascii=False)
        async with self._session() as db:
            await db.execute(
                """INSERT INTO profile_skills (profile_id, skill_id, config_overrides)
                   VALUES (?, ?, ?)
                   ON CONFLICT(profile_id, skill_id) DO UPDATE SET
                       config_overrides=excluded.config_overrides""",
                (profile_id, skill_id, config_json),
            )

    async def replace_profile_skills(self, profile_id: int, skill_ids: List[str]) -> None:
        """全量替换角色技能关联：先清后插。"""
        async with self._session() as db:
            await db.execute("DELETE FROM profile_skills WHERE profile_id = ?", (profile_id,))
            for skill_id in set(skill_ids):
                await db.execute(
                    "INSERT INTO profile_skills (profile_id, skill_id, config_overrides) VALUES (?, ?, '{}')",
                    (profile_id, skill_id),
                )

    async def set_selected_skills(self, profile_id: int, selected_skill_ids: List[str]) -> None:
        """批量设置角色下技能的选中状态：先全部置 0，再置指定项为 1。"""
        async with self._session() as db:
            await db.execute(
                "UPDATE profile_skills SET is_selected = 0 WHERE profile_id = ?",
                (profile_id,),
            )
            for skill_id in selected_skill_ids:
                await db.execute(
                    """INSERT INTO profile_skills (profile_id, skill_id, is_selected, config_overrides)
                       VALUES (?, ?, 1, '{}')
                       ON CONFLICT(profile_id, skill_id) DO UPDATE SET
                           is_selected = excluded.is_selected""",
                    (profile_id, skill_id),
                )
