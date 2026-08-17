# api/routes/chat.py
# 聊天 API 路由（薄层）。
#
# 仅负责 DTO 映射与协议转换，所有业务编排通过 conversation.facade 完成（§46-47）。
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse
from typing import List, Dict, Optional

from lumneo.api.schemas.chat import ChatRequest, DecisionUpdate
from lumneo.conversation.facade.conversation_facade import ConversationFacade


router = APIRouter(prefix="/api", tags=["chat"])


def _get_facade(request: Request) -> ConversationFacade:
    return request.app.state.facade


def _get_mcp_manager(request: Request):
    return getattr(request.app.state, "mcp_manager", None)


@router.post("/chat")
async def chat(chat_request: ChatRequest, request: Request):
    facade = _get_facade(request)
    mcp_manager = _get_mcp_manager(request)
    try:
        params = chat_request.params.model_dump(exclude_none=True) if chat_request.params else {}
        collaboration = chat_request.collaboration.model_dump(exclude_none=True) if chat_request.collaboration else None
        llm_config = chat_request.llm_config.model_dump() if chat_request.llm_config else None

        async def response_generator():
            async for chunk in await facade.generate_chat(
                messages=chat_request.messages,
                enable_tools=chat_request.enable_tools,
                llm_config=llm_config,
                profile_id=chat_request.profile_id,
                chat_id=chat_request.chat_id,
                turn_index=chat_request.turn_index,
                plan_id=chat_request.plan_id,
                is_executing_plan=chat_request.is_executing_plan,
                params=params,
                collaboration=collaboration,
                fastapi_request=request,
                mcp_manager=mcp_manager,
            ):
                yield chunk

        return StreamingResponse(response_generator(), media_type="text/event-stream")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"服务崩溃: {e}")


@router.get("/tools")
async def get_tools(request: Request):
    facade = _get_facade(request)
    return await facade.list_tools(_get_mcp_manager(request))


@router.get("/tools-info")
async def get_tools_info(request: Request):
    facade = _get_facade(request)
    return await facade.get_tools_info(_get_mcp_manager(request))


@router.get("/system-info")
async def get_system_info(request: Request):
    facade = _get_facade(request)
    return await facade.get_system_info()


@router.post("/decisions/update")
async def update_decision(decision: DecisionUpdate, request: Request):
    facade = _get_facade(request)
    try:
        return await facade.update_decision(decision.decision_id, decision.choice)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except RuntimeError as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/decisions")
async def get_decisions(chat_id: str, request: Request):
    facade = _get_facade(request)
    return await facade.get_decisions(chat_id)
