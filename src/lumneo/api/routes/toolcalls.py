# api/routes/toolcalls.py
# 工具调用记录管理路由（薄层）：查询 / 批量 / 删除 / 确认。
from fastapi import APIRouter, HTTPException, Request

from lumneo.api.schemas.resources import BatchRequest, ConfirmRequest
from lumneo.application.facade import ApplicationFacade


router = APIRouter(prefix="/api/tool-calls", tags=["tool-calls"])


def _get_facade(request: Request) -> ApplicationFacade:
    return request.app.state.resource_facade


@router.get("/{call_id}")
async def get_tool_call(call_id: str, request: Request):
    try:
        return await _get_facade(request).get_tool_call(call_id)
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/batch")
async def batch_get_tool_calls(req: BatchRequest, request: Request):
    return await _get_facade(request).batch_get_tool_calls(req.call_ids)


@router.delete("/batch")
async def batch_delete_tool_calls(req: BatchRequest, request: Request):
    return await _get_facade(request).delete_tool_calls(req.call_ids)


@router.post("/confirm")
async def confirm_tool_call(req: ConfirmRequest, request: Request):
    try:
        return await _get_facade(request).confirm_tool_call(req.call_id, req.confirmed)
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
