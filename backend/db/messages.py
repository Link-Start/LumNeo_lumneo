# backend/db/messages.py
import os
import json
import asyncio
import aiosqlite
from typing import List, Optional, Dict, Any
from backend.database import get_db
from backend.utils.base import delete_uploaded_files
from config_loader import config
from backend.bootstrap import logger


class MessageRecord:
    def __init__(self, row: aiosqlite.Row):
        self.id = row['id']
        self.chat_id = row['chat_id']
        self.role = row['role']
        self.content = self._parse_content(row['content'])
        self.profile_id = row['profile_id']
        self.file_ref = self._parse_json(row['file_ref'])
        self.turn_index = row['turn_index']
        self.created_at = row['created_at']

        self.profile = None
        if 'p_id' in row.keys():
            p_id = row['p_id']
            if p_id is not None:
                self.profile = {
                    'id': p_id,
                    'name': row['p_name'] if 'p_name' in row.keys() else '',
                    'avatar': row['p_avatar'] if 'p_avatar' in row.keys() else ''
                }
    
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
            'profile_id': self.profile_id,
            'profile': self.profile,
            'file_ref': self.file_ref,
            'turn_index': self.turn_index,
            'created_at': self.created_at
        }


async def get_messages(chat_id: str) -> List[MessageRecord]:
    """获取对话的所有消息（按 turn_index 顺序排列）"""
    db = await get_db()
    try:
        cursor = await db.execute(
            """
            SELECT 
                m.id, m.chat_id, m.role, m.content, 
                m.profile_id, m.file_ref, m.turn_index, m.created_at,
                p.id AS p_id, p.name AS p_name, p.avatar AS p_avatar
            FROM messages m
            LEFT JOIN profiles p ON m.profile_id = p.id
            WHERE m.chat_id = ?
            ORDER BY m.turn_index ASC
            """,
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
    profile_id: int = None,
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
            "INSERT INTO messages (chat_id, role, content, profile_id, file_ref, turn_index) VALUES (?, ?, ?, ?, ?, ?)",
            (chat_id, role, content_str, profile_id, file_ref_json, turn_index)
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
    profile_id: int = None,
    file_ref: Optional[dict] = None
) -> bool:
    """更新消息内容（移除了 tool_calls 参数）"""
    db = await get_db()
    try:
        content_str = json.dumps(content, ensure_ascii=False) if isinstance(content, (dict, list)) else content
        file_ref_json = json.dumps(file_ref) if file_ref else None
        
        await db.execute(
            "UPDATE messages SET content = ?, profile_id = ?, file_ref = ? WHERE id = ? AND chat_id = ?",
            (content_str, profile_id, file_ref_json, message_id, chat_id)
        )
        await db.commit()
        return db.total_changes > 0
    finally:
        await db.close()


async def truncate_messages(chat_id: str, from_turn_index: int) -> int:
    """
    截断消息：删除 from_turn_index 及之后的所有消息，
    并自动清理 tool_calls 表中对应的孤立工具记录及磁盘文件和关联的上传文件
    """
    db = await get_db()
    try:
        await db.execute("BEGIN TRANSACTION")
        
        # 1. 先查出来要被删掉的消息记录
        cursor = await db.execute(
            "SELECT role, content, file_ref FROM messages WHERE chat_id = ? AND turn_index >= ?",
            (chat_id, from_turn_index)
        )
        rows = await cursor.fetchall()
        
        # 2. 遍历提取所有 tool_call 的 call_id
        call_ids_to_delete = []
        for row in rows:
            if row['file_ref']:
                delete_uploaded_files(row['file_ref'])
            if row['role'] == 'assistant' and row['content']:
                try:
                    segments = json.loads(row['content'])
                    if isinstance(segments, list):
                        for seg in segments:
                            if seg.get('type') == 'tool_call':
                                c_id = (
                                    seg.get('id') or 
                                    seg.get('call_id') or 
                                    seg.get('content', {}).get('id') or 
                                    seg.get('content', {}).get('call_id')
                                )
                                if c_id:
                                    call_ids_to_delete.append(c_id)
                except:
                    pass
        
        # 3. 去重 call_ids
        unique_call_ids = list(set(call_ids_to_delete))
        files_to_delete = []

        # 4. 如果有关联工具，先读取它们的 meta_data 以获取磁盘文件路径
        if unique_call_ids:
            placeholders = ','.join(['?'] * len(unique_call_ids))
            cursor = await db.execute(
                f"SELECT meta_data FROM tool_calls WHERE call_id IN ({placeholders})",
                unique_call_ids
            )
            tool_rows = await cursor.fetchall()
            for tool_row in tool_rows:
                meta = tool_row['meta_data']
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

        # 5. 删除 messages 表中的记录
        await db.execute(
            "DELETE FROM messages WHERE chat_id = ? AND turn_index >= ?",
            (chat_id, from_turn_index)
        )
        
        # 6. 删除 tool_calls 表中的孤立数据
        if unique_call_ids:
            await db.execute(
                f"DELETE FROM tool_calls WHERE call_id IN ({placeholders})",
                unique_call_ids
            )
        
        await db.commit()

        # 7. 删除磁盘上的大文件
        for file_path in files_to_delete:
            await asyncio.sleep(0.5)  # 让出控制权，避免 Windows 文件占用
            max_retries = 3
            for attempt in range(max_retries):
                try:
                    os.remove(file_path)
                    try:
                        dir_path = os.path.dirname(file_path)
                        os.rmdir(dir_path)  # 只删空目录，不删有文件的目录
                    except OSError:
                        pass  # 目录不为空或已被删除，忽略即可
                    break
                except PermissionError as e:
                    if attempt < max_retries - 1:
                        logger.warning(f"文件被占用，第 {attempt+1} 次重试...")
                        await asyncio.sleep(0.5)
                    else:
                        logger.error(f"文件被占用无法删除 (重试 {max_retries} 次失败) {file_path}: {e}")
                except Exception as e:
                    logger.error(f"删除工具输出文件失败 {file_path}: {e}")
                    break

        return len(rows)
    except Exception as e:
        await db.rollback()
        raise e
    finally:
        await db.close()


async def delete_message(chat_id: str, turn_index: int) -> bool:
    """
    单轮精准删除。如果删的是 assistant，对应的 tool 和磁盘文件也会被清除。
    """
    db = await get_db()
    try:
        await db.execute("BEGIN TRANSACTION")
        
        # 1. 取出这一条 assistant 消息的内容，提取 call_id
        cursor = await db.execute(
            "SELECT role, content, file_ref FROM messages WHERE chat_id = ? AND turn_index = ?",
            (chat_id, turn_index)
        )
        row = await cursor.fetchone()

        if row and row['file_ref']:
            delete_uploaded_files(row['file_ref'])
        
        call_ids_to_delete = []
        if row and row['role'] == 'assistant' and row['content']:
            try:
                segments = json.loads(row['content'])
                if isinstance(segments, list):
                    for seg in segments:
                        if seg.get('type') == 'tool_call':
                            c_id = (
                                seg.get('id') or seg.get('call_id') or 
                                seg.get('content', {}).get('id') or seg.get('content', {}).get('call_id')
                            )
                            if c_id:
                                call_ids_to_delete.append(c_id)
            except:
                pass
        
        unique_call_ids = list(set(call_ids_to_delete))
        files_to_delete = []

        # 2. 获取对应的工具表记录，提取磁盘文件路径
        if unique_call_ids:
            placeholders = ','.join(['?'] * len(unique_call_ids))
            cursor = await db.execute(
                f"SELECT meta_data FROM tool_calls WHERE call_id IN ({placeholders})",
                unique_call_ids
            )
            tool_rows = await cursor.fetchall()
            for tool_row in tool_rows:
                meta = tool_row['meta_data']
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
        
        # 3. 删除消息
        await db.execute(
            "DELETE FROM messages WHERE chat_id = ? AND turn_index = ?",
            (chat_id, turn_index)
        )
        
        # 4. 删除工具
        if unique_call_ids:
            await db.execute(
                f"DELETE FROM tool_calls WHERE call_id IN ({placeholders})",
                unique_call_ids
            )
            
        await db.commit()

        # 5. 删除磁盘文件（带重试）
        for file_path in files_to_delete:
            await asyncio.sleep(0.5)
            max_retries = 3
            for attempt in range(max_retries):
                try:
                    os.remove(file_path)
                    try:
                        dir_path = os.path.dirname(file_path)
                        os.rmdir(dir_path)  # 只删空目录，不删有文件的目录
                    except OSError:
                        pass
                    break
                except PermissionError as e:
                    if attempt < max_retries - 1:
                        logger.warning(f"文件被占用，第 {attempt+1} 次重试...")
                        await asyncio.sleep(0.5)
                    else:
                        logger.error(f"文件被占用无法删除 (重试 {max_retries} 次失败) {file_path}: {e}")
                except Exception as e:
                    logger.error(f"删除工具输出文件失败 {file_path}: {e}")
                    break

        return True
    except Exception as e:
        await db.rollback()
        raise e
    finally:
        await db.close()