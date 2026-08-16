# api/routes/chats.py
# 聊天与消息管理路由（薄层，业务逻辑经 application.facade 完成，§46-47）。
from fastapi import APIRouter, HTTPException, Request

from lumneo.api.schemas.resources import UpdateChatTitle, AddMessageRequest, UpdateMessageRequest
from lumneo.application.facade import ApplicationFacade


router = APIRouter(prefix="/api/chats", tags=["chats"])


def _get_facade(request: Request) -> ApplicationFacade:
    return request.app.state.resource_facade


@router.post("/")
async def create_chat_route(request: Request):
    return await _get_facade(request).create_chat()


@router.patch("/{chat_id}")
async def update_chat_title_route(chat_id: str, data: UpdateChatTitle, request: Request):
    return await _get_facade(request).update_chat_title(chat_id, data.title)


@router.get("/")
async def list_chats_route(request: Request):
    return await _get_facade(request).list_chats()


@router.delete("/{chat_id}")
async def delete_chat_route(chat_id: str, request: Request):
    return await _get_facade(request).delete_chat(chat_id)


@router.get("/{chat_id}/messages")
async def get_messages_route(chat_id: str, request: Request):
    return await _get_facade(request).get_messages(chat_id)


@router.post("/{chat_id}/messages")
async def add_message_route(chat_id: str, req: AddMessageRequest, request: Request):
    return await _get_facade(request).add_message(
        chat_id=chat_id, role=req.role, content=req.content, profile_id=req.profile_id,
        plan_id=req.plan_id, model_id=req.model_id, file_ref=req.file_ref,
        turn_index=req.turn_index,
    )


@router.put("/{chat_id}/messages/{message_id}")
async def update_message_route(chat_id: str, message_id: int,
                               req: UpdateMessageRequest, request: Request):
    result = await _get_facade(request).update_message(
        message_id=message_id, chat_id=chat_id, content=req.content, file_ref=req.file_ref,
        plan_id=req.plan_id, model_id=req.model_id,
    )
    if not result:
        raise HTTPException(status_code=404, detail="Message not found")
    return result


@router.delete("/{chat_id}/messages/{turn_index}")
async def delete_message_route(chat_id: str, turn_index: int, request: Request):
    return await _get_facade(request).delete_messages_by_turn(chat_id, turn_index)


@router.get("/{chat_id}/messages/by-turn")
async def get_message_by_turn(chat_id: str, turn_index: int, request: Request):
    result = await _get_facade(request).get_message_by_turn(chat_id, turn_index)
    if not result:
        raise HTTPException(status_code=404, detail="Message not found")
    return result
