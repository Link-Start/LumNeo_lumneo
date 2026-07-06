# backend/db/profiles.py
import json
import aiosqlite
from typing import List, Optional
from backend.database import get_db

class ProfileRecord:
    def __init__(self, row: aiosqlite.Row):
        self.id = row['id']
        self.name = row['name']
        self.profile_prompt = row['profile_prompt'] or ""
        # 解析 tools JSON
        self.tools = self._parse_json(row['tools'])
        # 处理数值参数的默认值
        self.temperature = row['temperature'] if row['temperature'] is not None else 1.0
        self.top_p = row['top_p'] if row['top_p'] is not None else 1.0
        self.top_k = row['top_k'] if row['top_k'] is not None else 40
        self.frequency_penalty = row['frequency_penalty'] if row['frequency_penalty'] is not None else 0.0
        self.presence_penalty = row['presence_penalty'] if row['presence_penalty'] is not None else 0.0

    def _parse_json(self, val):
        if val is None:
            return []
        try:
            return json.loads(val)
        except:
            return []

    def to_dict(self):
        return {
            'id': self.id,
            'name': self.name,
            'tools': self.tools,
            'profile_prompt': self.profile_prompt,
            'temperature': self.temperature,
            'top_p': self.top_p,
            'top_k': self.top_k,
            'frequency_penalty': self.frequency_penalty,
            'presence_penalty': self.presence_penalty
        }

async def create_profile(
    name: str, 
    tools: List[str], 
    profile_prompt: str, 
    temperature: float, 
    top_p: float, 
    top_k: int, 
    frequency_penalty: float, 
    presence_penalty: float
) -> ProfileRecord:
    """创建新角色"""
    db = await get_db()
    try:
        tools_json = json.dumps(tools, ensure_ascii=False)
        cursor = await db.execute(
            """INSERT INTO profiles 
               (name, tools, profile_prompt, temperature, top_p, top_k, frequency_penalty, presence_penalty)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (name, tools_json, profile_prompt, temperature, top_p, top_k, frequency_penalty, presence_penalty)
        )
        await db.commit()
        profile_id = cursor.lastrowid
        
        # 查询刚插入的记录
        cursor = await db.execute("SELECT * FROM profiles WHERE id = ?", (profile_id,))
        row = await cursor.fetchone()
        return ProfileRecord(row)
    finally:
        await db.close()

async def update_profile(
    profile_id: int,
    name: str, 
    tools: List[str], 
    profile_prompt: str, 
    temperature: float, 
    top_p: float, 
    top_k: int, 
    frequency_penalty: float, 
    presence_penalty: float
) -> Optional[ProfileRecord]:
    """更新角色信息"""
    db = await get_db()
    try:
        tools_json = json.dumps(tools, ensure_ascii=False)
        await db.execute(
            """UPDATE profiles 
               SET name = ?, tools = ?, profile_prompt = ?,
                   temperature = ?, top_p = ?, top_k = ?, frequency_penalty = ?, presence_penalty = ?
               WHERE id = ?""",
            (name, tools_json, profile_prompt,
             temperature, top_p, top_k, frequency_penalty, presence_penalty,
             profile_id)
        )
        await db.commit()
        
        # 检查是否有更新
        if db.total_changes == 0:
            return None
            
        # 返回更新后的记录
        cursor = await db.execute("SELECT * FROM profiles WHERE id = ?", (profile_id,))
        row = await cursor.fetchone()
        return ProfileRecord(row)
    finally:
        await db.close()

async def list_profiles() -> List[ProfileRecord]:
    """获取所有角色列表"""
    db = await get_db()
    try:
        cursor = await db.execute(
            """SELECT id, name, tools, profile_prompt,
                      temperature, top_p, top_k, frequency_penalty, presence_penalty
               FROM profiles"""
        )
        rows = await cursor.fetchall()
        return [ProfileRecord(row) for row in rows]
    finally:
        await db.close()

async def delete_profile(profile_id: int) -> bool:
    """删除角色"""
    db = await get_db()
    try:
        await db.execute("DELETE FROM profiles WHERE id = ?", (profile_id,))
        await db.commit()
        return True
    finally:
        await db.close()

async def get_profile_by_id(profile_id: int) -> Optional[ProfileRecord]:
    """根据 ID 获取单个角色"""
    db = await get_db()
    try:
        cursor = await db.execute("SELECT * FROM profiles WHERE id = ?", (profile_id,))
        row = await cursor.fetchone()
        if row:
            return ProfileRecord(row)
        return None
    finally:
        await db.close()