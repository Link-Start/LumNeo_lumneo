# backend/routes/models.py
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import List, Optional
from backend.db.models import (
    list_models as list_models_db,
    create_model as create_model_db,
    update_model as update_model_db,
    delete_model as delete_model_db
)

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
    records = await list_models_db()
    return [r.to_dict() for r in records]

@router.post("/models", response_model=ModelConfigResponse)
async def create_model(data: ModelConfigBase):
    record = await create_model_db(
        name=data.name,
        type=data.type,
        model_name=data.modelName,
        base_url=data.baseUrl,
        api_key=data.apiKey
    )
    return record.to_dict()

@router.put("/models/{model_id}")
async def update_model(model_id: str, data: UpdateModelRequest):
    # 检查是否有需要更新的字段
    update_data = data.dict(exclude_unset=True)
    if not update_data:
        return {"status": "ok"}
        
    record = await update_model_db(
        model_id=model_id,
        name=data.name,
        type=data.type,
        model_name=data.modelName,
        base_url=data.baseUrl,
        api_key=data.apiKey
    )
    
    if not record:
        raise HTTPException(status_code=404, detail="Model not found")
        
    return {"status": "ok"}

@router.delete("/models/{model_id}")
async def delete_model(model_id: str):
    await delete_model_db(model_id)
    return {"status": "ok"}