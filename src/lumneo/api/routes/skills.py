# src/lumneo/api/routes/skills.py
# 技能管理路由：列表 / 更新 / 删除 / 上传 / 批量选择
from typing import List, Optional

from fastapi import APIRouter, HTTPException, Request, UploadFile, File, Form

from lumneo.api.schemas.resources import UpdateSkillRequest, BatchSelectRequest
from lumneo.application.facade import ApplicationFacade


router = APIRouter(prefix="/api/skills", tags=["skills"])


def _get_facade(request: Request) -> ApplicationFacade:
    return request.app.state.resource_facade


@router.get("/list")
async def list_skills(profile_id: Optional[int] = None, include_profiles: bool = False,
                      request: Request = None):
    return await _get_facade(request).list_skills(
        profile_id=profile_id, include_profiles=include_profiles,
    )


@router.put("/{skill_id}")
async def update_skill(skill_id: str, req: UpdateSkillRequest, request: Request):
    result = await _get_facade(request).update_skill(
        skill_id, name=req.name, description=req.description, is_global=req.is_global,
    )
    if not result:
        raise HTTPException(status_code=404, detail="技能不存在")
    return result


@router.delete("/{skill_id}")
async def delete_skill(skill_id: str, request: Request):
    try:
        return await _get_facade(request).delete_skill(skill_id)
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except RuntimeError as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/upload")
async def upload_skill_folder(request: Request, files: List[UploadFile] = File(...),
                              skillName: Optional[str] = Form(None),
                              is_global: bool = Form(False),
                              profile_id: Optional[int] = Form(None)):
    file_list = []
    try:
        for f in files:
            content = await f.read()
            file_list.append((f.filename, content))
    finally:
        for f in files:
            await f.close()
    try:
        return await _get_facade(request).upload_skill(
            files=file_list, skill_name=skillName, is_global=is_global, profile_id=profile_id,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/batch-select")
async def batch_select_skills(req: BatchSelectRequest, request: Request):
    await _get_facade(request).batch_select_skills(req.profile_id, req.selected_skill_ids)
    return {"success": True, "message": "批量更新成功"}
