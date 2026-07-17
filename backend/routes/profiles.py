# backend/routes/profiles.py
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from typing import List
from backend.db.profiles import (
    create_profile as create_profile_db,
    update_profile as update_profile_db,
    list_profiles as list_profiles_db,
    delete_profile as delete_profile_db
)
from backend.db.skills import get_skills_by_profile


router = APIRouter(prefix="/api/profiles", tags=["profiles"])

class ProfileCreate(BaseModel):
    name: str
    avatar: str
    tools: List[str] = []
    profile_prompt: str = ""
    temperature: float = Field(default=1.0, ge=0.0, le=2.0)
    top_p: float = Field(default=1.0, ge=0.0, le=1.0)
    top_k: int = Field(default=40, ge=1, le=100)
    frequency_penalty: float = Field(default=0.0, ge=-2.0, le=2.0) 
    presence_penalty: float = Field(default=0.0, ge=-2.0, le=2.0)

class ProfileResponse(BaseModel):
    id: int
    name: str
    avatar: str
    tools: List[str]
    profile_prompt: str
    temperature: float
    top_p: float
    top_k: int
    frequency_penalty: float
    presence_penalty: float

# 创建角色
@router.post("/", response_model=ProfileResponse)
async def create_profile_route(profile: ProfileCreate):
    record = await create_profile_db(
        name=profile.name,
        avatar=profile.avatar,
        tools=profile.tools,
        profile_prompt=profile.profile_prompt,
        temperature=profile.temperature,
        top_p=profile.top_p,
        top_k=profile.top_k,
        frequency_penalty=profile.frequency_penalty,
        presence_penalty=profile.presence_penalty
    )

    return record.to_dict()

# 更新角色
@router.put("/{profile_id}", response_model=ProfileResponse)
async def update_profile_route(profile_id: int, profile: ProfileCreate):
    print(profile)
    record = await update_profile_db(
        profile_id=profile_id,
        name=profile.name,
        avatar=profile.avatar,
        tools=profile.tools,
        profile_prompt=profile.profile_prompt,
        temperature=profile.temperature,
        top_p=profile.top_p,
        top_k=profile.top_k,
        frequency_penalty=profile.frequency_penalty,
        presence_penalty=profile.presence_penalty
    )
    
    if not record:
        raise HTTPException(status_code=404, detail="角色不存在")

    return record.to_dict()

# 获取所有角色
@router.get("/", response_model=List[ProfileResponse])
async def list_profiles_route(): 
    records = await list_profiles_db()
    result = []
    for r in records:
        d = r.to_dict()
        existing_tools = d.get('tools') or []
        d['tools'] = existing_tools
        result.append(d)
    return result

@router.delete("/{profile_id}")
async def delete_profile_route(profile_id: int):
    await delete_profile_db(profile_id)
    return {"status": "ok"}

# 获取指定角色已拥有的所有技能
@router.get("/{profile_id}/skills")
async def get_profile_skills(profile_id: int):
    """
    获取指定角色已拥有的所有技能
    """
    skills = await get_skills_by_profile(profile_id)
    # 返回技能列表，使用 to_dict() 或自定义字段
    return [s.id for s in skills]