# kernel/events/__init__.py
# Kernel —— 系统级 Event Contract 与极简事件总线（系统原语）。
#
# 根据《LumNeo V2 架构规范》：
# - Kernel 只定义 Event Contract（§18），不负责业务 Handler。
# - 事件 Handler 必须属于其业务 Owner（memory/handlers、hardware/handlers ...）。
# - 跨系统异步通信优先使用 Event Contract（§54 / §86）。
#
# 这里提供一个极简的内存 EventBus（发布/订阅原语），供各 OS 在 Bootstrap 中注册
# 自己的 Handler 使用。EventBus 属于系统级基础设施，不属于任何业务 Handler。
from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Type, TypeVar

EventT = TypeVar("EventT", bound="Event")


@dataclass
class Event:
    """所有系统事件的基类。"""

    type: str = field(init=False)
    payload: dict = field(default_factory=dict)

    def __post_init__(self):
        self.type = self.__class__.__name__


# ───────────────────────── 系统级事件契约 ─────────────────────────
@dataclass
class ApplicationStartedEvent(Event):
    payload: dict = field(default_factory=dict)


@dataclass
class ApplicationStoppingEvent(Event):
    payload: dict = field(default_factory=dict)


@dataclass
class DeviceConnectedEvent(Event):
    device_id: str = ""
    metadata: dict = field(default_factory=dict)


@dataclass
class DeviceDisconnectedEvent(Event):
    device_id: str = ""


@dataclass
class MemoryCapturedEvent(Event):
    memory_id: str = ""
    chat_id: str = ""


@dataclass
class ToolExecutedEvent(Event):
    call_id: str = ""
    tool_name: str = ""
    status: str = ""


class EventBus:
    """极简内存事件总线（系统级原语，不含任何业务 Handler 逻辑）。"""

    def __init__(self) -> None:
        self._handlers: Dict[str, List[Callable[[Any], Any]]] = {}

    def subscribe(self, event_type: Type[EventT], handler: Callable[[EventT], Any]) -> None:
        self._handlers.setdefault(event_type.__name__, []).append(handler)

    def unsubscribe(self, event_type: Type[EventT], handler: Callable[[EventT], Any]) -> None:
        handlers = self._handlers.get(event_type.__name__, [])
        if handler in handlers:
            handlers.remove(handler)

    async def publish(self, event: Event) -> None:
        for handler in list(self._handlers.get(event.type, [])):
            try:
                result = handler(event)
                if asyncio.iscoroutine(result):
                    await result
            except Exception:
                # 事件分发失败不应阻断主流程；具体错误处理由 Handler Owner 负责。
                pass
