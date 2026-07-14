# backend/db/tool_calls.py
import json
import aiosqlite
from typing import List, Optional, Dict, Any
from backend.database import get_db


class ToolCallRecord:
    def __init__(self, row: aiosqlite.Row = None, **kwargs):
        if row:
            self.id = row['id']
            self.chat_id = row['chat_id']
            self.call_id = row['call_id']
            self.tool_name = row['tool_name']
            self.arguments = self._parse_json(row['arguments'])
            self.result = row['result']
            self.meta_data = self._parse_json(row['meta_data'])
            self.status = row['status']
            self.execution_time = row['execution_time']
            self.error_message = row['error_message']
            self.created_at = row['created_at']
            self.updated_at = row['updated_at']
        else:
            for k, v in kwargs.items():
                setattr(self, k, v)
    
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
            'call_id': self.call_id,
            'tool_name': self.tool_name,
            'arguments': self.arguments,
            'result': self.result,
            'meta_data': self.meta_data,
            'status': self.status,
            'execution_time': self.execution_time,
            'error_message': self.error_message,
            'created_at': self.created_at,
            'updated_at': self.updated_at,
        }


async def create_tool_call(
    chat_id: str,
    call_id: str,
    tool_name: str,
    arguments: Optional[Dict] = None
) -> ToolCallRecord:
    """创建工具调用记录"""
    db = await get_db()
    try:
        args_json = json.dumps(arguments, ensure_ascii=False) if arguments else None
        cursor = await db.execute(
            """INSERT INTO tool_calls (chat_id, call_id, tool_name, arguments, status)
               VALUES (?, ?, ?, ?, 'calling')""",
            (chat_id, call_id, tool_name, args_json)
        )
        await db.commit()
        
        # 查询刚插入的记录
        cursor = await db.execute(
            "SELECT * FROM tool_calls WHERE id = ?",
            (cursor.lastrowid,)
        )
        row = await cursor.fetchone()
        return ToolCallRecord(row)
    finally:
        await db.close()


async def update_tool_call(
    call_id: str,
    result: Optional[str] = None,
    status: Optional[str] = None,
    execution_time: Optional[int] = None,
    error_message: Optional[str] = None,
    arguments: Optional[Dict] = None,
    meta_data: Optional[Dict] = None
) -> Optional[ToolCallRecord]:
    """更新工具调用结果、状态、元数据"""
    db = await get_db()
    try:
        updates = []
        params = []
        
        if result is not None:
            updates.append("result = ?")
            params.append(result)
        if status is not None:
            updates.append("status = ?")
            params.append(status)
        if execution_time is not None:
            updates.append("execution_time = ?")
            params.append(execution_time)
        if error_message is not None:
            updates.append("error_message = ?")
            params.append(error_message)
        if arguments is not None:
            updates.append("arguments = ?")
            params.append(json.dumps(arguments, ensure_ascii=False))
        if meta_data is not None:
            updates.append("meta_data = ?")
            params.append(json.dumps(meta_data, ensure_ascii=False))
        
        if not updates:
            return None
        
        updates.append("updated_at = CURRENT_TIMESTAMP")
        params.append(call_id)
        
        sql = f"UPDATE tool_calls SET {', '.join(updates)} WHERE call_id = ?"
        await db.execute(sql, params)
        await db.commit()
        
        cursor = await db.execute(
            "SELECT * FROM tool_calls WHERE call_id = ?",
            (call_id,)
        )
        row = await cursor.fetchone()
        return ToolCallRecord(row) if row else None
    finally:
        await db.close()


async def get_tool_call_by_id(call_id: str) -> Optional[ToolCallRecord]:
    """根据 call_id 获取单条工具调用详情"""
    db = await get_db()
    try:
        cursor = await db.execute(
            "SELECT * FROM tool_calls WHERE call_id = ?",
            (call_id,)
        )
        row = await cursor.fetchone()
        return ToolCallRecord(row) if row else None
    finally:
        await db.close()


async def get_tool_calls_by_chat_id(chat_id: str) -> List[ToolCallRecord]:
    """获取整个 chat_id 关联的所有工具调用 (替换原来的 get_tool_calls_by_message)"""
    db = await get_db()
    try:
        cursor = await db.execute(
            "SELECT * FROM tool_calls WHERE chat_id = ? ORDER BY created_at",
            (chat_id,)
        )
        rows = await cursor.fetchall()
        return [ToolCallRecord(row) for row in rows]
    finally:
        await db.close()


async def update_tool_call_arguments(call_id: str, arguments: Dict):
    """流式过程中更新参数（参数收集完成后）"""
    db = await get_db()
    try:
        await db.execute(
            "UPDATE tool_calls SET arguments = ?, updated_at = CURRENT_TIMESTAMP WHERE call_id = ?",
            (json.dumps(arguments, ensure_ascii=False), call_id)
        )
        await db.commit()
    finally:
        await db.close()


async def delete_tool_calls_by_call_ids(call_ids: List[str]) -> int:
    """根据 call_id 列表批量删除工具调用记录 (配合对话截断编辑时清理孤立数据)"""
    if not call_ids:
        return 0
    db = await get_db()
    try:
        placeholders = ','.join(['?'] * len(call_ids))
        cursor = await db.execute(
            f"DELETE FROM tool_calls WHERE call_id IN ({placeholders})", 
            call_ids
        )
        await db.commit()
        return cursor.rowcount
    finally:
        await db.close()


async def delete_tool_calls_by_chat_id(chat_id: str) -> int:
    """根据 chat_id 批量删除该对话下的所有工具调用 (删除整个对话时清理数据)"""
    db = await get_db()
    try:
        cursor = await db.execute(
            "DELETE FROM tool_calls WHERE chat_id = ?", 
            (chat_id,)
        )
        await db.commit()
        return cursor.rowcount
    finally:
        await db.close()