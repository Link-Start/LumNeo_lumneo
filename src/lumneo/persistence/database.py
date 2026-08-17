# src/lumneo/persistence/database.py
# Persistence —— 数据库基础设施（Database Infrastructure）
#
# 根据《LumNeo V2 架构规范》§30 / §32：
# - database.py 负责 Engine / Connection / Session Factory / Transaction Primitive /
#   Database Lifecycle，不承载任何业务逻辑（§31）。
# - 这里使用 aiosqlite 作为底层驱动；Connection 即“Session/Connection”原语。
# - 业务 CRUD / 查询交由 persistence/repositories/；数据映射交由 persistence/models/。
# - 本模块只依赖 Kernel（config / logger），禁止反向依赖任何业务模块。
import os
import aiosqlite
from typing import Optional

from lumneo.kernel.config.app_config import config


class Database:
    """数据库基础设施：连接工厂 + Schema 初始化 + 迁移。"""

    def __init__(self, db_path: str):
        self.db_path = db_path

    @property
    def path(self) -> str:
        return self.db_path

    async def connect(self) -> aiosqlite.Connection:
        """打开一个带 PRAGMA 配置的连接（Connection / Session 原语）。"""
        db = await aiosqlite.connect(self.db_path)
        db.row_factory = aiosqlite.Row
        await db.execute("PRAGMA foreign_keys = ON")
        # 开启 WAL 模式，实现读写并发，避免 "database is locked"
        await db.execute("PRAGMA journal_mode = WAL")
        # 调大缓存（约 80MB），减少磁盘 IO
        await db.execute("PRAGMA cache_size = -20000")
        # 同步模式 NORMAL，兼顾写入速度与安全性
        await db.execute("PRAGMA synchronous = NORMAL")
        return db

    async def init(self) -> None:
        """创建表结构并执行迁移（数据库生命周期）。"""
        os.makedirs(os.path.dirname(self.db_path) or ".", exist_ok=True)
        db = await self.connect()
        try:
            await self._create_schema(db)
            await self._migrate(db)
            await db.commit()
        finally:
            await db.close()

    # ───────────────────────── Schema 定义 ─────────────────────────
    async def _create_schema(self, db: aiosqlite.Connection) -> None:
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
                profile_id INTEGER DEFAULT NULL,
                model_id TEXT DEFAULT NULL,
                file_ref TEXT DEFAULT NULL,
                turn_index INTEGER NOT NULL,
                plan_id TEXT DEFAULT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (chat_id) REFERENCES chats(id) ON DELETE CASCADE
            )
        """)
        await db.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS idx_messages_turn "
            "ON messages (chat_id, turn_index, role)"
        )
        await db.execute(
            "CREATE INDEX IF NOT EXISTS idx_messages_time "
            "ON messages (chat_id, created_at ASC)"
        )
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
        await db.execute(
            "CREATE INDEX IF NOT EXISTS idx_tool_calls_call_id ON tool_calls (call_id)"
        )
        await db.execute(
            "CREATE INDEX IF NOT EXISTS idx_tool_calls_chat_id ON tool_calls (chat_id)"
        )
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
        await db.execute("""
            CREATE TABLE IF NOT EXISTS user_decisions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                chat_id TEXT NOT NULL,
                turn_index INTEGER NOT NULL,
                message TEXT DEFAULT NULL,
                status TEXT DEFAULT 'pending',
                timeout_seconds INTEGER DEFAULT 60,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (chat_id) REFERENCES chats(id) ON DELETE CASCADE
            )
        """)
        await db.execute(
            "CREATE INDEX IF NOT EXISTS idx_decisions_chat ON user_decisions (chat_id)"
        )
        await db.execute(
            "CREATE INDEX IF NOT EXISTS idx_decisions_status ON user_decisions (status)"
        )
        await db.execute("""
            CREATE TABLE IF NOT EXISTS plans (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                plan_id TEXT NOT NULL UNIQUE,
                chat_id TEXT NOT NULL,
                steps TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (chat_id) REFERENCES chats(id) ON DELETE CASCADE
            )
        """)
        await db.execute(
            "CREATE INDEX IF NOT EXISTS idx_plans_plan_id ON plans (plan_id)"
        )
        await db.execute(
            "CREATE INDEX IF NOT EXISTS idx_plans_chat_id ON plans (chat_id)"
        )

    # ───────────────────────── 迁移 ─────────────────────────
    async def _migrate(self, db: aiosqlite.Connection) -> None:
        cursor = await db.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = await cursor.fetchall()
        table_names = [t[0] for t in tables]

        if "profiles" in table_names:
            cursor = await db.execute("PRAGMA table_info(profiles)")
            columns = await cursor.fetchall()
            column_names = [col[1] for col in columns]
            if "avatar" not in column_names:
                await db.execute("ALTER TABLE profiles ADD COLUMN avatar TEXT DEFAULT ''")

        if "messages" in table_names:
            cursor = await db.execute("PRAGMA table_info(messages)")
            columns = await cursor.fetchall()
            column_names = [col[1] for col in columns]
            if "profile_id" not in column_names:
                await db.execute("ALTER TABLE messages ADD COLUMN profile_id TEXT DEFAULT ''")
            if "model_id" not in column_names:
                await db.execute("ALTER TABLE messages ADD COLUMN model_id TEXT DEFAULT ''")
            if "plan_id" not in column_names:
                await db.execute("ALTER TABLE messages ADD COLUMN plan_id TEXT DEFAULT NULL")


# ───────────────────────── 模块级单例 ─────────────────────────
_database: Optional[Database] = None


def get_database() -> Database:
    """获取全局 Database 单例（由 Bootstrap 初始化阶段创建并注入）。"""
    global _database
    if _database is None:
        db_path = str(config.db_path)
        _database = Database(db_path)
    return _database


def set_database(database: Database) -> None:
    """允许 Bootstrap 显式注入 Database 实例。"""
    global _database
    _database = database
