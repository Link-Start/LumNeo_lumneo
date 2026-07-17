# backend/database.py
import os
import aiosqlite
from config_loader import config


async def get_db():
    db = await aiosqlite.connect(f"{config.data_dir}/data/lumneo.db")
    db.row_factory = aiosqlite.Row
    await db.execute("PRAGMA foreign_keys = ON")
    # 1. 开启 WAL 模式，实现读写并发，避免报错 "database is locked"
    await db.execute("PRAGMA journal_mode = WAL")
    # 2. 调大缓存大小（单位是页，1页通常为 4KB，调大能极大减少磁盘 IO）
    await db.execute("PRAGMA cache_size = -20000")  # 约 80MB 内存缓存
    # 3. 同步模式设为 NORMAL（兼顾写入速度与安全性）
    await db.execute("PRAGMA synchronous = NORMAL")
    return db

async def init_db():
    os.makedirs(os.path.dirname(f"{config.data_dir}/data/lumneo.db"), exist_ok=True)
    db = await get_db()

    await db.execute("""
        CREATE TABLE IF NOT EXISTS chats (
            id TEXT PRIMARY KEY,
            title TEXT DEFAULT '新对话',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    await db.execute("""
        CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            chat_id TEXT NOT NULL,
            role TEXT NOT NULL,
            content TEXT DEFAULT NULL,
            file_ref TEXT DEFAULT NULL,
            turn_index INTEGER NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (chat_id) REFERENCES chats(id) ON DELETE CASCADE
        )
    """)

    # 复合唯一索引（防止并发或重试导致轮次错乱）
    await db.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_messages_turn ON messages (chat_id, turn_index, role)")
    # 拉取顺序索引
    await db.execute("CREATE INDEX IF NOT EXISTS idx_messages_time ON messages (chat_id, created_at ASC)")

    await db.execute("""
        CREATE TABLE IF NOT EXISTS profiles (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            avatar TEXT DEFAULT '',
            tools TEXT NOT NULL DEFAULT '[]',
            profile_prompt TEXT DEFAULT '',
            temperature REAL DEFAULT 1.0,
            top_p REAL DEFAULT 1.0,
            top_k INTEGER DEFAULT 40,
            frequency_penalty REAL DEFAULT 0.0,
            presence_penalty REAL DEFAULT 0.0
        )
    """)

    await db.execute("""
        CREATE TABLE IF NOT EXISTS models (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            type TEXT NOT NULL,
            modelName TEXT NOT NULL,
            baseUrl TEXT NOT NULL,
            apiKey TEXT NOT NULL
        )
    """)

    await db.execute("""
        CREATE TABLE IF NOT EXISTS tool_calls (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            call_id TEXT NOT NULL UNIQUE,
            chat_id TEXT NOT NULL,
            tool_name TEXT NOT NULL,
            arguments TEXT DEFAULT NULL,
            result TEXT DEFAULT NULL,
            meta_data TEXT DEFAULT '{}',
            status TEXT DEFAULT 'calling',
            execution_time INTEGER DEFAULT NULL,
            error_message TEXT DEFAULT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (chat_id) REFERENCES chats(id) ON DELETE CASCADE
        )
    """)

    # 飞快的索引：用于大模型发送时，根据 call_id 列表一次性补全数据
    await db.execute("CREATE INDEX IF NOT EXISTS idx_tool_calls_call_id ON tool_calls (call_id)")
    await db.execute("CREATE INDEX IF NOT EXISTS idx_tool_calls_chat_id ON tool_calls (chat_id)")

    await db.execute("""
        CREATE TABLE IF NOT EXISTS skills (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            description TEXT DEFAULT NULL,
            file_path TEXT NOT NULL,
            enabled INTEGER DEFAULT 1,
            is_global INTEGER DEFAULT 0,
            metadata TEXT DEFAULT '{}',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    await db.execute("""
        CREATE TABLE IF NOT EXISTS profile_skills (
            profile_id INTEGER NOT NULL,
            skill_id TEXT NOT NULL,
            is_selected INTEGER DEFAULT 0,
            config_overrides TEXT DEFAULT '{}',
            PRIMARY KEY (profile_id, skill_id),
            FOREIGN KEY (profile_id) REFERENCES profiles(id) ON DELETE CASCADE,
            FOREIGN KEY (skill_id) REFERENCES skills(id) ON DELETE CASCADE
        )
    """)
    await migrate_db(db)
    await db.commit()
    await db.close()


async def migrate_db(db):
    """执行数据库迁移"""
    # 获取所有表的列信息
    cursor = await db.execute("SELECT name FROM sqlite_master WHERE type='table'")
    tables = await cursor.fetchall()
    table_names = [t[0] for t in tables]
    
    # profiles 表迁移
    if 'profiles' in table_names:
        cursor = await db.execute("PRAGMA table_info(profiles)")
        columns = await cursor.fetchall()
        column_names = [col[1] for col in columns]
        
        # 添加 avatar 字段
        if 'avatar' not in column_names:
            await db.execute("ALTER TABLE profiles ADD COLUMN avatar TEXT DEFAULT ''")