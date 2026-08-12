# tests/conftest.py
import sys
from pathlib import Path

# 将项目根目录添加到 sys.path
sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest
import aiosqlite
from typing import AsyncGenerator

from backend.memory.manager import MemoryManager
from backend.memory.fts_index import FTSIndexManager


@pytest.fixture(scope="function")
async def tmp_memory_dir(tmp_path: Path) -> AsyncGenerator[Path, None]:
    """每个测试用例独立的临时 memory 目录"""
    memory_dir = tmp_path / "memory"
    memory_dir.mkdir(parents=True)
    yield memory_dir


@pytest.fixture(scope="function")
async def db_connection(tmp_path: Path) -> AsyncGenerator[aiosqlite.Connection, None]:
    """临时 SQLite 数据库连接（用于 FTS）"""
    db_path = tmp_path / "test.db"
    db = await aiosqlite.connect(str(db_path))
    db.row_factory = aiosqlite.Row
    await db.execute("PRAGMA journal_mode=WAL")
    yield db
    await db.close()


@pytest.fixture(scope="function")
async def fts_manager(db_connection: aiosqlite.Connection) -> AsyncGenerator[FTSIndexManager, None]:
    fts = FTSIndexManager(db_connection)
    await fts.init_schema()  # 每次重新创建表
    yield fts


@pytest.fixture(scope="function")
async def memory_manager(
    tmp_memory_dir: Path,
    fts_manager: FTSIndexManager
) -> AsyncGenerator[MemoryManager, None]:
    """MemoryManager 实例（已注入 FTS）"""
    mgr = MemoryManager(memory_dir=tmp_memory_dir, fts_manager=fts_manager)
    # 取消后台循环，避免干扰测试
    try:
        mgr._access_flush_task.cancel()
    except Exception:
        pass
    try:
        mgr._pending_cleanup_task.cancel()
    except Exception:
        pass
    yield mgr
    await mgr.shutdown()