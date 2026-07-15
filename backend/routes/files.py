# backend/routes/files.py
import os
import uuid
from fastapi import APIRouter, UploadFile, File, Request
from config_loader import config
from backend.utils.base import delete_uploaded_files


router = APIRouter(prefix="/api/files", tags=["files"])

@router.post("/upload")
async def upload_file(file: UploadFile = File(...)):
    os.makedirs(config.uploads_dir, exist_ok=True)
    ext = os.path.splitext(file.filename)[1]
    unique_name = f"{uuid.uuid4()}{ext}"
    file_path = os.path.join(config.uploads_dir, unique_name)
    content = await file.read()
    with open(file_path, "wb") as f:
        f.write(content)

    file_url = f"/files/uploads/{unique_name}"

    return {"filename": file.filename, "stored_name": unique_name, "type": file.content_type, "url": file_url}

@router.delete("/")
async def delete_file(request: Request):
    data = await request.body()
    delete_uploaded_files(data)
    return {"message": "File deleted successfully"}