# backend/routes/chats.py
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import List, Optional, Any, Union
from backend.db.chats import (
    create_chat,
    update_chat_title,
    list_chats,
    delete_chat
)
from backend.db.messages import (
    get_messages,
    add_message,
    update_message as update_message_db,
    truncate_messages as truncate_messages_db,
    delete_message as delete_message_db
)

router = APIRouter(prefix="/api/chats", tags=["chats"])

# ---------- Pydantic 响应模型 ----------
class ChatResponse(BaseModel):
    id: str
    title: str
    created_at: Optional[str] = None

class MessageResponse(BaseModel):
    id: int
    chat_id: str
    role: str
    content: Any
    file_ref: Optional[Union[dict, list]] = None
    turn_index: int
    created_at: Optional[str] = None

# ---------- Pydantic 请求模型 ----------
class UpdateChatTitle(BaseModel):
    title: str

class AddMessageRequest(BaseModel):
    role: str
    content: Any
    file_ref: Optional[Union[dict, list]] = None
    turn_index: Optional[int] = None  # 如果没传，后端会自动分配下一轮

class UpdateMessageRequest(BaseModel):
    content: Any
    file_ref: Optional[Union[dict, list]] = None

# ---------- 路由 ----------

# 创建新对话
@router.post("/", response_model=ChatResponse)
async def create_chat_route():
    record = await create_chat()
    return record.to_dict()

# 更新对话标题
@router.patch("/{chat_id}")
async def update_chat_title_route(chat_id: str, data: UpdateChatTitle):
    await update_chat_title(chat_id, data.title)
    return {"status": "ok"}

# 获取所有对话列表
@router.get("/", response_model=List[ChatResponse])
async def list_chats_route():
    records = await list_chats()
    return [r.to_dict() for r in records]

# 删除对话（由于 chat 表有 ON DELETE CASCADE，依附的 messages 和 tool_calls 会自动清空）
@router.delete("/{chat_id}")
async def delete_chat_route(chat_id: str):
    await delete_chat(chat_id)
    return {"status": "ok"}

# ---------- 对话消息操作 ----------

# 获取指定对话的消息（按轮次排序）
@router.get("/{chat_id}/messages", response_model=List[MessageResponse])
async def get_messages_route(chat_id: str):
    records = await get_messages(chat_id)
    return [r.to_dict() for r in records]

# 新增一条消息（前端发来 user 或 流式结束后的 assistant 折叠 JSON）
@router.post("/{chat_id}/messages", response_model=MessageResponse)
async def add_message_route(chat_id: str, req: AddMessageRequest):
    record = await add_message(
        chat_id=chat_id,
        role=req.role,
        content=req.content,
        file_ref=req.file_ref,
        turn_index=req.turn_index
    )
    return record.to_dict()

# 更新一条消息的内容（仅限 content 和 file_ref）
@router.put("/{chat_id}/messages/{message_id}")
async def update_message_route(chat_id: str, message_id: int, req: UpdateMessageRequest):
    success = await update_message_db(
        message_id=message_id,
        chat_id=chat_id,
        content=req.content,
        file_ref=req.file_ref
    )
    if not success:
        raise HTTPException(status_code=404, detail="Message not found")
    return {"status": "ok"}

# 删除消息 / 截断对话（按轮次 turn_index 精准删除）
# 注意：URL 参数已从 message_id 改为 turn_index
@router.delete("/{chat_id}/messages/{turn_index}")
async def delete_message_route(chat_id: str, turn_index: int):
    # 内部会执行事务，自动清理 tool_calls
    deleted_count = await truncate_messages_db(chat_id=chat_id, from_turn_index=turn_index)
    return {"status": "ok", "deleted_count": deleted_count}