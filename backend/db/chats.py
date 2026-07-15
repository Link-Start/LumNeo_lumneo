# backend/db/chats.py
import os
import uuid
import shutil
import aiosqlite
from datetime import datetime
from backend.database import get_db
from backend.utils.base import delete_uploaded_files
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
        # 先删除对话关联的上传文件
        cursor = await db.execute(
            "SELECT file_ref FROM messages WHERE chat_id = ?", 
            (chat_id,)
        )
        msg_rows = await cursor.fetchall()

        for row in msg_rows:
            if row['file_ref']:
                delete_uploaded_files(row['file_ref'])

        tool_dir = f"{config.cache_dir}/{chat_id}"
        abs_tool_dir = os.path.abspath(tool_dir)

        # 触发数据库级联删除（chats 表删除后，messages 和 tool_calls 会自动删除）
        await db.execute("DELETE FROM chats WHERE id = ?", (chat_id,))
        await db.commit()

        # 清理真实的磁盘文件
        if os.path.exists(abs_tool_dir) and abs_tool_dir.startswith(os.path.abspath(config.cache_dir)):
            try:
                shutil.rmtree(abs_tool_dir)
            except Exception as e:
                logger.error(f"删除对话工具关联文件夹失败 {abs_tool_dir}: {e}")
        else:
            logger.warning(f"工具文件夹不存在或路径异常，跳过删除: {abs_tool_dir}")
    finally:
        await db.close()