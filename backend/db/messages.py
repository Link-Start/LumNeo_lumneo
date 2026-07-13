import json
import aiosqlite
from typing import List, Optional, Dict, Any
from backend.database import get_db


class MessageRecord:
    def __init__(self, row: aiosqlite.Row):
        self.id = row['id']
        self.chat_id = row['chat_id']
        self.role = row['role']
        self.content = self._parse_content(row['content'])
        self.file_ref = self._parse_json(row['file_ref'])
        self.turn_index = row['turn_index']
        self.created_at = row['created_at']
    
    def _parse_content(self, val):
        # 如果 content 是 JSON 字符串 (assistant 角色)，尝试解析为字典
        if val and val.strip().startswith('{'):
            try:
                return json.loads(val)
            except:
                return val
        return val
    
    def _parse_json(self, val):
        if val is None:
            return None
        try:
            return json.loads(val)
        except:
            return val
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'id': self.id,
            'chat_id': self.chat_id,
            'role': self.role,
            'content': self.content,
            'file_ref': self.file_ref,
            'turn_index': self.turn_index,
            'created_at': self.created_at
        }


async def get_messages(chat_id: str) -> List[MessageRecord]:
    """获取对话的所有消息（按 turn_index 顺序排列）"""
    db = await get_db()
    try:
        cursor = await db.execute(
            "SELECT id, chat_id, role, content, file_ref, turn_index, created_at FROM messages WHERE chat_id = ? ORDER BY turn_index ASC",
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
    turn_index: Optional[int] = None
) -> MessageRecord:
    """添加一条消息（自动计算 turn_index）"""
    db = await get_db()
    try:
        # 如果没有传入 turn_index，自动计算当前对话的最大轮次 + 1
        if turn_index is None:
            cursor = await db.execute(
                "SELECT IFNULL(MAX(turn_index), 0) + 1 as next_turn FROM messages WHERE chat_id = ?", 
                (chat_id,)
            )
            row = await cursor.fetchone()
            turn_index = row['next_turn']
        
        # 序列化处理 content
        content_str = json.dumps(content, ensure_ascii=False) if isinstance(content, (dict, list)) else content
        file_ref_json = json.dumps(file_ref) if file_ref else None

        cursor = await db.execute(
            "INSERT INTO messages (chat_id, role, content, file_ref, turn_index) VALUES (?, ?, ?, ?, ?)",
            (chat_id, role, content_str, file_ref_json, turn_index)
        )
        await db.commit()
        msg_id = cursor.lastrowid
        
        cursor = await db.execute("SELECT * FROM messages WHERE id = ?", (msg_id,))
        row = await cursor.fetchone()
        return MessageRecord(row)
    finally:
        await db.close()


async def update_message(
    message_id: int, 
    chat_id: str, 
    content: Any, 
    file_ref: Optional[dict] = None
) -> bool:
    """更新消息内容（移除了 tool_calls 参数）"""
    db = await get_db()
    try:
        content_str = json.dumps(content, ensure_ascii=False) if isinstance(content, (dict, list)) else content
        file_ref_json = json.dumps(file_ref) if file_ref else None
        
        await db.execute(
            "UPDATE messages SET content = ?, file_ref = ? WHERE id = ? AND chat_id = ?",
            (content_str, file_ref_json, message_id, chat_id)
        )
        await db.commit()
        return db.total_changes > 0
    finally:
        await db.close()


async def delete_message(chat_id: str, turn_index: int) -> bool:
    """删除单条消息（按轮次精确删除）"""
    db = await get_db()
    try:
        await db.execute(
            "DELETE FROM messages WHERE chat_id = ? AND turn_index = ?",
            (chat_id, turn_index)
        )
        await db.commit()
        return True
    finally:
        await db.close()


async def truncate_messages(chat_id: str, from_turn_index: int) -> int:
    """
    截断消息：删除 from_turn_index 及之后的所有消息
    用于用户点击“重新生成”或“编辑”时的快速回滚
    """
    db = await get_db()
    try:
        cursor = await db.execute(
            "DELETE FROM messages WHERE chat_id = ? AND turn_index >= ?",
            (chat_id, from_turn_index)
        )
        await db.commit()
        return cursor.rowcount
    finally:
        await db.close()