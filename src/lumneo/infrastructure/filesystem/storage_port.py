# src/lumneo/infrastructure/filesystem/storage_port.py
# Storage Port（基础设施抽象）
#
# 领域 / 工具通过此抽象访问本地文件系统，不直接依赖 pathlib / os 的具体实现，
# 未来可替换为 S3 / 对象存储而不影响上层。
from abc import ABC, abstractmethod
from typing import List, Optional


class StoragePort(ABC):
    """本地文件存储抽象。"""

    @abstractmethod
    def read_text(self, path: str, encoding: str = "utf-8") -> str: ...

    @abstractmethod
    def write_text(self, path: str, content: str, encoding: str = "utf-8") -> int: ...

    @abstractmethod
    def read_bytes(self, path: str) -> bytes: ...

    @abstractmethod
    def write_bytes(self, path: str, data: bytes) -> int: ...

    @abstractmethod
    def delete(self, path: str) -> bool: ...

    @abstractmethod
    def delete_many(self, paths: List[str]) -> List[str]: ...

    @abstractmethod
    def exists(self, path: str) -> bool: ...

    @abstractmethod
    def list_files(self, directory: str, recursive: bool = True,
                   pattern: Optional[str] = None) -> List[str]: ...

    @abstractmethod
    def write_under(self, root: str, relative_path: str, content: str,
                    encoding: str = "utf-8") -> str: ...

    @abstractmethod
    def read_under(self, root: str, relative_path: str, encoding: str = "utf-8") -> str: ...
