from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import List
from backend.db.tool_calls import (
    get_tool_call_by_id,
    delete_tool_calls_by_call_ids,
)

router = APIRouter(prefix="/api/tool-calls", tags=["tool-calls"])


# ---------- 请求体模型 ----------
class BatchDeleteRequest(BaseModel):
    call_ids: List[str]


# ---------- 接口 ----------
@router.get("/{call_id}")
async def get_tool_call(call_id: str):
    """获取单个工具调用详情（前端查看完整参数/大文件时使用）"""
    record = await get_tool_call_by_id(call_id)
    if not record:
        raise HTTPException(status_code=404, detail="Tool call not found")
    return record.to_dict()


@router.delete("/batch")
async def delete_tool_calls_batch(request: BatchDeleteRequest):
    """
    批量删除工具调用记录
    """
    if not request.call_ids:
        return {"message": "No call_ids provided", "deleted_count": 0}
        
    deleted_count = await delete_tool_calls_by_call_ids(request.call_ids)
    return {
        "message": "Tool calls deleted successfully",
        "deleted_count": deleted_count
    }