# api/routes/plans.py
# 计划（Plan）更新路由（薄层）。
from fastapi import APIRouter, HTTPException, Request

from lumneo.api.schemas.resources import UpdatePlanRequest
from lumneo.application.facade import ApplicationFacade


router = APIRouter(prefix="/api/plans", tags=["plans"])


def _get_facade(request: Request) -> ApplicationFacade:
    return request.app.state.resource_facade


@router.put("/{plan_id}")
async def update_plan_route(plan_id: str, req: UpdatePlanRequest, request: Request):
    try:
        return await _get_facade(request).update_plan(plan_id, req.steps)
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except RuntimeError as e:
        raise HTTPException(status_code=500, detail=str(e))
