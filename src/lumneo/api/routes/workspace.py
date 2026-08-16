# api/routes/workspace.py
# 工作区设置 / 查询路由（薄层）。工作区路径是运行时全局状态（lumneo.workspace_path）。
from fastapi import APIRouter, HTTPException, Request

from lumneo.api.schemas.resources import WorkspaceRequest
from lumneo.application.facade import ApplicationFacade


router = APIRouter(prefix="/api", tags=["workspace"])


def _get_facade(request: Request) -> ApplicationFacade:
    return request.app.state.resource_facade


@router.post("/workspace/set")
async def set_workspace(req: WorkspaceRequest, request: Request):
    try:
        return await _get_facade(request).set_workspace(req.path)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/workspace")
async def get_workspace(request: Request):
    return await _get_facade(request).get_workspace()
