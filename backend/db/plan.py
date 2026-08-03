# backend/db/plan.py
import aiosqlite
import json
from backend.database import get_db
from typing import List, Dict, Optional


async def create_plan(plan_id: str, chat_id: str, steps: List[Dict]) -> bool:
    db = await get_db()
    try:
        steps_json = json.dumps(steps, ensure_ascii=False)
        await db.execute(
            "INSERT INTO plans (plan_id, chat_id, steps) VALUES (?, ?, ?)",
            (plan_id, chat_id, steps_json)
        )
        await db.commit()
        return True
    except aiosqlite.IntegrityError:
        return False
    finally:
        await db.close()


async def update_plan(plan_id: str, steps: List[Dict]) -> bool:
    db = await get_db()
    try:
        steps_json = json.dumps(steps, ensure_ascii=False)
        await db.execute(
            "UPDATE plans SET steps = ?, updated_at = CURRENT_TIMESTAMP WHERE plan_id = ?",
            (steps_json, plan_id)
        )
        await db.commit()
        return True
    except Exception:
        return False
    finally:
        await db.close()


async def get_plan(plan_id: str) -> Optional[List[Dict]]:
    db = await get_db()
    try:
        cursor = await db.execute("SELECT steps FROM plans WHERE plan_id = ?", (plan_id,))
        row = await cursor.fetchone()
        if row:
            return json.loads(row['steps'])
        return None
    finally:
        await db.close()