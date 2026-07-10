# backend/routes/chats.py
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import List, Optional, Any, Union
from backend.db.chats import (
    create_chat,
    update_chat_title,
    list_chats,
    delete_chat,
    get_messages,
    add_message,
    update_message as update_message_db,
    delete_message as delete_message_db
)

router = APIRouter(prefix="/api/chats", tags=["chats"])

class ChatResponse(BaseModel):
    id: str
    title: str
    created_at: Optional[str] = None

class MessageResponse(BaseModel):
    id: int
    role: str
    content: Any
    file_ref: Optional[Union[dict, list]] = None
    tool_calls: Optional[Any] = None
    tool_call_id: Optional[str] = None

class AddMessageRequest(BaseModel):
    role: str
    content: Any
    file_ref: Optional[Union[dict, list]] = None

class UpdateChatTitle(BaseModel):
    title: str

# 创建新对话
@router.post("/", response_model=ChatResponse)
async def create_chat_route():
    # 调用 db 层函数
    record = await create_chat()
    return record.to_dict()

@router.patch("/{chat_id}")
async def update_chat_title_route(chat_id: str, data: UpdateChatTitle):
    await update_chat_title(chat_id, data.title)
    return {"status": "ok"}

# 获取所有对话列表
@router.get("/", response_model=List[ChatResponse])
async def list_chats_route():
    records = await list_chats()
    return [r.to_dict() for r in records]

# 删除对话
@router.delete("/{chat_id}")
async def delete_chat_route(chat_id: str):
    await delete_chat(chat_id)
    return {"status": "ok"}

# 获取对话消息
@router.get("/{chat_id}/messages", response_model=List[MessageResponse])
async def get_messages_route(chat_id: str):
    records = await get_messages(chat_id)
    return [r.to_dict() for r in records]

@router.post("/{chat_id}/messages", response_model=MessageResponse)
async def add_message_route(chat_id: str, req: AddMessageRequest):
    record = await add_message(chat_id, req.role, req.content, req.file_ref)
    return record.to_dict()

@router.put("/{chat_id}/messages/{message_id}")
async def update_message_route(chat_id: str, message_id: int, req: AddMessageRequest):
    success = await update_message_db(message_id, chat_id, req.content, req.file_ref)
    
    if not success:
        raise HTTPException(status_code=404, detail="Message not found")
    
    return {"status": "ok"}

@router.delete("/{chat_id}/messages/{message_id}")
async def delete_message_route(chat_id: str, message_id: int, cascade: bool = False):
    await delete_message_db(message_id, chat_id, cascade)
    return {"status": "ok"}
