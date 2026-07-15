# backend/db/chats.py
import os
import json
import uuid
import aiosqlite
from datetime import datetime
from backend.database import get_db
from config_loader import config
from backend.bootstrap import logger


class ChatRecord:
    def __init__(self, row: aiosqlite.Row):
        self.id = row['id']
        self.title = row['title']
        self.created_at = row['created_at']
    
    def to_dict(self):
        return {
            'id': self.id,
            'title': self.title,
            'created_at': self.created_at,
        }


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


async def update_chat_title(chat_id: str, title: str):
    db = await get_db()
    try:
        await db.execute(
            "UPDATE chats SET title = ? WHERE id = ?",
            (title, chat_id)
        )
        await db.commit()
    finally:
        await db.close()


async def list_chats() -> list[ChatRecord]:
    db = await get_db()
    try:
        cursor = await db.execute("SELECT id, title, created_at FROM chats ORDER BY created_at DESC")
        rows = await cursor.fetchall()
        return [ChatRecord(row) for row in rows]
    finally:
        await db.close()


async def delete_chat(chat_id: str):
    db = await get_db()
    try:
        # 1. 在级联删除前，先提取该对话下所有工具文件的路径
        cursor = await db.execute(
            "SELECT meta_data FROM tool_calls WHERE chat_id = ?", 
            (chat_id,)
        )
        rows = await cursor.fetchall()
        files_to_delete = []
        for row in rows:
            meta = row['meta_data']
            if meta:
                try:
                    meta_data = json.loads(meta)
                    if meta_data.get('storage_type') == 'file':
                        file_path = meta_data.get('file_path')
                        if file_path:
                            file_path = f"{config.cache_dir}/{file_path}"
                            abs_path = os.path.abspath(file_path)
                            if os.path.exists(abs_path):
                                files_to_delete.append(abs_path)
                except:
                    pass

        # 2. 触发数据库级联删除（chats 表删除后，messages 和 tool_calls 会自动删除）
        await db.execute("DELETE FROM chats WHERE id = ?", (chat_id,))
        await db.commit()

        # 3. 清理真实的磁盘文件
        for file_path in files_to_delete:
            try:
                os.remove(file_path)
                logger.info(f"成功删除对话关联的工具文件: {file_path}")
            except Exception as e:
                logger.error(f"删除对话关联文件失败 {file_path}: {e}")
    finally:
        await db.close()