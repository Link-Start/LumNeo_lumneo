# api/schemas/resources.py
# 管理/资源域接口的 Pydantic 数据契约（对应原 backend/routes 中各请求体模型）。
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


# ---------- chats ----------
class UpdateChatTitle(BaseModel):
    title: str


class AddMessageRequest(BaseModel):
    role: str
    content: Any
    plan_id: Optional[str] = None
    profile_id: Optional[int] = None
    model_id: Optional[str] = None
    file_ref: Optional[Any] = None
    turn_index: Optional[int] = None


class UpdateMessageRequest(BaseModel):
    content: Any
    file_ref: Optional[Any] = None
    plan_id: Optional[str] = None
    model_id: Optional[str] = None


# ---------- profiles ----------
class ProfileCreate(BaseModel):
    name: str
    avatar: str
    tools: List[str] = []
    profile_prompt: str = ""
    temperature: float = Field(default=1.0, ge=0.0, le=2.0)
    top_p: float = Field(default=1.0, ge=0.0, le=1.0)
    top_k: int = Field(default=40, ge=1, le=100)
    frequency_penalty: float = Field(default=0.0, ge=-2.0, le=2.0)
    presence_penalty: float = Field(default=0.0, ge=-2.0, le=2.0)


# ---------- models ----------
class ModelConfigBase(BaseModel):
    name: str
    type: str  # 'local' or 'online'
    modelName: Optional[str] = None
    baseUrl: str
    apiKey: str


class UpdateModelRequest(BaseModel):
    name: Optional[str] = None
    type: Optional[str] = None
    modelName: Optional[str] = None
    baseUrl: Optional[str] = None
    apiKey: Optional[str] = None


class ModelQuery(BaseModel):
    base_url: str
    api_key: str


# ---------- skills ----------
class UpdateSkillRequest(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    is_global: Optional[bool] = None


class BatchSelectRequest(BaseModel):
    profile_id: int
    selected_skill_ids: List[str]


# ---------- tool calls ----------
class BatchRequest(BaseModel):
    call_ids: List[str]


class ConfirmRequest(BaseModel):
    call_id: str
    confirmed: bool


# ---------- plans ----------
class UpdatePlanRequest(BaseModel):
    steps: List[Dict[str, Any]]


# ---------- workspace ----------
class WorkspaceRequest(BaseModel):
    path: str
