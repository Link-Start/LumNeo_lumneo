import pytest
from pathlib import Path
from datetime import datetime, timedelta

from backend.memory.manager import MemoryManager
from backend.memory.models import MemoryEntry, MemoryFrontmatter

pytestmark = pytest.mark.asyncio(loop_scope="function")

@pytest.mark.asyncio
async def test_create_and_read_memory(memory_manager: MemoryManager):
    """测试创建和读取记忆"""
    content = "测试内容"
    fm_data = {"importance": 4}
    entry = await memory_manager.create_memory(
        scope="work",
        category="fact",
        key="test_key",
        content=content,
        frontmatter_data=fm_data,
    )
    assert entry is not None
    assert entry.file_path is not None
    assert entry.frontmatter.key == "test_key"
    assert entry.frontmatter.category == "fact"
    assert entry.frontmatter.importance == 4
    assert entry.content == content

    # 读取
    read_entry = await memory_manager.read_memory(Path(entry.file_path))
    assert read_entry is not None
    assert read_entry.content == content
    # 读取后 access_count 增加（批量计数，但检查内存计数器）
    assert memory_manager._pending_access_updates.get(entry.file_path) is not None

@pytest.mark.asyncio
async def test_conflict_and_supersedes(memory_manager: MemoryManager):
    """测试冲突检测与版本链"""
    # 创建第一条
    entry1 = await memory_manager.create_memory(
        scope="work", category="fact", key="conflict_key", content="旧内容"
    )
    # 检查冲突
    conflict = await memory_manager.check_conflict("conflict_key", "work", "fact")
    assert conflict.has_conflict is True
    assert conflict.existing_path == entry1.file_path

    # 创建新版本（版本链）
    new_entry, old_entry = await memory_manager.create_with_supersedes(
        scope="work", category="fact", key="conflict_key", content="新内容"
    )
    assert new_entry is not None
    assert old_entry is not None
    # 旧文件状态应为 superseded
    old_read = await memory_manager.read_memory(Path(old_entry.file_path))
    assert old_read.frontmatter.status == "superseded"
    assert old_read.frontmatter.superseded_by == Path(new_entry.file_path).name
    # 新文件 supersedes 应包含旧文件名
    assert new_entry.frontmatter.supersedes == [Path(old_entry.file_path).name]

@pytest.mark.asyncio
async def test_access_count_flush_not_update_updated_at(memory_manager: MemoryManager):
    """测试 access_count 刷盘时不更新 updated_at"""
    entry = await memory_manager.create_memory(
        scope="work", category="fact", key="access_test", content="测试"
    )
    file_path = Path(entry.file_path)
    # 记录原始 updated_at
    original_updated = entry.frontmatter.updated_at

    # 模拟多次读取（触发批量刷盘）
    for _ in range(60):
        await memory_manager.read_memory(file_path)

    # 强制刷盘
    await memory_manager._flush_access_counts()

    # 重新读取文件检查
    updated_entry = await memory_manager.read_memory(file_path, skip_access_count=True)
    assert updated_entry.frontmatter.updated_at == original_updated
    assert updated_entry.frontmatter.access_count >= 60

@pytest.mark.asyncio
async def test_timeline_write_sensitivity_auto(memory_manager: MemoryManager):
    """测试 timeline 写入时自动敏感度检测"""
    # 包含身份证号的文本应标记为 secret
    content = "我的身份证号是 11010119900307666X"
    file_path, final_sensitivity = await memory_manager.write_timeline(
        date_str="2026-01-01", content=content
    )
    assert final_sensitivity == "secret"

    # 包含健康信息的文本应标记为 private
    content = "明天要去医院复查膝盖"
    file_path, final_sensitivity = await memory_manager.write_timeline(
        date_str="2026-01-02", content=content
    )
    assert final_sensitivity == "private"

@pytest.mark.asyncio
async def test_pending_flow(memory_manager: MemoryManager):
    """测试 Pending 确认流程"""
    # 创建 pending
    pending_path = await memory_manager.create_pending(
        source_timeline="life/timeline/2026/01/01.md",
        summary="待确认摘要",
        original_quote="原始引用",
        expires_days=7,
    )
    assert pending_path.exists()

    # 获取 pending 列表
    pending_list = await memory_manager.get_pending_list()
    assert len(pending_list) == 1
    assert pending_list[0][0] == pending_path

    # 确认 pending（创建 fact）
    success = await memory_manager.confirm_pending(pending_path, "confirm")
    assert success is True
    # pending 文件应被删除
    assert not pending_path.exists()
    # fact 文件应生成（在 life/facts/ 下）
    fact_dir = memory_manager.memory_dir / "life" / "facts"
    fact_files = list(fact_dir.glob("*.md"))
    assert len(fact_files) > 0
    # 读取 fact 验证内容
    fact_entry = await memory_manager.read_memory(fact_files[0])
    assert "待确认摘要" in fact_entry.content