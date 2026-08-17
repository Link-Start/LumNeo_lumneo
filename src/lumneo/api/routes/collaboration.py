# api/routes/collaboration.py
# 模型协作调度预览路由（薄层）。纯策略计算，不落库。
from fastapi import APIRouter, Request
from typing import Any, Dict

from lumneo.application.facade import ApplicationFacade


router = APIRouter(prefix="/api", tags=["collaboration"])


def _get_facade(request: Request) -> ApplicationFacade:
    return request.app.state.resource_facade


@router.post("/collaboration/preview")
async def preview_selection(req: Dict[str, Any], request: Request):
    return await _get_facade(request).preview_collaboration(req)
