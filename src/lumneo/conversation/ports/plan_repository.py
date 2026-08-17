# src/lumneo/conversation/ports/plan_repository.py
# Repository Port（领域拥有，§25）。
from abc import ABC, abstractmethod
from typing import List, Optional


class PlanRepository(ABC):
    """计划（plans）持久化端口。"""

    @abstractmethod
    async def create(self, plan_id: str, chat_id: str, steps: List[dict]) -> bool: ...

    @abstractmethod
    async def update(self, plan_id: str, steps: List[dict]) -> bool: ...

    @abstractmethod
    async def get(self, plan_id: str) -> Optional[List[dict]]: ...
