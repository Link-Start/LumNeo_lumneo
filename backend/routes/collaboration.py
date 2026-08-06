# backend/routes/collaboration.py
from fastapi import APIRouter
from pydantic import BaseModel, Field
from typing import Optional, Dict, Any, List
from backend.db.models import list_models as list_models_db
from backend.utils.collaboration_strategy import select_model_by_strategy


router = APIRouter(prefix="/api", tags=["collaboration"])

class TriggerConditions(BaseModel):
    """触发条件配置"""
    complexity_threshold: float = Field(default=0.6, ge=0.0, le=1.0, description="复杂度阈值，超过则倾向副模型")
    tool_heavy_priority: str = Field(default="secondary", description="工具密集型任务优先使用的模型类型: primary/secondary")
    keyword_triggers: List[Dict[str, str]] = Field(
        default=[
            {"keyword": "代码", "target": "primary"},
            {"keyword": "分析", "target": "secondary"},
            {"keyword": "总结", "target": "primary"}
        ],
        description="关键词触发规则"
    )
    message_length_threshold: int = Field(default=500, ge=100, le=10000, description="消息长度阈值，超过则倾向副模型")
    enable_complexity_detect: bool = Field(default=True, description="启用复杂度检测")
    enable_keyword_detect: bool = Field(default=True, description="启用关键词检测")
    enable_length_detect: bool = Field(default=True, description="启用长度检测")


class CollaborationConfigRequest(BaseModel):
    name: str = Field(default="默认协作策略")
    enabled: bool = Field(default=False)
    primary_model_id: str
    secondary_model_id: Optional[str] = None
    strategy: str = Field(default="auto", pattern="^(auto|primary|secondary|hybrid)$")
    primary_ratio: int = Field(default=70, ge=0, le=100)
    conditions: Optional[Dict[str, Any]] = None
    fallback_enabled: bool = Field(default=True)


class CollaborationConfigResponse(BaseModel):
    id: int
    name: str
    enabled: bool
    primary_model_id: str
    secondary_model_id: Optional[str]
    strategy: str
    primary_ratio: int
    conditions: Dict[str, Any]
    fallback_enabled: bool
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


@router.post("/collaboration/preview")
async def preview_selection(req: Dict[str, Any]):
    """
    预览：根据前端传来的协作参数，返回会选择哪个模型
    请求体: {
        "message": "用户消息",
        "enable_tools": false,
        "collaboration": { ...协作参数... }
    }
    """
    collab = req.get("collaboration")
    if not collab or not collab.get("enabled"):
        return {"strategy": "disabled", "selected": None, "reason": "协作模式未启用"}

    models = await list_models_db()
    model_map = {m.id: m.to_dict() for m in models}

    message = req.get("message", "")
    enable_tools = req.get("enable_tools", False)

    # 构造一个类似 CollaborationRecord 的对象传给策略选择器
    class _FakeConfig:
        pass
    config = _FakeConfig()
    for k, v in collab.items():
        setattr(config, k, v)

    selected_id, reason = await select_model_by_strategy(
        config, message, enable_tools, model_map
    )

    return {
        "strategy": collab.get("strategy"),
        "selected": model_map.get(selected_id),
        "selected_id": selected_id,
        "reason": reason,
        "primary_model": model_map.get(collab.get("primary_model_id")),
        "secondary_model": model_map.get(collab.get("secondary_model_id"))
    }