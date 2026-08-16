# kernel/identity/__init__.py
# Kernel —— 身份原语（系统级共享类型）。
#
# 提供 User / System / Device / Scope(Tenant) 等身份抽象，供需要身份语义的模块使用。
# 这里只定义轻量数据结构，不承载任何业务身份逻辑。
from dataclasses import dataclass, field
from typing import Optional, Dict, Any


@dataclass
class Identity:
    """身份基类。"""

    id: str
    kind: str = "generic"
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class UserIdentity(Identity):
    kind: str = "user"
    name: str = ""


@dataclass
class SystemIdentity(Identity):
    kind: str = "system"
    version: str = ""


@dataclass
class DeviceIdentity(Identity):
    kind: str = "device"
    device_type: str = ""
    capabilities: list = field(default_factory=list)


@dataclass
class ScopeIdentity(Identity):
    """租户 / 作用域身份。"""

    kind: str = "scope"
    tenant: str = ""
