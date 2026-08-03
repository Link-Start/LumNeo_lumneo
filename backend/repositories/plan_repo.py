# backend/repositories/plan_repo.py
from typing import List, Dict, Optional
from backend.db.plan import create_plan, update_plan, get_plan


class PlanRepository:
    @staticmethod
    async def create_plan(plan_id: str, chat_id: str, steps: List[Dict]) -> bool:
        return await create_plan(plan_id, chat_id, steps)

    @staticmethod
    async def update_plan(plan_id: str, steps: List[Dict]) -> bool:
        return await update_plan(plan_id, steps)

    @staticmethod
    async def get_plan(plan_id: str) -> Optional[List[Dict]]:
        return await get_plan(plan_id)