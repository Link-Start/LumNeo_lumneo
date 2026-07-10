# backend/db/models.py
import uuid
import aiosqlite
from typing import List, Optional
from backend.database import get_db

class ModelRecord:
    def __init__(self, row: aiosqlite.Row):
        self.id = row['id']
        self.name = row['name']
        self.type = row['type']
        self.modelName = row['modelName']
        self.baseUrl = row['baseUrl']
        self.apiKey = row['apiKey']

    def to_dict(self):
        return {
            'id': self.id,
            'name': self.name,
            'type': self.type,
            'modelName': self.modelName,
            'baseUrl': self.baseUrl,
            'apiKey': self.apiKey
        }

async def list_models() -> List[ModelRecord]:
    """获取所有模型配置"""
    db = await get_db()
    try:
        cursor = await db.execute(
            "SELECT id, name, type, modelName, baseUrl, apiKey FROM models ORDER BY name"
        )
        rows = await cursor.fetchall()
        return [ModelRecord(row) for row in rows]
    finally:
        await db.close()

async def create_model(
    name: str, 
    type: str, 
    model_name: Optional[str], 
    base_url: str, 
    api_key: str
) -> ModelRecord:
    """创建模型配置"""
    db = await get_db()
    try:
        model_id = str(uuid.uuid4())
        # 如果 model_name 为 None，存入空字符串
        final_model_name = model_name or ""
        
        await db.execute(
            "INSERT INTO models (id, name, type, modelName, baseUrl, apiKey) VALUES (?, ?, ?, ?, ?, ?)",
            (model_id, name, type, final_model_name, base_url, api_key)
        )
        await db.commit()
        
        # 查询刚插入的记录
        cursor = await db.execute("SELECT * FROM models WHERE id = ?", (model_id,))
        row = await cursor.fetchone()
        return ModelRecord(row)
    finally:
        await db.close()

async def update_model(
    model_id: str,
    name: Optional[str] = None,
    type: Optional[str] = None,
    model_name: Optional[str] = None,
    base_url: Optional[str] = None,
    api_key: Optional[str] = None
) -> Optional[ModelRecord]:
    """更新模型配置"""
    db = await get_db()
    try:
        updates = []
        params = []
        
        if name is not None:
            updates.append("name = ?")
            params.append(name)
        if type is not None:
            updates.append("type = ?")
            params.append(type)
        if model_name is not None:
            updates.append("modelName = ?")
            params.append(model_name)
        if base_url is not None:
            updates.append("baseUrl = ?")
            params.append(base_url)
        if api_key is not None:
            updates.append("apiKey = ?")
            params.append(api_key)
            
        if not updates:
            # 如果没有提供任何更新字段，直接返回当前记录（或 None）
            cursor = await db.execute("SELECT * FROM models WHERE id = ?", (model_id,))
            row = await cursor.fetchone()
            return ModelRecord(row) if row else None
            
        params.append(model_id)
        query = f"UPDATE models SET {', '.join(updates)} WHERE id = ?"
        await db.execute(query, params)
        await db.commit()
        
        # 检查是否有行被更新
        if db.total_changes == 0:
            return None
            
        # 返回更新后的记录
        cursor = await db.execute("SELECT * FROM models WHERE id = ?", (model_id,))
        row = await cursor.fetchone()
        return ModelRecord(row)
    finally:
        await db.close()

async def delete_model(model_id: str) -> bool:
    """删除模型配置"""
    db = await get_db()
    try:
        await db.execute("DELETE FROM models WHERE id = ?", (model_id,))
        await db.commit()
        return True
    finally:
        await db.close()
