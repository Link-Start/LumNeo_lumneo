# src/lumneo/kernel/common/result.py
# Kernel / Common —— 通用 Result 原语（系统级共享类型）。
#
# 提供统一的成功/失败结果容器，供 Application / Domain / Infrastructure 边界之间
# 传递操作结果，避免使用零散的 dict 约定。
from dataclasses import dataclass, field
from typing import Generic, TypeVar, Optional

T = TypeVar("T")


@dataclass
class Result(Generic[T]):
    """统一的操作结果容器。"""

    success: bool
    data: Optional[T] = None
    error: Optional[str] = None
    code: str = ""

    @classmethod
    def ok(cls, data: Optional[T] = None) -> "Result[T]":
        return cls(success=True, data=data)

    @classmethod
    def fail(cls, error: str, code: str = "", data: Optional[T] = None) -> "Result[T]":
        return cls(success=False, error=error, code=code, data=data)

    def to_dict(self) -> dict:
        return {
            "success": self.success,
            "data": self.data,
            "error": self.error,
            "code": self.code,
        }


@dataclass
class Page(Generic[T]):
    """分页结果容器。"""

    items: list = field(default_factory=list)
    total: int = 0
    page: int = 1
    page_size: int = 50
