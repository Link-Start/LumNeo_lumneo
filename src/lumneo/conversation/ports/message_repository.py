# conversation/ports/message_repository.py
# Repository Port（领域拥有，§25）。
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional

from lumneo.persistence.models.message import MessageModel


class MessageRepository(ABC):
    """消息（messages）持久化端口。"""

    @abstractmethod
    async def get_by_chat(self, chat_id: str) -> List[MessageModel]: ...

    @abstractmethod
    async def add(
        self,
        chat_id: str,
        role: str,
        content: Any,
        profile_id: Optional[int] = None,
        plan_id: Optional[str] = None,
        model_id: Optional[str] = None,
        file_ref: Optional[dict] = None,
        turn_index: Optional[int] = None,
    ) -> MessageModel: ...

    @abstractmethod
    async def update(
        self,
        message_id: int,
        chat_id: str,
        content: Any = None,
        profile_id: Optional[int] = None,
        plan_id: Optional[str] = None,
        model_id: Optional[str] = None,
        file_ref: Optional[dict] = None,
    ) -> bool: ...

    @abstractmethod
    async def truncate(self, chat_id: str, from_turn_index: int) -> List[str]:
        """截断消息（含关联 plan/tool_calls 清理），返回需清理的磁盘文件路径列表。"""
        ...

    @abstractmethod
    async def delete_one(self, chat_id: str, turn_index: int) -> List[str]:
        """精准删除单轮消息，返回需清理的磁盘文件路径列表。"""
        ...
