# api/routes/files.py
# 文件上传 / 删除路由（薄层）。物理落盘经 ApplicationFacade → StoragePort。
from fastapi import APIRouter, Request, UploadFile, File

from lumneo.application.facade import ApplicationFacade


router = APIRouter(prefix="/api/files", tags=["files"])


def _get_facade(request: Request) -> ApplicationFacade:
    return request.app.state.resource_facade


@router.post("/upload")
async def upload_file(file: UploadFile = File(...), request: Request = None):
    content = await file.read()
    return await _get_facade(request).upload_file(file.filename, content, file.content_type)


@router.delete("/")
async def delete_file(request: Request):
    body = await request.body()
    return await _get_facade(request).delete_files(body)
