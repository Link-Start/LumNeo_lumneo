# backend/routes/chat.py
import re
import json
import traceback
import os
import random
from fastapi import APIRouter, HTTPException, Depends, Request, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from typing import List, Dict, Optional, Literal, Any
import backend
from backend.services.llm_service import LLMService
from backend.services.tools import get_local_tools, get_mcp_tools, get_all_tools
from backend.db.profiles import get_profile_by_id
from backend.db.skills import get_skills_by_profile
from backend.db.decisions import update_decision_status, get_decision_status
from backend.db.models import list_models as list_models_db
from backend.utils.base import resource_path, get_current_time, get_local_ip
from config_loader import config
from backend.bootstrap import logger


router = APIRouter(prefix="/api", tags=["chat"])

BASE_SYSTEM_PROMPT = ""
full_path = resource_path("system_prompt.md")
with open(full_path, 'r', encoding="utf-8") as f:
    BASE_SYSTEM_PROMPT = f.read()
BASE_SYSTEM_PROMPT = BASE_SYSTEM_PROMPT.replace("{{uploads_dir}}", str(config.uploads_dir))

disabled_tools = ['system_write_file', 'system_patch_file', 'system_delete_file', 'system_create_project_tree', 'system_read_file_list']
default_tools = ['system_get_weather', 'system_read_file']

 # 需要转义 reasoning_effort 的模型名称列表
REASONING_EFFORT_MAPPING_MODELS = [
    "agnes-2.0-flash",
    # 可继续添加
]

# 转义映射规则
REASONING_EFFORT_MAP = {
    "high": "low",
    "xhigh": "high",
}

class StrategyParams(BaseModel):
    """执行策略配置参数"""
    blueprint_mode: bool = Field(default=False, description="蓝图模式")
    approval_mode: bool = Field(default=True, description="审批模式")
    auto_decision: bool = Field(default=False, description="自主决策（低风险免审批）")
    max_iterations: int = Field(default=10, ge=1, le=100, description="最大迭代轮次")
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
    local_ratio: int = Field(default=70, ge=0, le=100)
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

async def get_mcp_manager(request: Request):
    return request.app.state.mcp_manager


# ========== 模型协作策略核心逻辑 ==========

def _estimate_complexity(message: str) -> float:
    """估算消息复杂度 0.0-1.0"""
    score = 0.0
    length = len(message)

    # 长度因子
    if length > 2000:
        score += 0.4
    elif length > 1000:
        score += 0.25
    elif length > 500:
        score += 0.1

    # 代码/结构化内容检测
    code_patterns = [
        r'```[\w\s\S]*?```',  # 代码块
        r'def\s+\w+\s*\(',
        r'class\s+\w+',
        r'function\s+\w+',
        r'import\s+\w+',
        r'#include',
        r'<[^>]+>.*?</[^>]+>',  # XML/HTML
    ]
    for pattern in code_patterns:
        if re.search(pattern, message, re.IGNORECASE):
            score += 0.15
            break

    # 复杂任务关键词
    complex_keywords = ['分析', '对比', '评估', '优化', '架构', '设计', '推理', '证明', '推导']
    for kw in complex_keywords:
        if kw in message:
            score += 0.08
            break

    # 多步骤指示
    step_patterns = [r'第[一二三四五六七八九十\d]+步', r'首先.*然后.*最后', r'步骤[\d一二三四五六七八九十]']
    for pattern in step_patterns:
        if re.search(pattern, message):
            score += 0.1
            break

    return min(score, 1.0)


def _check_keyword_triggers(message: str, triggers: List[Dict[str, str]]) -> Optional[str]:
    """检查关键词触发规则，返回目标模型类型或None"""
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

    # 获取模型类型信息
    primary_model = model_map.get(primary_id, {})
    secondary_model = model_map.get(secondary_id, {}) if secondary_id else {}
    primary_type = primary_model.get("type", "local")
    secondary_type = secondary_model.get("type", "cloud") if secondary_model else "cloud"

    # 策略1: 固定主模型
    if strategy == "primary":
        return primary_id, f"策略[固定主模型]: 始终使用 {primary_model.get('name', '主模型')}"

    # 策略2: 固定副模型
    if strategy == "secondary":
        if secondary_id and secondary_model:
            return secondary_id, f"策略[固定副模型]: 始终使用 {secondary_model.get('name', '副模型')}"
        return primary_id, "副模型未配置，回退到主模型"

    # 策略3: 混合模式 - 按占比随机
    if strategy == "hybrid":
        # local_ratio 表示本地模型占比，需要判断主/副哪个是本地
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

    # 策略4: 自动模式 - 智能判断
    reasons = []

    # 4.1 关键词检测
    if conditions.get("enable_keyword_detect", True):
        triggers = conditions.get("keyword_triggers", [])
        keyword_target = _check_keyword_triggers(message, triggers)
        if keyword_target:
            target_id = primary_id if primary_type == keyword_target else secondary_id
            if target_id:
                target_model = model_map.get(target_id, {})
                return target_id, f"策略[自动-关键词触发]: 命中'{keyword_target}'类型规则，选择 {target_model.get('name', keyword_target)}"

    # 4.2 复杂度检测
    if conditions.get("enable_complexity_detect", True):
        complexity = _estimate_complexity(message)
        threshold = conditions.get("complexity_threshold", 0.6)
        if complexity >= threshold:
            # 复杂任务倾向云端
            cloud_id = secondary_id if secondary_type == "cloud" else (primary_id if primary_type == "cloud" else None)
            if cloud_id:
                cloud_model = model_map.get(cloud_id, {})
                reasons.append(f"复杂度{complexity:.2f}≥阈值{threshold}，倾向云端模型 {cloud_model.get('name', '')}")
                return cloud_id, f"策略[自动-复杂度检测]: {'; '.join(reasons)}"
        else:
            reasons.append(f"复杂度{complexity:.2f}<阈值{threshold}")

    # 4.3 工具调用检测
    if enable_tools and conditions.get("tool_heavy_priority", "cloud") == "cloud":
        cloud_id = secondary_id if secondary_type == "cloud" else (primary_id if primary_type == "cloud" else None)
        if cloud_id:
            cloud_model = model_map.get(cloud_id, {})
            return cloud_id, f"策略[自动-工具优先]: 启用工具调用，优先使用云端模型 {cloud_model.get('name', '')}"

    # 4.4 长度检测
    if conditions.get("enable_length_detect", True):
        length_threshold = conditions.get("message_length_threshold", 500)
        if len(message) > length_threshold:
            cloud_id = secondary_id if secondary_type == "cloud" else (primary_id if primary_type == "cloud" else None)
            if cloud_id:
                cloud_model = model_map.get(cloud_id, {})
                return cloud_id, f"策略[自动-长度检测]: 消息长度{len(message)}>{length_threshold}，使用云端模型 {cloud_model.get('name', '')}"

    # 默认回退到主模型
    return primary_id, f"策略[自动-默认回退]: {'; '.join(reasons) if reasons else '无特殊触发条件'}，使用主模型 {primary_model.get('name', '')}"


# ========== 聊天接口 ==========

@router.post("/chat")
async def chat(
    request: ChatRequest,
    fastapi_request: Request,
    mcp_manager=Depends(get_mcp_manager)
):
    try:
        cfg = request.llm_config
        collab_reason = None

        # ========== 模型协作策略介入 ==========
        # 执行已确认的计划时，跳过模型协作策略的自动切换
        if not request.is_executing_plan:
            # 优先使用请求体携带的协作参数（前端实时配置），否则回退到数据库
            collab_config = None
            if request.collaboration and request.collaboration.enabled:
                collab_config = request.collaboration

            if collab_config:
                models = await list_models_db()
                model_map = {m.id: m.to_dict() for m in models}

                # 获取最后一条用户消息用于判断
                last_user_msg = ""
                for msg in reversed(request.messages):
                    if msg.get("role") == "user":
                        content = msg.get("content", "")
                        if isinstance(content, str):
                            last_user_msg = content
                        elif isinstance(content, list):
                            for part in content:
                                if isinstance(part, dict) and part.get("type") == "text":
                                    last_user_msg = part.get("text", "")
                                    break
                        break

                selected_id, collab_reason = await _select_model_by_strategy(
                    collab_config, last_user_msg, request.enable_tools, model_map
                )

                # 如果选中的不是当前请求的模型，则替换
                if cfg is None or cfg.model_id != selected_id:
                    selected_model = model_map.get(selected_id)
                    if selected_model:
                        reasoning_effort = cfg.reasoning_effort if cfg else 'high'
                        model_name = selected_model.get('modelName', '')
                        if model_name and any(
                            re.search(pattern, model_name, re.IGNORECASE)
                            for pattern in REASONING_EFFORT_MAPPING_MODELS
                        ):
                            reasoning_effort = REASONING_EFFORT_MAP.get(reasoning_effort, reasoning_effort)

                        cfg = ModelConfig(
                            type=selected_model.get('type', 'local'),
                            model_id=selected_model.get('id'),
                            model_name=model_name,
                            base_url=selected_model.get('baseUrl'),
                            api_key=selected_model.get('apiKey'),
                            thinking='enabled',
                            reasoning_effort=reasoning_effort
                        )
                        logger.info(f"[协作策略] {collab_reason}")

        # 创建 LLM 服务实例
        if cfg:
            reasoning_effort = cfg.reasoning_effort
            if cfg.model_name and any(
                re.search(pattern, cfg.model_name, re.IGNORECASE) 
                for pattern in REASONING_EFFORT_MAPPING_MODELS
            ):
                reasoning_effort = REASONING_EFFORT_MAP.get(
                    reasoning_effort, reasoning_effort
                )
            if cfg.type == "local":
                service = LLMService(
                    model_type="local", model_name=cfg.model_name,
                    base_url=cfg.base_url, api_key=cfg.api_key, thinking=cfg.thinking, reasoning_effort=reasoning_effort
                )
            else:
                if not cfg.api_key:
                    raise HTTPException(status_code=400, detail="线上模型必须提供 API Key")
                service = LLMService(
                    model_type="online", model_name=cfg.model_name,
                    base_url=cfg.base_url, api_key=cfg.api_key, thinking=cfg.thinking, reasoning_effort=reasoning_effort
                )
        else:
            service = LLMService.instance
            if not service:
                raise HTTPException(status_code=400, detail="请先选择或配置模型")

        # 准备 System Prompt 和 Tools
        messages = request.messages.copy()

        # 基础 System Prompt
        system_prompt = BASE_SYSTEM_PROMPT.replace("{{workspace_path}}", backend.workspace_path)
        system_prompt = system_prompt.replace("{{time_now}}", get_current_time())

        # 如果协作策略介入，在系统提示中标注（帮助用户理解）
        if collab_reason:
            system_prompt += f"\n\n[系统提示] 当前由模型协作策略调度: {collab_reason}"

        # 处理 Profile 和 Skills
        profile = None
        has_available_skills = False
        if request.profile_id is not None:
            profile = await get_profile_by_id(request.profile_id)
            if profile:
                # 注入角色 Prompt
                if profile.profile_prompt:
                    system_prompt += f"\n\n ## 当前角色人设 \n\n{profile.profile_prompt}"

                # --- 加载技能（懒加载） ---
                if request.enable_tools:
                    db_skills = await get_skills_by_profile(request.profile_id)

                    # 存放技能的描述（轻量级）
                    skill_descriptions = []

                    for skill in db_skills:
                        # 1. 获取简短描述（优先 metadata，其次 prompt_content 首行，最后用名称）
                        desc = ""
                        if skill.metadata and isinstance(skill.metadata, dict):
                            desc = skill.metadata.get("description", "")
                        if not desc and skill.prompt_content:
                            # 取第一行作为描述
                            lines = skill.prompt_content.strip().split('\n')
                            desc = lines[0] if lines else skill.name
                        if not desc:
                            desc = skill.name


                        # 2. 构建技能条目
                        if skill.file_path:
                            # 新技能：有文件路径，只注入描述，提示读取 SKILL.md
                            skill_md_path = os.path.join(skill.file_path, "SKILL.md")
                            if os.path.exists(skill_md_path):
                                skill_descriptions.append(
                                    f"- 技能ID: `{skill.id}` | 名称：{skill.name} | 描述：{desc}"
                                )
                            else:
                                skill_descriptions.append(
                                    f"- 技能ID: `{skill.id}` | 名称：{skill.name} | 描述：{desc} (⚠️ 指令文件缺失，请检查)"
                                )

                    # 将新技能的描述块加入 system_prompt
                    if skill_descriptions:
                        system_prompt += "\n\n## 可用技能索引\n\n"
                        system_prompt += "\n".join(skill_descriptions)
                        has_available_skills = True

        # 处理系统工具
        local_tools = get_local_tools()
        system_tools = [t for t in local_tools if t["function"]["name"] in default_tools]

        if profile and request.enable_tools:
            # 筛选 Profile 允许的工具
            mcp_tools = await get_mcp_tools(mcp_manager) if request.enable_tools else []
            allowed_tools = profile.tools

            enable_tools = [t for t in local_tools if t["function"]["name"] in disabled_tools]
            enable_tools.extend(mcp_tools)

            use_tools = [t for t in enable_tools if t["function"]["name"] in allowed_tools]
            system_tools.extend(use_tools)

        skill_tools = []
        # 合并所有工具 (系统工具 + 技能工具)
        if has_available_skills:
            skill_tools = [t for t in local_tools if t["function"]["name"] in ['system_use_skill', 'system_execute_script']]
        final_tools = system_tools + skill_tools

        # 清理历史消息中的 reasoning block
        REASONING_BLOCK = re.compile(r'<!--reasoning:start-->.*?<!--reasoning:end:\d+\.?\d*-->', re.DOTALL)
        MISC_MARKERS = re.compile(r'<!--(?:token_usage|reasoning):[^>]*-->')

        for msg in messages:
            content = msg.get("content")
            if isinstance(content, str):
                content = REASONING_BLOCK.sub('', content)
                content = MISC_MARKERS.sub('', content)
                msg["content"] = content
            elif isinstance(content, list):
                for part in content:
                    if isinstance(part, dict) and part.get("type") == "text":
                        text = part["text"]
                        text = REASONING_BLOCK.sub('', text)
                        text = MISC_MARKERS.sub('', text)
                        part["text"] = text
            else:
                if msg.get("role") == "tool":
                    # 将对象转为 JSON 字符串
                    msg["content"] = json.dumps(content, ensure_ascii=False)
                else:
                    # 对于其他角色，如果出现意料外的类型，也转为字符串（或根据情况处理）
                    # 但通常 user/assistant 不应出现 dict，若出现也转为字符串避免出错
                    msg["content"] = json.dumps(content, ensure_ascii=False) if content is not None else ""

        base_params = {}
        if profile:
            base_params = {
                'temperature': profile.temperature,
                'top_p': profile.top_p,
                'top_k': profile.top_k,
                'frequency_penalty': profile.frequency_penalty,
                'presence_penalty': profile.presence_penalty,
            }
        strategy_params = {}
        if request.params:
            strategy_params = request.params.model_dump(exclude_none=True)

        final_params = {**base_params, **strategy_params}
        if request.params and request.params.blueprint_mode and request.plan_id is None:
            # 注入蓝图模式的 System Prompt 指令（要求包含 arguments）
            blueprint_instruction = """

## 蓝图模式
触发：任务需 ≥2 个工具协作时，输出以下 JSON 计划。

**严格规则**：
1. 只输出一个 JSON 数组，不要调用任何工具。
2. 每个步骤必须包含：`step_id`、`description`、`tool`。
3. 回复以 `<<<PLAN_START>>>` 开头，以 `<<<PLAN_END>>>` 结尾。
4. 输出计划后，立即停止生成，不要添加任何额外文字、解释或工具调用。

示例（查询天气并写入文件）：
<<<PLAN_START>>>
[
    {"step_id":1,"description":"查询北京的天气","tool":"system_get_weather"},
    {"step_id":2,"description":"将天气结果总结后写入文件","tool":"system_write_file"}
]
<<<PLAN_END>>>

            """
            # 将蓝图指令追加到 System Prompt 中
            system_prompt += blueprint_instruction

        # 插入最终的 System Prompt
        messages.insert(0, {"role": "system", "content": system_prompt})

        # ========== 包装流式响应，先发送实际使用的模型信息 ==========
        async def response_generator():
            # 如果协作策略切换了模型，先告知前端实际使用的模型
            if cfg and collab_reason:
                model_info = {
                    "model_id": cfg.model_id,
                    "model_name": cfg.model_name,
                    "type": cfg.type,
                    "reason": collab_reason
                }
                yield f"<!--model_info:{json.dumps(model_info, ensure_ascii=False)}-->"

            async for chunk in service.generate_response(
                messages=messages,
                enable_tools=request.enable_tools,
                tools=final_tools,
                request=fastapi_request,
                mcp_manager=mcp_manager,
                params=final_params,
                profile_id=profile.id if profile else None,
                model_id=cfg.model_id if cfg else None,
                chat_id=request.chat_id,
                turn_index=request.turn_index,
                blueprint_mode=request.params.blueprint_mode if request.params else False,
                plan_id=request.plan_id if request.plan_id else None,
                is_executing_plan=request.is_executing_plan
            ):
                yield chunk

        # 流式响应
        return StreamingResponse(
            response_generator(),
            media_type="text/event-stream"
        )
    except Exception as e:
        logger.error(f"对话服务错误：{e}")
        error_trace = traceback.format_exc()
        raise HTTPException(
            status_code=500, detail=f"服务崩溃: {error_trace}"
        )

@router.get("/tools")
async def get_tools(mcp_manager=Depends(get_mcp_manager)):
    local_tools = get_local_tools()
    enable_tools = [t for t in local_tools if t["function"]["name"] in disabled_tools]
    mcp_tools = await get_mcp_tools(mcp_manager)
    enable_tools.extend(mcp_tools)
    return {"tools": enable_tools}

@router.get("/tools-info")
async def get_tools_info(mcp_manager=Depends(get_mcp_manager)):
    all_tools = await get_all_tools(mcp_manager)
    tool_json = {}
    for tool in all_tools:
        tool_json[tool["function"]["name"]] = {
            'title': tool["function"]["title"],
            'description': tool["function"]["description"],
        }
    return tool_json

@router.get("/system-info")
async def get_system_info():
    return {
        "workspace_dir": backend.workspace_path,
        "upload_dir": config.uploads_dir,
        "local_ip": get_local_ip(),
    }


@router.post("/decisions/update")
async def update_decision(decision: DecisionUpdate):
    """用户决策回写接口"""
    if decision.choice not in ['continue', 'stop']:
        raise HTTPException(status_code=400, detail="无效的选择")

    status = await get_decision_status(decision.decision_id)
    if status is None:
        raise HTTPException(status_code=404, detail="决策不存在")
    if status != 'pending':
        raise HTTPException(status_code=400, detail="该决策已被处理")

    success = await update_decision_status(decision.decision_id, decision.choice)
    if not success:
        raise HTTPException(status_code=500, detail="更新失败")
    return {"success": True}

@router.get("/decisions")
async def get_decisions(chat_id: str = Query(..., description="对话 ID")):
    """获取某个对话的所有决策记录（按时间倒序）"""
    from backend.db.decisions import list_decisions_by_chat
    records = await list_decisions_by_chat(chat_id)
    return [r.to_dict() for r in records]