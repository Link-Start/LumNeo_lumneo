# backend/routes/memory.py
from pydantic import BaseModel
from fastapi import APIRouter, HTTPException, Request
from typing import Optional
from pydantic import BaseModel, Field


router = APIRouter(prefix="/api", tags=["memory"])

class ConsolidateRequest(BaseModel):
    force: bool = Field(default=False, description="是否强制运行，忽略触发门控")
    scope: Optional[str] = Field(default=None, description="归档范围: life/work，None 则全部")

class PendingActionRequest(BaseModel):
    path: str = Field(..., description="pending 文件路径")
    action: str = Field(..., description="操作: confirm(确认入库) / ignore(忽略删除) / escalate(标记secret)")

@router.post("/consolidate")
async def consolidate_memory(fastapi_request: Request, req: ConsolidateRequest):
    """手动触发记忆归档（Consolidator）"""
    consolidator = fastapi_request.app.state.consolidator
    if not consolidator:
        raise HTTPException(status_code=503, detail="记忆归档服务未初始化")

    try:
        processed, extracted = await consolidator.run(force=req.force)
        return {
            "success": True,
            "processed": processed,
            "extracted": extracted,
            "force": req.force,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"归档失败: {str(e)}")


@router.get("/stats")
async def memory_stats(fastapi_request: Request):
    """获取记忆系统统计"""
    memory_mgr = fastapi_request.app.state.memory_manager
    if not memory_mgr:
        raise HTTPException(status_code=503, detail="记忆服务未初始化")

    stats = {
        "memory_dir": str(memory_mgr.memory_dir),
        "life": {},
        "work": {},
    }

    for scope in ["life", "work"]:
        scope_dir = memory_mgr.memory_dir / scope
        if scope_dir.exists():
            for category_dir in scope_dir.iterdir():
                if category_dir.is_dir():
                    count = len(list(category_dir.rglob("*.md")))
                    stats[scope][category_dir.name] = count

    # FTS5 统计
    fts_mgr = fastapi_request.app.state.fts_manager
    if fts_mgr:
        try:
            fts_stats = await fts_mgr.get_stats()
            stats["fts5"] = fts_stats
        except Exception:
            stats["fts5"] = {"error": "无法获取"}

    return stats


@router.get("/pending")
async def list_pending(fastapi_request: Request):
    """获取待确认的记忆列表"""
    memory_mgr = fastapi_request.app.state.memory_manager
    if not memory_mgr:
        raise HTTPException(status_code=503, detail="记忆服务未初始化")

    pending_list = await memory_mgr.get_pending_list()
    return {
        "count": len(pending_list),
        "items": [
            {
                "path": str(p.relative_to(memory_mgr.memory_dir)),
                "key": fm.key,
                "created_at": fm.created_at,
                "expires_at": fm.expires_at,
                "summary": content[:200].replace("\n", " ") if content else "",
            }
            for p, fm, content in pending_list
        ],
    }


@router.post("/pending/action")
async def pending_action(fastapi_request: Request, req: PendingActionRequest):
    """处理待确认记忆（确认/忽略/标记secret）"""
    memory_mgr = fastapi_request.app.state.memory_manager
    if not memory_mgr:
        raise HTTPException(status_code=503, detail="记忆服务未初始化")

    if req.action not in ("confirm", "ignore", "escalate"):
        raise HTTPException(status_code=400, detail="无效的操作，可选: confirm / ignore / escalate")

    try:
        # #6 修复：路径遍历防护
        # 1. 拒绝绝对路径
        raw_path = req.path
        if raw_path.startswith("/") or raw_path.startswith("\\"):
            raise HTTPException(status_code=400, detail="路径必须为相对路径")
        
        # 2. 拒绝包含 .. 的路径
        if ".." in raw_path.replace("\\", "/").split("/"):
            raise HTTPException(status_code=400, detail="路径包含非法字符")

        # 3. 解析为相对路径，确保最终路径在 memory_dir 下
        target_path = memory_mgr.memory_dir / raw_path
        target_path = target_path.resolve()
        memory_dir_resolved = memory_mgr.memory_dir.resolve()
        
        if not str(target_path).startswith(str(memory_dir_resolved)):
            raise HTTPException(status_code=403, detail="路径超出允许范围")

        if not target_path.exists():
            raise HTTPException(status_code=404, detail="pending 文件不存在")

        success = await memory_mgr.confirm_pending(target_path, req.action)
        return {"success": success}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"处理失败: {str(e)}")