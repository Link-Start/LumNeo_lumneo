import pytest
from pathlib import Path
from backend.memory.fts_index import FTSIndexManager

pytestmark = pytest.mark.asyncio(loop_scope="function")

@pytest.mark.asyncio
async def test_sync_and_search(fts_manager, tmp_memory_dir):
    """FTS5 同步与搜索"""
    # 创建一个 MD 文件
    file_path = tmp_memory_dir / "work" / "facts" / "test.md"
    file_path.parent.mkdir(parents=True, exist_ok=True)
    content = "---\ncategory: fact\nkey: test_key\n---\n\n这是测试内容"
    with open(file_path, "w", encoding="utf-8") as f:
        f.write(content)

    # 同步到 FTS
    await fts_manager.sync_file(file_path, project_tag="global")
    # 搜索
    results = await fts_manager.search("测试内容")
    assert len(results) >= 1
    assert results[0]["path"] == str(file_path)

@pytest.mark.asyncio
async def test_startup_consistency(fts_manager, tmp_memory_dir):
    """启动一致性校验：检测 MD 更新并重建索引"""
    # 创建文件并同步
    file_path = tmp_memory_dir / "work" / "facts" / "consistency.md"
    file_path.parent.mkdir(parents=True, exist_ok=True)
    content = "---\ncategory: fact\nkey: consistency\nupdated_at: 2026-01-01T00:00:00\n---\n\n旧内容"
    with open(file_path, "w", encoding="utf-8") as f:
        f.write(content)
    await fts_manager.sync_file(file_path)

    # 模拟 MD 更新（手动修改文件，更新 updated_at）
    new_content = "---\ncategory: fact\nkey: consistency\nupdated_at: 2026-01-02T00:00:00\n---\n\n新内容"
    with open(file_path, "w", encoding="utf-8") as f:
        f.write(new_content)

    # 运行一致性检查
    rebuilt, total = await fts_manager.startup_consistency_check(tmp_memory_dir)
    assert rebuilt >= 1
    assert total >= 1

    # 搜索应返回新内容
    results = await fts_manager.search("新内容")
    assert len(results) >= 1
    assert "新内容" in results[0]["content"]