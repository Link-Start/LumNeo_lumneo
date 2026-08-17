# conversation/ports/tool_call_repository.py
# Repository Port（领域拥有，§25）。
from abc import ABC, abstractmethod
from typing import Dict, List, Optional

from lumneo.persistence.models.tool_call import ToolCallModel


class ToolCallRepository(ABC):
    """工具调用记录（tool_calls）持久化端口。"""

    @abstractmethod
    async def create(self, chat_id: str, call_id: str, tool_name: str) -> ToolCallModel: ...

    @abstractmethod
    async def update_arguments(self, call_id: str, arguments: Dict) -> None: ...

    @abstractmethod
    async def update_status(self, call_id: str, status: str) -> None: ...

    @abstractmethod
    async def update_full(self, call_id: str, **fields) -> Optional[ToolCallModel]: ...

    @abstractmethod
    async def get_status(self, call_id: str) -> Optional[str]: ...

    @abstractmethod
    async def get_by_id(self, call_id: str) -> Optional[ToolCallModel]:
        """按 call_id 取单条工具调用记录（含完整字段）。"""
        ...

    @abstractmethod
    async def list_by_call_ids(self, call_ids: List[str]) -> List[ToolCallModel]:
        """按 call_id 列表批量取记录。"""
        ...

    @abstractmethod
    async def delete_by_call_ids(self, call_ids: List[str]) -> List[str]:
        """批量删除工具调用记录，返回需清理的磁盘文件路径列表。"""
        ...

    @abstractmethod
    async def delete_by_chat_id(self, chat_id: str) -> List[str]:
        """删除某对话的全部工具调用记录，返回需清理的磁盘文件路径列表。"""
        ...
