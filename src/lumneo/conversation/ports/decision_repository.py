# src/lumneo/conversation/ports/decision_repository.py
# Repository Port（领域拥有，§25）。
from abc import ABC, abstractmethod
from typing import List, Optional

from lumneo.persistence.models.decision import DecisionModel


class DecisionRepository(ABC):
    """用户决策（user_decisions）持久化端口。"""

    @abstractmethod
    async def create(self, chat_id: Optional[str], turn_index: Optional[int],
                     message: str, timeout_seconds: int) -> int: ...

    @abstractmethod
    async def get_status(self, decision_id: int) -> Optional[str]: ...

    @abstractmethod
    async def update_status(self, decision_id: int, status: str) -> bool: ...

    @abstractmethod
    async def get(self, decision_id: int) -> Optional[DecisionModel]: ...

    @abstractmethod
    async def list_by_chat(self, chat_id: str, limit: int = 50) -> List[DecisionModel]: ...
