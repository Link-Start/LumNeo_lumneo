# backend/routes/toolcalls.py
import os
import asyncio
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import List
from backend.db.tool_calls import (
    get_tool_call_by_id,
    get_tool_calls_by_call_ids,
    delete_tool_calls_by_call_ids,
)
from config_loader import config


router = APIRouter(prefix="/api/tool-calls", tags=["tool-calls"])

# ---------- 请求体模型 ----------
class BatchRequest(BaseModel):
    call_ids: List[str]

# ---------- 接口 ----------
@router.get("/{call_id}")
async def get_tool_call(call_id: str):
    record = await get_tool_call_by_id(call_id)
    if not record:
        raise HTTPException(status_code=404, detail="Tool call not found")
    
    data = record.to_dict()
    
    # 检查是否为存于磁盘的大文件
    if record.meta_data and record.meta_data.get("storage_type") == "file":
        file_path = f"{config.cache_dir}/{record.meta_data.get("file_path")}"
        if os.path.exists(file_path):
            try:
                # 使用 asyncio.to_thread 将同步的文件读取操作放到后台线程，不堵塞主线程
                full_content = await asyncio.to_thread(
                    lambda: open(file_path, "r", encoding="utf-8").read()
                )
                data["result"] = full_content
            except Exception as e:
                data["result"] = f"[读取完整内容失败: {str(e)}]"
        else:
            data["result"] = "[错误：本地结果文件已丢失或路径无效]"
            
    return data


@router.post("/batch")
async def batch_get_tool_calls(request: BatchRequest):
    if not request.call_ids:
        return {}
    
    records = await get_tool_calls_by_call_ids(request.call_ids)
    result_map = {}
    
    for r in records:
        # 检查是否为存于磁盘的大文件
        if r.meta_data and r.meta_data.get("storage_type") == "file":
            file_path = f"{config.cache_dir}/{r.meta_data.get("file_path")}"
            try:
                if os.path.exists(file_path):
                    # 使用 asyncio.to_thread 后台读取
                    full_content = await asyncio.to_thread(
                        lambda: open(file_path, "r", encoding="utf-8").read()
                    )
                    
                    # 发给大模型的必须做截断！防止 Token 爆炸
                    MAX_MODEL_CHARS = 6000
                    if len(full_content) > MAX_MODEL_CHARS:
                        truncated = (
                            full_content[:4000] 
                            + "\n\n...(中间内容过长已省略)...\n\n" 
                            + full_content[-2000:]
                        )
                    else:
                        truncated = full_content
                        
                    result_map[r.call_id] = {
                        "arguments": r.arguments, 
                        "result": truncated
                    }
                else:
                    result_map[r.call_id] = {
                        "arguments": r.arguments, 
                        "result": "[错误：本地文件缺失，无法提供上下文]"
                    }
            except Exception as e:
                result_map[r.call_id] = {
                    "arguments": r.arguments, 
                    "result": f"[读取完整内容失败: {str(e)}]"
                }
        else:
            # 普通小数据，直接返回
            result_map[r.call_id] = {
                "arguments": r.arguments, 
                "result": r.result
            }
            
    return result_map

@router.delete("/batch")
async def batch_delete_tool_calls(request: BatchRequest):
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