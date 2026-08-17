# api/routes/profiles.py
# 角色（画像）管理路由（薄层）。
from fastapi import APIRouter, HTTPException, Request

from lumneo.api.schemas.resources import ProfileCreate
from lumneo.application.facade import ApplicationFacade


router = APIRouter(prefix="/api/profiles", tags=["profiles"])


def _get_facade(request: Request) -> ApplicationFacade:
    return request.app.state.resource_facade


@router.post("/")
async def create_profile_route(profile: ProfileCreate, request: Request):
    return await _get_facade(request).create_profile(
        name=profile.name, avatar=profile.avatar, tools=profile.tools,
        profile_prompt=profile.profile_prompt, temperature=profile.temperature,
        top_p=profile.top_p, top_k=profile.top_k,
        frequency_penalty=profile.frequency_penalty, presence_penalty=profile.presence_penalty,
    )


@router.put("/{profile_id}")
async def update_profile_route(profile_id: int, profile: ProfileCreate, request: Request):
    result = await _get_facade(request).update_profile(
        profile_id, name=profile.name, avatar=profile.avatar, tools=profile.tools,
        profile_prompt=profile.profile_prompt, temperature=profile.temperature,
        top_p=profile.top_p, top_k=profile.top_k,
        frequency_penalty=profile.frequency_penalty, presence_penalty=profile.presence_penalty,
    )
    if not result:
        raise HTTPException(status_code=404, detail="角色不存在")
    return result


@router.get("/")
async def list_profiles_route(request: Request):
    return await _get_facade(request).list_profiles()


@router.delete("/{profile_id}")
async def delete_profile_route(profile_id: int, request: Request):
    await _get_facade(request).delete_profile(profile_id)
    return {"status": "ok"}


@router.get("/{profile_id}/skills")
async def get_profile_skills(profile_id: int, request: Request):
    return await _get_facade(request).get_profile_skills(profile_id)
