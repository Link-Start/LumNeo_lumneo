# backend/routes/chats.py
import json
from http.client import HTTPException
from fastapi import APIRouter
from pydantic import BaseModel
from typing import List, Optional, Any, Union
from backend.database import get_db


router = APIRouter(prefix="/api/chats", tags=["chats"])

class ChatResponse(BaseModel):
    id: str
    title: str
    created_at: Optional[str] = None

class MessageResponse(BaseModel):
    id: int
    role: str
    content: str
    file_ref: Optional[Union[dict, list]] = None

class AddMessageRequest(BaseModel):
    role: str
    content: Any
    file_ref: Optional[Union[dict, list]] = None

class UpdateChatTitle(BaseModel):
    title: str

# 创建新对话
@router.post("/", response_model=ChatResponse)
async def create_chat():
    import uuid
    from datetime import datetime
    chat_id = str(uuid.uuid4())
    now = datetime.now().isoformat()
    db = await get_db()
    await db.execute("INSERT INTO chats (id, title, created_at) VALUES (?, ?, ?)", (chat_id, "新对话", now))
    await db.commit()
    await db.close()
    return {"id": chat_id, "title": "新对话", "created_at": now}

@router.patch("/{chat_id}")
async def update_chat_title(chat_id: str, data: UpdateChatTitle):
    db = await get_db()
    await db.execute("UPDATE chats SET title = ? WHERE id = ?", (data.title, chat_id))
    await db.commit()
    await db.close()
    return {"status": "ok"}

# 获取所有对话列表
@router.get("/", response_model=List[ChatResponse])
async def list_chats():
    db = await get_db()
    cursor = await db.execute("SELECT id, title, created_at FROM chats ORDER BY created_at DESC")
    rows = await cursor.fetchall()
    await db.close()
    return [{"id": row[0], "title": row[1], "created_at": row[2]} for row in rows]

# 删除对话
@router.delete("/{chat_id}")
async def delete_chat(chat_id: str):
    db = await get_db()
    await db.execute("DELETE FROM chats WHERE id = ?", (chat_id,))
    await db.commit()
    await db.close()
    return {"status": "ok"}

# 获取对话消息
@router.get("/{chat_id}/messages", response_model=List[MessageResponse])
async def get_messages(chat_id: str):
    db = await get_db()
    cursor = await db.execute("SELECT id, role, content, file_ref FROM messages WHERE chat_id = ? ORDER BY id", (chat_id,))
    rows = await cursor.fetchall()
    await db.close()
    return [
        {
            "id": row[0],
            "role": row[1],
            "content": json.loads(row[2]) if isinstance(row[2], str) and (row[2].startswith('[') or row[2].startswith('{')) else row[2],
            "file_ref": json.loads(row[3]) if row[3] else None
        } 
        for row in rows
    ]

@router.post("/{chat_id}/messages", response_model=MessageResponse)
async def add_message(chat_id: str, req: AddMessageRequest):
    db = await get_db()
    cursor = await db.execute(
        "INSERT INTO messages (chat_id, role, content, file_ref) VALUES (?, ?, ?, ?)",
        (chat_id, req.role, req.content, json.dumps(req.file_ref) if req.file_ref else None)
    )
    await db.commit()
    msg_id = cursor.lastrowid
    await db.close()
    return {"id": msg_id, "role": req.role, "content": req.content, "file_ref": req.file_ref}

@router.put("/{chat_id}/messages/{message_id}")
async def update_message(chat_id: str, message_id: int, req: AddMessageRequest):
    db = await get_db()
    await db.execute("UPDATE messages SET content = ? WHERE id = ? AND chat_id = ?", (req.content, message_id, chat_id))
    if db.total_changes == 0:
        await db.close()
        raise HTTPException(status_code=404, detail="Message not found")
    await db.commit()
    await db.close()
    return {"status": "ok"}

@router.delete("/{chat_id}/messages/{message_id}")
async def delete_message(chat_id: str, message_id: int, cascade: bool = False):
    db = await get_db()
    if cascade:
        await db.execute("DELETE FROM messages WHERE chat_id = ? AND id >= ?", (chat_id, message_id))
    else:
        await db.execute("DELETE FROM messages WHERE id = ? AND chat_id = ?", (message_id, chat_id))
    await db.commit()
    await db.close()
    return {"status": "ok"}