# src/lumneo/infrastructure/network/http_client.py
# Network Adapter
#
# 对外部 HTTP 调用的统一封装。外部 SDK / 外部 API（如天气）通过它发起请求，
# 避免把具体网络库散落到各业务模块。依赖 httpx（OpenAI SDK 已间接提供）。
from typing import Any, Dict, Optional

import httpx

from lumneo.kernel.common.logger import logger
from lumneo.kernel.errors import InfrastructureError


class HttpClient:
    """轻量异步 HTTP 客户端适配器。"""

    def __init__(self, timeout: float = 15.0, verify: bool = True):
        self._timeout = timeout
        self._verify = verify

    async def get_json(self, url: str, params: Optional[Dict[str, Any]] = None,
                       headers: Optional[Dict[str, str]] = None) -> Any:
        try:
            async with httpx.AsyncClient(timeout=self._timeout, verify=self._verify) as client:
                resp = await client.get(url, params=params, headers=headers)
                resp.raise_for_status()
                return resp.json()
        except httpx.HTTPStatusError as e:
            raise InfrastructureError(
                f"HTTP 请求失败 [{e.response.status_code}]: {url}",
                code="HTTP_STATUS_ERROR",
            ) from e
        except httpx.HTTPError as e:
            logger.error(f"HTTP 请求异常: {url} -> {e}")
            raise InfrastructureError(
                f"HTTP 请求异常: {e}", code="HTTP_ERROR"
            ) from e

    async def get_text(self, url: str, params: Optional[Dict[str, Any]] = None,
                       headers: Optional[Dict[str, str]] = None) -> str:
        try:
            async with httpx.AsyncClient(timeout=self._timeout, verify=self._verify) as client:
                resp = await client.get(url, params=params, headers=headers)
                resp.raise_for_status()
                return resp.text
        except httpx.HTTPError as e:
            logger.error(f"HTTP 文本请求异常: {url} -> {e}")
            raise InfrastructureError(
                f"HTTP 请求异常: {e}", code="HTTP_ERROR"
            ) from e
