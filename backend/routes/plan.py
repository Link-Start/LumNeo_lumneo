# backend/routes/plans.py
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import List, Dict, Any
from backend.db.plan import get_plan, update_plan

router = APIRouter(prefix="/api/plans", tags=["plans"])

class UpdatePlanRequest(BaseModel):
    steps: List[Dict[str, Any]]

@router.put("/{plan_id}")
async def update_plan_route(plan_id: str, req: UpdatePlanRequest):
    existing = await get_plan(plan_id)
    if existing is None:
        raise HTTPException(status_code=404, detail="Plan not found")
    success = await update_plan(plan_id, req.steps)
    if not success:
        raise HTTPException(status_code=500, detail="Failed to update plan")
    return {"status": "ok"}