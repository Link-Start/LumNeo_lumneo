# backend/db/chats.py
import json
import uuid
from datetime import datetime
import aiosqlite
from typing import List, Dict, Any
from backend.database import get_db

class ChatRecord:
    def __init__(self, row: aiosqlite.Row):
        self.id = row['id']
        self.title = row['title']
        self.created_at = row['created_at']

    def to_dict(self) -> Dict[str, Any]:
        return {
            'id': self.id,
            'title': self.title,
            'created_at': self.created_at
        }

    def _parse_json(self, val):
        if val is None:
            return None
        try:
            return json.loads(val)
        except:
            return val

    def _parse_content(self, val):
        # 如果是看起来像 JSON 的字符串则解析，否则原样返回
        if isinstance(val, str):
            if val.startswith('[') or val.startswith('{'):
                try:
                    return json.loads(val)
                except:
                    return val
            return val
        return val

# --- Chat CRUD ---

async def create_chat(title: str = "新对话") -> ChatRecord:
    """创建新对话"""
    db = await get_db()
    try:
        chat_id = str(uuid.uuid4())
        now = datetime.now().isoformat()
        await db.execute(
            "INSERT INTO chats (id, title, created_at) VALUES (?, ?, ?)",
            (chat_id, title, now)
        )
        await db.commit()
        # 直接构造对象返回，避免再次查询
        return ChatRecord({'id': chat_id, 'title': title, 'created_at': now})
    finally:
        await db.close()

async def update_chat_title(chat_id: str, title: str) -> bool:
    """更新对话标题"""
    db = await get_db()
    try:
        await db.execute("UPDATE chats SET title = ? WHERE id = ?", (title, chat_id))
        await db.commit()
        return True
    finally:
        await db.close()

async def list_chats() -> List[ChatRecord]:
    """获取所有对话列表"""
    db = await get_db()
    try:
        cursor = await db.execute("SELECT id, title, created_at FROM chats ORDER BY created_at DESC")
        rows = await cursor.fetchall()
        return [ChatRecord(row) for row in rows]
    finally:
        await db.close()

async def delete_chat(chat_id: str) -> bool:
    """删除对话"""
    db = await get_db()
    try:
        await db.execute("DELETE FROM chats WHERE id = ?", (chat_id,))
        await db.commit()
        return True
    finally:
        await db.close()

