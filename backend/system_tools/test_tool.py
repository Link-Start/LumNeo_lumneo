# backend/tools/test_tool.py
async def test_fail():
    """强制失败的测试工具，用于验证失败处理流程"""
    raise RuntimeError("连接超时了。。。")