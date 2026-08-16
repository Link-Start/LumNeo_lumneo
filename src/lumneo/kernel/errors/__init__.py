# kernel/errors/__init__.py
# Kernel —— 基础错误契约（系统级原语）
#
# 根据《LumNeo V2 Architecture & Dependency Governance Specification》：
# - Kernel 只定义基础错误（§88），不承载业务逻辑。
# - 领域级错误（MemoryError / HardwareError / ConversationError）由各 OS 自行扩展，
#   且不得落入 kernel/（除非确属全局系统级错误）。
# - 基础设施错误（ConnectionError / SDKError / SerialError / DatabaseError）不得直接
#   泄漏到 API（§89），应由基础设施 → 应用/领域错误 → API 错误映射 进行转换。
from typing import Optional, Any


class LumNeoError(Exception):
    """LumNeo 所有自定义异常的基类。"""

    code: str = "LUMNEO_ERROR"
    http_status: int = 500

    def __init__(self, message: str = "", *, detail: Any = None, code: Optional[str] = None):
        super().__init__(message)
        self.message = message
        self.detail = detail
        if code is not None:
            self.code = code

    def to_dict(self) -> dict:
        return {
            "error": self.code,
            "message": self.message,
            "detail": self.detail,
        }


class ValidationError(LumNeoError):
    """请求参数 / 配置校验失败。"""

    code = "VALIDATION_ERROR"
    http_status = 400


class ConfigurationError(LumNeoError):
    """系统配置缺失或非法。"""

    code = "CONFIGURATION_ERROR"
    http_status = 500


class InfrastructureError(LumNeoError):
    """基础设施层（DB / 文件 / 网络 / SDK）异常的统一基类。"""

    code = "INFRASTRUCTURE_ERROR"
    http_status = 502


class NotFoundError(LumNeoError):
    """资源不存在。"""

    code = "NOT_FOUND"
    http_status = 404


class ConflictError(LumNeoError):
    """资源冲突（并发 / 重复）。"""

    code = "CONFLICT"
    http_status = 409


class PersistenceError(InfrastructureError):
    """持久化层异常（Database / ORM / SQL 相关），由基础设施层抛出。"""

    code = "PERSISTENCE_ERROR"


class FileSystemError(InfrastructureError):
    """文件系统操作异常。"""

    code = "FILE_SYSTEM_ERROR"


class ProviderError(InfrastructureError):
    """外部 Provider（LLM / 天气 / 网络）调用异常。"""

    code = "PROVIDER_ERROR"
