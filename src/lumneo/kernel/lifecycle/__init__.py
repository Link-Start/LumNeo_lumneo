# kernel/lifecycle/__init__.py
# Kernel —— 生命周期原语（系统级共享类型）。
#
# 提供应用 / 组件生命周期状态定义与极简状态机，供 Bootstrap 与 Runtime 使用。
# 不承载任何业务启动/关闭逻辑（那属于 Bootstrap 与各 OS）。
from enum import Enum
from dataclasses import dataclass, field
from typing import Optional, Callable, List


class LifecycleState(str, Enum):
    """系统 / 组件生命周期状态。"""

    STARTING = "starting"
    READY = "ready"
    RUNNING = "running"
    STOPPING = "stopping"
    STOPPED = "stopped"
    FAILED = "failed"


@dataclass
class Lifecycle:
    """极简生命周期追踪器。"""

    state: LifecycleState = LifecycleState.STOPPED
    error: Optional[str] = None
    _listeners: List[Callable[[LifecycleState], None]] = field(default_factory=list, repr=False)

    def on_change(self, listener: Callable[[LifecycleState], None]) -> None:
        self._listeners.append(listener)

    def set(self, state: LifecycleState, error: Optional[str] = None) -> None:
        self.state = state
        self.error = error
        for listener in list(self._listeners):
            try:
                listener(state)
            except Exception:
                pass

    @property
    def is_ready(self) -> bool:
        return self.state in (LifecycleState.READY, LifecycleState.RUNNING)
