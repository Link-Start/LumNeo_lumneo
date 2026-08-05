# backend/routes/collaboration.py
import re
import random
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from typing import Optional, Dict, Any, List
from backend.db.models import list_models as list_models_db

router = APIRouter(prefix="/api", tags=["collaboration"])


class TriggerConditions(BaseModel):
    """触发条件配置"""
    complexity_threshold: float = Field(default=0.6, ge=0.0, le=1.0, description="复杂度阈值，超过则倾向云端模型")
    tool_heavy_priority: str = Field(default="cloud", description="工具密集型任务优先使用的模型类型: local/cloud")
    keyword_triggers: List[Dict[str, str]] = Field(
        default=[
            {"keyword": "代码", "target": "local"},
            {"keyword": "分析", "target": "cloud"},
            {"keyword": "总结", "target": "local"}
        ],
        description="关键词触发规则"
    )
    message_length_threshold: int = Field(default=500, ge=100, le=10000, description="消息长度阈值，超过则倾向云端")
    enable_complexity_detect: bool = Field(default=True, description="启用复杂度检测")
    enable_keyword_detect: bool = Field(default=True, description="启用关键词检测")
    enable_length_detect: bool = Field(default=True, description="启用长度检测")


class CollaborationConfigRequest(BaseModel):
    name: str = Field(default="默认协作策略")
    enabled: bool = Field(default=False)
    primary_model_id: str
    secondary_model_id: Optional[str] = None
    strategy: str = Field(default="auto", pattern="^(auto|primary|secondary|hybrid)$")
    local_ratio: int = Field(default=70, ge=0, le=100)
    conditions: Optional[Dict[str, Any]] = None
    fallback_enabled: bool = Field(default=True)


class CollaborationConfigResponse(BaseModel):
    id: int
    name: str
    enabled: bool
    primary_model_id: str
    secondary_model_id: Optional[str]
    strategy: str
    local_ratio: int
    conditions: Dict[str, Any]
    fallback_enabled: bool
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


# ========== 策略核心逻辑（内联避免循环导入）==========

def _estimate_complexity(message: str) -> float:
    """估算消息复杂度 0.0-1.0"""
    score = 0.0
    length = len(message)

    if length > 2000:
        score += 0.4
    elif length > 1000:
        score += 0.25
    elif length > 500:
        score += 0.1

    code_patterns = [
        r'```[\w\s\S]*?```',
        r'def\s+\w+\s*\(',
        r'class\s+\w+',
        r'function\s+\w+',
        r'import\s+\w+',
        r'#include',
        r'<[^>]+>.*?</[^>]+>',
    ]
    for pattern in code_patterns:
        if re.search(pattern, message, re.IGNORECASE):
            score += 0.15
            break

    complex_keywords = ['分析', '对比', '评估', '优化', '架构', '设计', '推理', '证明', '推导']
    for kw in complex_keywords:
        if kw in message:
            score += 0.08
            break

    step_patterns = [r'第[一二三四五六七八九十\d]+步', r'首先.*然后.*最后', r'步骤[\d一二三四五六七八九十]']
    for pattern in step_patterns:
        if re.search(pattern, message):
            score += 0.1
            break

    return min(score, 1.0)


def _check_keyword_triggers(message: str, triggers: List[Dict[str, str]]) -> Optional[str]:
    message_lower = message.lower()
    for rule in triggers:
        keyword = rule.get("keyword", "")
        target = rule.get("target", "")
        if keyword and keyword.lower() in message_lower:
            return target
    return None


async def _select_model_by_strategy(
    collab_config,
    message: str,
    enable_tools: bool,
    model_map: Dict[str, Dict]
) -> tuple:
    """
    根据协作策略选择模型
    返回: (selected_model_id, reason)
    """
    strategy = collab_config.strategy
    primary_id = collab_config.primary_model_id
    secondary_id = collab_config.secondary_model_id
    conditions = collab_config.conditions or {}
    local_ratio = collab_config.local_ratio

    primary_model = model_map.get(primary_id, {})
    secondary_model = model_map.get(secondary_id, {}) if secondary_id else {}
    primary_type = primary_model.get("type", "local")
    secondary_type = secondary_model.get("type", "cloud") if secondary_model else "cloud"

    if strategy == "primary":
        return primary_id, f"策略[固定主模型]: 始终使用 {primary_model.get('name', '主模型')}"

    if strategy == "secondary":
        if secondary_id and secondary_model:
            return secondary_id, f"策略[固定副模型]: 始终使用 {secondary_model.get('name', '副模型')}"
        return primary_id, "副模型未配置，回退到主模型"

    if strategy == "hybrid":
        primary_is_local = primary_type == "local"
        if primary_is_local:
            local_id, cloud_id = primary_id, secondary_id
            local_name = primary_model.get('name', '本地')
            cloud_name = secondary_model.get('name', '云端') if secondary_model else '云端'
        else:
            local_id, cloud_id = secondary_id, primary_id
            local_name = secondary_model.get('name', '本地') if secondary_model else '本地'
            cloud_name = primary_model.get('name', '云端')

        roll = random.randint(1, 100)
        if roll <= local_ratio:
            selected = local_id if local_id else primary_id
            return selected, f"策略[混合模式]: 随机占比 {roll}/100 ≤ {local_ratio}%，选择本地模型 {local_name}"
        else:
            selected = cloud_id if cloud_id else primary_id
            return selected, f"策略[混合模式]: 随机占比 {roll}/100 > {local_ratio}%，选择云端模型 {cloud_name}"

    # 自动模式
    reasons = []

    if conditions.get("enable_keyword_detect", True):
        triggers = conditions.get("keyword_triggers", [])
        keyword_target = _check_keyword_triggers(message, triggers)
        if keyword_target:
            target_id = primary_id if primary_type == keyword_target else secondary_id
            if target_id:
                target_model = model_map.get(target_id, {})
                return target_id, f"策略[自动-关键词触发]: 命中'{keyword_target}'类型规则，选择 {target_model.get('name', keyword_target)}"

    if conditions.get("enable_complexity_detect", True):
        complexity = _estimate_complexity(message)
        threshold = conditions.get("complexity_threshold", 0.6)
        if complexity >= threshold:
            cloud_id = secondary_id if secondary_type == "cloud" else (primary_id if primary_type == "cloud" else None)
            if cloud_id:
                cloud_model = model_map.get(cloud_id, {})
                reasons.append(f"复杂度{complexity:.2f}≥阈值{threshold}，倾向云端模型 {cloud_model.get('name', '')}")
                return cloud_id, f"策略[自动-复杂度检测]: {'; '.join(reasons)}"
        else:
            reasons.append(f"复杂度{complexity:.2f}<阈值{threshold}")

    if enable_tools and conditions.get("tool_heavy_priority", "cloud") == "cloud":
        cloud_id = secondary_id if secondary_type == "cloud" else (primary_id if primary_type == "cloud" else None)
        if cloud_id:
            cloud_model = model_map.get(cloud_id, {})
            return cloud_id, f"策略[自动-工具优先]: 启用工具调用，优先使用云端模型 {cloud_model.get('name', '')}"

    if conditions.get("enable_length_detect", True):
        length_threshold = conditions.get("message_length_threshold", 500)
        if len(message) > length_threshold:
            cloud_id = secondary_id if secondary_type == "cloud" else (primary_id if primary_type == "cloud" else None)
            if cloud_id:
                cloud_model = model_map.get(cloud_id, {})
                return cloud_id, f"策略[自动-长度检测]: 消息长度{len(message)}>{length_threshold}，使用云端模型 {cloud_model.get('name', '')}"

    return primary_id, f"策略[自动-默认回退]: {'; '.join(reasons) if reasons else '无特殊触发条件'}，使用主模型 {primary_model.get('name', '')}"


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

    selected_id, reason = await _select_model_by_strategy(
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