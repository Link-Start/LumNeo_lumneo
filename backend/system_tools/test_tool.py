import asyncio

async def test_fail():
    """强制失败的测试工具，用于验证失败处理流程，延迟20秒后失败"""
    await asyncio.sleep(20)
    raise RuntimeError("连接超时了。。。")