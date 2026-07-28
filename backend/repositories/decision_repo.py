from abc import ABC, abstractmethod
from typing import Optional
from backend.db.decisions import create_decision, get_decision_status


class DecisionRepository(ABC):
    @abstractmethod
    async def create(self, chat_id: Optional[str], turn_index: Optional[int],
                     message: str, timeout_seconds: int) -> str:
        pass

    @abstractmethod
    async def get_status(self, decision_id: str) -> Optional[str]:
        pass


class DBDecisionRepository(DecisionRepository):
    async def create(self, chat_id: Optional[str], turn_index: Optional[int],
                     message: str, timeout_seconds: int) -> str:
        return await create_decision(chat_id, turn_index, message, timeout_seconds)

    async def get_status(self, decision_id: str) -> Optional[str]:
        return await get_decision_status(decision_id)