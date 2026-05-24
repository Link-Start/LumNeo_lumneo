# backend/routes/workspace.py
import os
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
import backend

router = APIRouter(prefix="/api", tags=["workspace"])

class WorkspaceRequest(BaseModel):
    path: str

@router.post("/workspace/set")
async def set_workspace(req: WorkspaceRequest):

    if not os.path.isdir(req.path):
        raise HTTPException(400, "提供的路径不是一个有效目录")
    backend.workspace_path = req.path
    return {"status": "ok", "path": backend.workspace_path}

@router.get("/workspace")
async def get_workspace():
    return {"path": backend.workspace_path}