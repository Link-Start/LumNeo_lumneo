# backend/repositories/tool_call_repo.py
import json
from abc import ABC, abstractmethod
from typing import Dict, Optional
from backend.db.tool_calls import (
    create_tool_call,
    update_tool_call,
    update_tool_call_arguments,
    update_tool_call_status,
    get_tool_call_status,
)


class ToolCallRepository(ABC):
    @abstractmethod
    async def create(self, chat_id: str, call_id: str, tool_name: str) -> None:
        pass

    @abstractmethod
    async def update_arguments(self, call_id: str, arguments: Dict) -> None:
        pass

    @abstractmethod
    async def update_status(self, call_id: str, status: str) -> None:
        pass

    @abstractmethod
    async def update_full(
        self,
        call_id: str,
        arguments: Dict,
        result: str,
        status: str,
        execution_time: int,
        error_message: Optional[str],
        meta_data: Dict
    ) -> None:
        pass

    @abstractmethod
    async def get_status(self, call_id: str) -> Optional[str]:
        pass


class DBoolCallRepository(ToolCallRepository):
    async def create(self, chat_id: str, call_id: str, tool_name: str) -> None:
        await create_tool_call(chat_id, call_id, tool_name)

    async def update_arguments(self, call_id: str, arguments: Dict) -> None:
        # 将 dict 转为 JSON 字符串
        arguments_json = json.dumps(arguments, ensure_ascii=False)
        await update_tool_call_arguments(call_id, arguments_json)

    async def update_status(self, call_id: str, status: str) -> None:
        await update_tool_call_status(call_id, status)

    async def update_full(
        self,
        call_id: str,
        arguments: Dict,
        result: str,
        status: str,
        execution_time: int,
        error_message: Optional[str],
        meta_data: Dict
    ) -> None:
        # 将 dict 转为 JSON 字符串
        arguments_json = json.dumps(arguments, ensure_ascii=False) if arguments else "{}"
        meta_json = json.dumps(meta_data, ensure_ascii=False) if meta_data else "{}"
        await update_tool_call(
            call_id=call_id,
            arguments=arguments_json,
            result=result,
            status=status,
            execution_time=execution_time,
            error_message=error_message,
            meta_data=meta_json
        )

    async def get_status(self, call_id: str) -> Optional[str]:
        return await get_tool_call_status(call_id)