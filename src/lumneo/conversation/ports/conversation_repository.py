# conversation/ports/conversation_repository.py
# Repository Port（由领域拥有，§25）。
#
# 根据规范：Domain/Application → Repository Port → Persistence Repository。
# 这里定义稳定抽象；具体实现位于 persistence/repositories/。
from abc import ABC, abstractmethod
from typing import List, Optional

from lumneo.persistence.models.chat import ChatModel


class ConversationRepository(ABC):
    """对话（chats）持久化端口。"""

    @abstractmethod
    async def create(self, title: str = "新对话") -> ChatModel: ...

    @abstractmethod
    async def list(self) -> List[ChatModel]: ...

    @abstractmethod
    async def update_title(self, chat_id: str, title: str) -> None: ...

    @abstractmethod
    async def get(self, chat_id: str) -> Optional[ChatModel]: ...

    @abstractmethod
    async def delete(self, chat_id: str) -> List[str]:
        """删除对话，返回需要清理磁盘的（上传文件/工具目录）物理路径列表。"""
        ...
