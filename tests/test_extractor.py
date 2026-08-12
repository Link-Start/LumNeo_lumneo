import pytest
from unittest.mock import AsyncMock
from backend.memory.extractor import MemoryExtractor

# 标记整个文件使用异步
pytestmark = pytest.mark.asyncio(loop_scope="function")


async def test_extract_fact():
    """测试提取 Fact（Mock LLM）"""
    mock_llm = AsyncMock()
    
    # 模拟异步生成器
    async def mock_generate(*args, **kwargs):
        yield '[{"category":"fact","key":"测试","content":"测试内容","importance":3}]'
    
    mock_llm.generate_response = mock_generate
    extractor = MemoryExtractor(llm_service=mock_llm)
    messages = [{"role": "user", "content": "我喜欢喝咖啡"}]
    result = await extractor.extract(messages, scope="life")
    
    assert len(result) == 1
    assert result[0]["category"] == "fact"
    assert result[0]["key"] == "测试"
    assert result[0]["content"] == "测试内容"
    assert result[0]["sensitivity"] == "normal"


async def test_extract_skill_default_proficiency():
    """提取 Skill 时 proficiency 固定为 1"""
    mock_llm = AsyncMock()
    
    async def mock_generate(*args, **kwargs):
        yield ('[{"category":"skill","key":"异步编程","content":"场景\\n方案\\n反模式",'
               '"domain":"backend","source_project":"测试项目","scenario":"高并发",'
               '"solution":"使用连接池","pitfalls":"避免新建连接"}]')
    
    mock_llm.generate_response = mock_generate
    extractor = MemoryExtractor(llm_service=mock_llm)
    messages = [{"role": "user", "content": "总结下异步编程方法"}]
    result = await extractor.extract(messages, scope="work", source_project="测试项目")
    
    assert result[0]["category"] == "skill"
    assert result[0]["proficiency"] == 1
    assert result[0]["verified"] is False
    assert result[0]["domain"] == "backend"
    assert "## 场景" in result[0]["content"]