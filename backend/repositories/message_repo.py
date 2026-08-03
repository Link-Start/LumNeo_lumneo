# backend/repositories/message_repo.py
from abc import ABC, abstractmethod
from typing import Optional
from backend.db.messages import add_message


class MessageRepository(ABC):
    @abstractmethod
    async def add_assistant_message(
        self,
        chat_id: str,
        content: str,
        profile_id: Optional[int],
        plan_id: Optional[str],
        model_id: Optional[str],
        turn_index: int,
        file_ref: Optional[str] = None
    ) -> None:
        pass


class DBMessageRepository(MessageRepository):
    async def add_assistant_message(
        self,
        chat_id: str,
        content: str,
        profile_id: Optional[int],
        plan_id: Optional[str],
        model_id: Optional[str],
        turn_index: int,
        file_ref: Optional[str] = None
    ) -> None:
        await add_message(chat_id, "assistant", content, profile_id, plan_id, model_id, file_ref, turn_index)