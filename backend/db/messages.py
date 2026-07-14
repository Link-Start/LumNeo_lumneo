# backend/db/messages.py
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


async def truncate_messages(chat_id: str, from_turn_index: int) -> int:
    """
    截断消息：删除 from_turn_index 及之后的所有消息，
    并自动清理 tool_calls 表中对应的孤立工具调用记录（原子操作）
    """
    db = await get_db()
    try:
        # 开启事务，保证删除动作要么全成功，要么全回滚
        await db.execute("BEGIN TRANSACTION")
        
        # 1. 先查出来要被删掉的记录（主要用于提取 call_id）
        cursor = await db.execute(
            "SELECT role, content FROM messages WHERE chat_id = ? AND turn_index >= ?",
            (chat_id, from_turn_index)
        )
        rows = await cursor.fetchall()
        
        # 2. 遍历提取所有 tool_call 的 call_id
        call_ids_to_delete = []
        for row in rows:
            if row['role'] == 'assistant' and row['content']:
                try:
                    segments = json.loads(row['content'])
                    if isinstance(segments, list):
                        for seg in segments:
                            if seg.get('type') == 'tool_call':
                                # 兼容你的各种结构提取 call_id
                                c_id = (
                                    seg.get('id') or 
                                    seg.get('call_id') or 
                                    seg.get('content', {}).get('id') or 
                                    seg.get('content', {}).get('call_id')
                                )
                                if c_id:
                                    call_ids_to_delete.append(c_id)
                except:
                    pass  # 非 JSON 数据忽略（例如 user 消息）
        
        # 3. 删除 messages 表中的记录
        await db.execute(
            "DELETE FROM messages WHERE chat_id = ? AND turn_index >= ?",
            (chat_id, from_turn_index)
        )
        
        # 4. 如果提取到了 call_id，同步删除 tool_calls 表中的孤立数据
        if call_ids_to_delete:
            # 去除重复的 ID
            unique_call_ids = list(set(call_ids_to_delete))
            placeholders = ','.join(['?'] * len(unique_call_ids))
            await db.execute(
                f"DELETE FROM tool_calls WHERE chat_id = ? AND call_id IN ({placeholders})",
                (chat_id, *unique_call_ids)
            )
        
        await db.commit()
        return len(rows)  # 返回实际删除的消息行数
    except Exception as e:
        await db.rollback()
        raise e
    finally:
        await db.close()


async def delete_message(chat_id: str, turn_index: int) -> bool:
    """
    单轮精准删除（仅删除一个轮次）。如果删的是 assistant，对应的 tool 也会被清除。
    """
    db = await get_db()
    try:
        await db.execute("BEGIN TRANSACTION")
        
        # 1. 取出这一条 assistant 消息的内容，提取 call_id
        cursor = await db.execute(
            "SELECT role, content FROM messages WHERE chat_id = ? AND turn_index = ?",
            (chat_id, turn_index)
        )
        row = await cursor.fetchone()
        call_ids_to_delete = []
        if row and row['role'] == 'assistant' and row['content']:
            try:
                segments = json.loads(row['content'])
                if isinstance(segments, list):
                    for seg in segments:
                        if seg.get('type') == 'tool_call':
                            c_id = seg.get('id') or seg.get('call_id') or seg.get('content', {}).get('id') or seg.get('content', {}).get('call_id')
                            if c_id:
                                call_ids_to_delete.append(c_id)
            except:
                pass
        
        # 2. 删除消息
        await db.execute(
            "DELETE FROM messages WHERE chat_id = ? AND turn_index = ?",
            (chat_id, turn_index)
        )
        
        # 3. 删除工具
        if call_ids_to_delete:
            unique_call_ids = list(set(call_ids_to_delete))
            placeholders = ','.join(['?'] * len(unique_call_ids))
            await db.execute(
                f"DELETE FROM tool_calls WHERE chat_id = ? AND call_id IN ({placeholders})",
                (chat_id, *unique_call_ids)
            )
            
        await db.commit()
        return True
    except Exception as e:
        await db.rollback()
        raise e
    finally:
        await db.close()