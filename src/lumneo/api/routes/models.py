# src/lumneo/api/routes/models.py
# 模型配置（ProviderModel）管理与远程模型探测路由
from fastapi import APIRouter, HTTPException, Request

from lumneo.api.schemas.resources import ModelConfigBase, UpdateModelRequest, ModelQuery
from lumneo.application.facade import ApplicationFacade


router = APIRouter(prefix="/api", tags=["models"])


def _get_facade(request: Request) -> ApplicationFacade:
    return request.app.state.resource_facade


@router.get("/models")
async def list_models(request: Request):
    return await _get_facade(request).list_models()


@router.post("/models")
async def create_model(data: ModelConfigBase, request: Request):
    return await _get_facade(request).create_model(
        name=data.name, type=data.type, model_name=data.modelName,
        base_url=data.baseUrl, api_key=data.apiKey,
    )


@router.put("/models/{model_id}")
async def update_model(model_id: str, data: UpdateModelRequest, request: Request):
    result = await _get_facade(request).update_model(
        model_id, name=data.name, type=data.type, model_name=data.modelName,
        base_url=data.baseUrl, api_key=data.apiKey,
    )
    if not result:
        raise HTTPException(status_code=404, detail="Model not found")
    return {"status": "ok"}


@router.delete("/models/{model_id}")
async def delete_model(model_id: str, request: Request):
    await _get_facade(request).delete_model(model_id)
    return {"status": "ok"}


@router.post("/model")
async def list_remote_models(query: ModelQuery, request: Request):
    try:
        return await _get_facade(request).list_remote_models(query.base_url, query.api_key)
    except RuntimeError as e:
        raise HTTPException(status_code=500, detail=str(e))
