# backend/routes/profiles.py
import json
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import List
from backend.database import get_db

router = APIRouter(prefix="/api/profiles", tags=["profiles"])

class ProfileCreate(BaseModel):
    name: str
    tools: List[str] = []
    profile_prompt: str = ""

class ProfileResponse(BaseModel):
    id: int
    name: str
    tools: List[str]
    profile_prompt: str

# 创建角色
@router.post("/", response_model=ProfileResponse)
async def create_profile(profile: ProfileCreate):
    db = await get_db()
    tools_json = json.dumps(profile.tools)
    cursor = await db.execute(
        "INSERT INTO profiles (name, tools, profile_prompt) VALUES (?, ?, ?)",
        (profile.name, tools_json, profile.profile_prompt)
    )
    await db.commit()
    profile_id = cursor.lastrowid
    await db.close()
    return {"id": profile_id, "name": profile.name, "tools": profile.tools, "profile_prompt": profile.profile_prompt}

# 更新角色
@router.put("/{profile_id}", response_model=ProfileResponse)
async def update_profile(profile_id: int, profile: ProfileCreate):
    db = await get_db()
    tools_json = json.dumps(profile.tools)
    await db.execute(
        "UPDATE profiles SET name = ?, tools = ?, profile_prompt = ? WHERE id = ?",
        (profile.name, tools_json, profile.profile_prompt, profile_id)
    )
    if db.total_changes == 0:
        await db.close()
        raise HTTPException(status_code=404, detail="角色不存在")
    await db.commit()
    await db.close()
    return {"id": profile_id, "name": profile.name, "tools": profile.tools, "profile_prompt": profile.profile_prompt}

# 获取所有角色
@router.get("/", response_model=List[ProfileResponse])
async def list_profiles():
    db = await get_db()
    cursor = await db.execute("SELECT id, name, tools, profile_prompt FROM profiles")
    rows = await cursor.fetchall()
    await db.close()
    return [{"id": row[0], "name": row[1], "tools": __parse_tools(row[2]), "profile_prompt": row[3] or ""} for row in rows]

@router.delete("/{profile_id}")
async def delete_profile(profile_id: int):
    db = await get_db()
    await db.execute("DELETE FROM profiles WHERE id = ?", (profile_id,))
    await db.commit()
    await db.close()
    return {"status": "ok"}

def __parse_tools(tools_str: str) -> List[str]:
    import json
    try:
        return json.loads(tools_str)
    except:
        return []