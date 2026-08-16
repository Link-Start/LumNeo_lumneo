# api/schemas/chat.py
# 聊天相关接口的 Pydantic 数据契约（原 backend/routes/chat.py 中的模型定义）。
from typing import List, Dict, Optional, Literal, Any
from pydantic import BaseModel, Field


class StrategyParams(BaseModel):
    """执行策略配置参数"""
    blueprint_mode: bool = Field(default=False, description="蓝图模式")
    approval_mode: bool = Field(default=True, description="审批模式")
    auto_decision: bool = Field(default=False, description="自主决策（低风险免审批）")
    max_iterations: int = Field(default=10, ge=1, le=500, description="最大迭代轮次")
    max_parallel: int = Field(default=5, ge=1, le=20, description="最大并行数")
    tool_timeout: int = Field(default=30, ge=5, le=600, description="工具超时（秒）")
    retry_count: int = Field(default=2, ge=0, le=10, description="自动重试次数")
    retry_delay: int = Field(default=1, ge=0, le=30, description="重试间隔（秒）")
    failure_threshold: int = Field(default=3, ge=1, le=20, description="连续失败阈值")
    failure_behavior: Literal['continue', 'stop', 'ask'] = Field(
        default='continue', description="失败后行为"
    )


class ModelConfig(BaseModel):
    type: str
    name: str
    model_id: str
    model_name: str
    base_url: Optional[str] = None
    api_key: Optional[str] = None
    thinking: str = 'enabled'
    reasoning_effort: str = 'high'


class CollaborationParams(BaseModel):
    """模型协作调度参数（前端每次请求携带）"""
    enabled: bool = False
    primary_model_id: str
    secondary_model_id: Optional[str] = None
    strategy: str = Field(default="auto", pattern="^(auto|primary|secondary|hybrid)$")
    primary_ratio: int = Field(default=70, ge=0, le=100)
    conditions: Optional[Dict[str, Any]] = None
    fallback_enabled: bool = True


class ChatRequest(BaseModel):
    messages: List[Dict[str, Any]]
    enable_tools: bool = False
    llm_config: Optional[ModelConfig] = None
    profile_id: Optional[int] = None
    message_id: Optional[int] = None
    chat_id: Optional[str] = None
    turn_index: Optional[int] = None
    plan_id: Optional[str] = None
    is_executing_plan: bool = False
    params: Optional[StrategyParams] = None
    collaboration: Optional[CollaborationParams] = None


class DecisionUpdate(BaseModel):
    decision_id: int
    choice: str  # 'continue' 或 'stop'


class ExecutePlanRequest(BaseModel):
    chat_id: str
    turn_index: int
    plan: List[Dict[Any, Any]]       # 用户编辑后的计划
    messages: List[Dict[str, Any]]   # 当前的对话历史
    profile_id: Optional[int] = None
    llm_config: Optional[ModelConfig] = None
    params: Optional[Dict[str, Any]] = None
