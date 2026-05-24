# backend/routes/models.py
import uuid
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import List, Optional
from backend.database import get_db

router = APIRouter(prefix="/api", tags=["models"])

class ModelConfigBase(BaseModel):
    name: str
    type: str  # 'local' or 'online'
    modelName: Optional[str] = None
    baseUrl: str
    apiKey: str

class ModelConfigResponse(ModelConfigBase):
    id: str

class UpdateModelRequest(BaseModel):
    name: Optional[str] = None
    type: Optional[str] = None
    modelName: Optional[str] = None
    baseUrl: Optional[str] = None
    apiKey: Optional[str] = None

@router.get("/models", response_model=List[ModelConfigResponse])
async def list_models():
    db = await get_db()
    cursor = await db.execute("SELECT id, name, type, modelName, baseUrl, apiKey FROM models ORDER BY name")
    rows = await cursor.fetchall()
    await db.close()
    return [
        {
            "id": row[0],
            "name": row[1],
            "type": row[2],
            "modelName": row[3],
            "baseUrl": row[4],
            "apiKey": row[5],
        }
        for row in rows
    ]

@router.post("/models", response_model=ModelConfigResponse)
async def create_model(data: ModelConfigBase):
    model_id = str(uuid.uuid4())
    db = await get_db()
    await db.execute(
        "INSERT INTO models (id, name, type, modelName, baseUrl, apiKey) VALUES (?, ?, ?, ?, ?, ?)",
        (model_id, data.name, data.type, data.modelName or "", data.baseUrl, data.apiKey)
    )
    await db.commit()
    await db.close()
    return {**data.dict(), "id": model_id}

@router.put("/models/{model_id}")
async def update_model(model_id: str, data: UpdateModelRequest):
    db = await get_db()
    # 构建动态更新语句
    updates = []
    params = []
    if data.name is not None:
        updates.append("name = ?")
        params.append(data.name)
    if data.type is not None:
        updates.append("type = ?")
        params.append(data.type)
    if data.modelName is not None:
        updates.append("modelName = ?")
        params.append(data.modelName)
    if data.baseUrl is not None:
        updates.append("baseUrl = ?")
        params.append(data.baseUrl)
    if data.apiKey is not None:
        updates.append("apiKey = ?")
        params.append(data.apiKey)
    if not updates:
        return {"status": "ok"}
    params.append(model_id)
    query = f"UPDATE models SET {', '.join(updates)} WHERE id = ?"
    await db.execute(query, params)
    if db.total_changes == 0:
        await db.close()
        raise HTTPException(status_code=404, detail="Model not found")
    await db.commit()
    await db.close()
    return {"status": "ok"}

@router.delete("/models/{model_id}")
async def delete_model(model_id: str):
    db = await get_db()
    await db.execute("DELETE FROM models WHERE id = ?", (model_id,))
    await db.commit()
    await db.close()
    return {"status": "ok"}