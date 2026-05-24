# backend/routes/model.py
from pydantic import BaseModel
from fastapi import APIRouter, HTTPException
from openai import AsyncOpenAI

router = APIRouter(prefix="/api", tags=["model"])

class ModelQuery(BaseModel):
    base_url: str
    api_key: str = ""


@router.post("/model")
async def list_models(query: ModelQuery):
    try:
        temp_client = AsyncOpenAI(api_key=query.api_key or None, base_url=query.base_url)
        models = await temp_client.models.list()
        return [m.id for m in models.data]
    except Exception as e:
        raise HTTPException(500, str(e))