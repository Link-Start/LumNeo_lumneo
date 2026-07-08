# backend/db/chats.py
import json
import uuid
from datetime import datetime
import aiosqlite
from typing import List, Optional, Dict, Any
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

class MessageRecord:
    def __init__(self, row: aiosqlite.Row):
        self.id = row['id']
        self.chat_id = row['chat_id']
        self.role = row['role']
        self.content = self._parse_content(row['content'])
        self.file_ref = self._parse_json(row['file_ref'])
        self.tool_calls = self._parse_json(row['tool_calls']) if row['tool_calls'] else None
        self.tool_call_id = row['tool_call_id']

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

    def to_dict(self) -> Dict[str, Any]:
        return {
            'id': self.id,
            'role': self.role,
            'content': self.content,
            'file_ref': self.file_ref,
            'tool_calls': self.tool_calls,
            'tool_call_id': self.tool_call_id
        }

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

# --- Message CRUD ---

async def get_messages(chat_id: str) -> List[MessageRecord]:
    """获取对话的所有消息"""
    db = await get_db()
    try:
        cursor = await db.execute(
            "SELECT id, chat_id, role, content, file_ref, tool_calls, tool_call_id FROM messages WHERE chat_id = ? ORDER BY id",
            (chat_id,)
        )
        rows = await cursor.fetchall()
        return [MessageRecord(row) for row in rows]
    finally:
        await db.close()

async def add_message(
    chat_id: str, 
    role: str, 
    content: Any, 
    file_ref: Optional[dict] = None,
    tool_calls: Optional[List[Dict]] = None,
    tool_call_id: Optional[str] = None
) -> MessageRecord:
    """添加一条消息"""
    db = await get_db()
    try:
        # 处理 file_ref 序列化
        file_ref_json = json.dumps(file_ref) if file_ref else None
        
        # 处理 content：如果是 dict/list 需要转成 json 字符串存入
        content_str = json.dumps(content, ensure_ascii=False) if isinstance(content, (dict, list)) else content
        file_ref_json = json.dumps(file_ref) if file_ref else None
        tool_calls_json = json.dumps(tool_calls, ensure_ascii=False) if tool_calls else None

        cursor = await db.execute(
            "INSERT INTO messages (chat_id, role, content, file_ref, tool_calls, tool_call_id) VALUES (?, ?, ?, ?, ?, ?)",
            (chat_id, role, content_str, file_ref_json, tool_calls_json, tool_call_id)
        )
        await db.commit()
        msg_id = cursor.lastrowid
        
        # 查询刚插入的记录以返回完整对象
        cursor = await db.execute("SELECT * FROM messages WHERE id = ?", (msg_id,))
        row = await cursor.fetchone()
        return MessageRecord(row)
    finally:
        await db.close()

async def update_message(message_id: int, chat_id: str, content: Any, file_ref: Optional[dict] = None) -> bool:
    """更新消息内容"""
    db = await get_db()
    try:
        content_str = content
        if isinstance(content, (dict, list)):
            content_str = json.dumps(content, ensure_ascii=False)
            
        file_ref_json = json.dumps(file_ref) if file_ref else None
        
        await db.execute(
            "UPDATE messages SET content = ?, file_ref = ? WHERE id = ? AND chat_id = ?",
            (content_str, file_ref_json, message_id, chat_id)
        )
        await db.commit()
        # 返回是否有行被更新
        return db.total_changes > 0
    finally:
        await db.close()

async def delete_message(message_id: int, chat_id: str, cascade: bool = False) -> bool:
    """删除消息"""
    db = await get_db()
    try:
        if cascade:
            await db.execute(
                "DELETE FROM messages WHERE chat_id = ? AND id >= ?",
                (chat_id, message_id)
            )
        else:
            await db.execute(
                "DELETE FROM messages WHERE id = ? AND chat_id = ?",
                (message_id, chat_id)
            )
        await db.commit()
        return True
    finally:
        await db.close()
