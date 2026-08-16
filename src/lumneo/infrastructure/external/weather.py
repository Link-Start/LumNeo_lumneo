# infrastructure/external/weather.py
# Weather Provider Adapter（§37 / §38 / §60）。
#
# 外部天气 API 适配器。对外暴露 WeatherProvider 抽象，运行时工具只依赖抽象，
# 具体网络请求（httpx）集中在基础设施层，避免业务模块直接做 HTTP I/O。
from abc import ABC, abstractmethod
from typing import Any, Dict, Optional

from lumneo.infrastructure.network.http_client import HttpClient


class WeatherProvider(ABC):
    """天气数据获取抽象。"""

    @abstractmethod
    async def get_weather(self, location: str, days: int = 1) -> Dict[str, Any]: ...


class WttrInWeatherAdapter(WeatherProvider):
    """基于 wttr.in 的天气适配器（纯文本结果）。"""

    def __init__(self, http_client: Optional[HttpClient] = None):
        self._http = http_client or HttpClient()

    async def get_weather(self, location: str, days: int = 1) -> Dict[str, Any]:
        url = f"https://wttr.in/{location}?T&{days}"
        try:
            text = await self._http.get_text(url)
            return {"success": True, "content": text}
        except Exception:
            return {"success": False, "content": "查询天气失败"}


# 模块级便捷函数（供工具注册表按签名 get_weather(location, days) 直接装载）。
# 运行时工具只依赖基础设施层暴露的能力，不直接持有网络客户端。
async def get_weather(location: str, days: int = 1) -> Dict[str, Any]:
    """获取指定地点天气（默认 wttr.in 适配器）。"""
    adapter = WttrInWeatherAdapter()
    return await adapter.get_weather(location, days)
