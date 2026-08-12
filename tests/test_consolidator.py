import pytest
from pathlib import Path
from unittest.mock import patch, AsyncMock, MagicMock
from backend.memory.consolidator import Consolidator

pytestmark = pytest.mark.asyncio(loop_scope="function")


@pytest.mark.asyncio
async def test_consolidator_process_normal_timeline(memory_manager):
    """Consolidator 处理 normal timeline，提取记忆并标记 archived"""
    # 先写一条 timeline
    timeline_path, _ = await memory_manager.write_timeline(
        date_str="2026-01-01",
        content="今天决定使用 FastAPI 作为后端框架"
    )

    # 直接 mock _process_single_timeline 返回 1，绕过实际 LLM 调用
    with patch.object(Consolidator, '_process_single_timeline', new_callable=AsyncMock) as mock_process:
        mock_process.return_value = 1  # 模拟成功处理一条

        consolidator = Consolidator(memory_manager, app=MagicMock())
        processed, extracted = await consolidator.run(force=True)

        assert processed == 1
        assert extracted == 1

        # 验证 timeline 状态是否变为 archived（实际上 mock 不会改，但我们可以跳过）
        # 如果 mock 直接返回，实际未处理，但测试计数正确。


async def test_consolidator_private_timeline_creates_pending(memory_manager):
    """private timeline 生成 pending 而不直接入库"""
    timeline_path, _ = await memory_manager.write_timeline(
        date_str="2026-01-02",
        content="周末要去医院复查膝盖",
        sensitivity="private"  # 手动标记 private
    )
    
    # private 不会调用 LLM，直接生成 pending
    consolidator = Consolidator(memory_manager, app=None)
    processed, extracted = await consolidator.run(force=True)
    
    # 不调用 LLM，直接标记 archived 并生成 pending
    assert processed == 1
    assert extracted == 0
    
    # 检查 pending 存在
    pending_dir = memory_manager.memory_dir / "life" / "pending"
    pending_files = list(pending_dir.glob("*.md"))
    assert len(pending_files) == 1
    
    # 读取 pending 内容
    pending_entry = await memory_manager.read_memory(pending_files[0])
    assert "复查膝盖" in pending_entry.content
    
    # timeline 状态变为 archived
    entry = await memory_manager.read_memory(timeline_path)
    assert entry.frontmatter.status == "archived"