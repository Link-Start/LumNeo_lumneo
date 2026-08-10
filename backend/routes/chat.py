# backend/routes/chat.py
import re
import json
import traceback
import os
import asyncio
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
from backend.utils.base import resource_path, get_current_time, get_local_ip, get_typeName
from backend.utils.collaboration_strategy import select_model_by_strategy
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
    mode: str = "chat"           # "life" | "chat"
    project_tag: Optional[str] = None
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


async def _after_chat_memory_task(
    request,
    messages: list,
    fastapi_request: Request,
    cfg,
):
    """
    对话结束后异步执行：提取记忆、写入 Timeline、更新 State。
    失败静默处理，不打断用户。
    """
    memory_mgr = fastapi_request.app.state.memory_manager
    if not memory_mgr:
        return
    
    scope = "life" if request.mode == "life" else "work"
    
    try:
        # 1. Life Mode：写入 Timeline
        if request.mode == "life":
            from datetime import datetime
            from backend.memory.utils import sensitivity_precheck
            
            user_messages = [m for m in messages if m.get("role") == "user"]
            timeline_content = "\n\n".join(
                f"- {m.get('content', '')}" for m in user_messages[-5:]
            )
            
            sensitivity = sensitivity_precheck(timeline_content)
            today = datetime.now().strftime("%Y-%m-%d")
            
            await memory_mgr.write_timeline(
                date_str=today,
                content=timeline_content,
                sensitivity=sensitivity,
            )
        
        # 2. 异步提取记忆（调用 LLM）
        # 创建用于提取的 LLMService 实例
        from backend.services.llm_service import LLMService
        from backend.memory import MemoryExtractor
        
        extract_service = None
        if cfg:
            extract_service = LLMService(
                model_type="local" if cfg.type == "local" else "online",
                model_name=cfg.model_name,
                base_url=cfg.base_url,
                api_key=cfg.api_key or "",
                thinking="enabled",
                reasoning_effort="high",
            )
        elif LLMService.instance:
            extract_service = LLMService.instance
        
        if extract_service:
            extractor = MemoryExtractor(llm_service=extract_service)
            extracted = await extractor.extract(
                messages=messages,
                scope=scope,
                chat_id=request.chat_id,
                source_project=request.project_tag,
            )
            
            # 写入 memory
            for item in extracted:
                category = item.get("category", "fact")
                key = item.get("key", "未命名")
                content = item.get("content", "")
                
                # 过滤 frontmatter 字段
                fm_data = {k: v for k, v in item.items() 
                          if k not in ("category", "key", "content")}
                
                await memory_mgr.create_memory(
                    scope=scope,
                    category=category,
                    key=key,
                    content=content,
                    frontmatter_data=fm_data,
                )
            
            # 同步更新 FTS5 索引
            fts_mgr = fastapi_request.app.state.fts_manager
            if fts_mgr and extracted:
                pass
        
        # 3. Life Mode：更新 state.md
        if request.mode == "life":
            from backend.memory import StateManager
            state_mgr = StateManager()
            
            # 创建用于 state 评估的 LLMService
            state_service = None
            if cfg:
                state_service = LLMService(
                    model_type="local" if cfg.type == "local" else "online",
                    model_name=cfg.model_name,
                    base_url=cfg.base_url,
                    api_key=cfg.api_key or "",
                    thinking="enabled",
                    reasoning_effort="high",
                )
            elif LLMService.instance:
                state_service = LLMService.instance
            
            if state_service:
                await state_mgr.update_state(
                    llm_service=state_service,
                    messages=messages,
                )
                
    except Exception as e:
        logger.warning(f"记忆提取失败: {e}")
        pass

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
        # 显式初始化 collab_config，避免 is_executing_plan=True 时 UnboundLocalError
        collab_config = None
        # 保存用户原始请求的 reasoning_effort，避免协作策略覆盖后丢失
        original_reasoning_effort = request.llm_config.reasoning_effort if request.llm_config else 'high'

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

                selected_id, collab_reason = await select_model_by_strategy(
                    collab_config, last_user_msg, request.enable_tools, model_map
                )

                # 如果选中的不是当前请求的模型，则替换
                if cfg is None or cfg.model_id != selected_id:
                    selected_model = model_map.get(selected_id)
                    if selected_model:
                        reasoning_effort = original_reasoning_effort
                        model_name = selected_model.get('modelName', '')
                        if model_name and any(
                            re.search(pattern, model_name, re.IGNORECASE)
                            for pattern in REASONING_EFFORT_MAPPING_MODELS
                        ):
                            reasoning_effort = REASONING_EFFORT_MAP.get(reasoning_effort, reasoning_effort)

                        cfg = ModelConfig(
                            type=selected_model.get('type', 'local'),
                            name=selected_model.get('name', ''),
                            model_id=selected_model.get('id'),
                            model_name=model_name,
                            base_url=selected_model.get('baseUrl'),
                            api_key=selected_model.get('apiKey'),
                            thinking='enabled',
                            reasoning_effort=reasoning_effort
                        )
                        # logger.info(f"[协作策略] {collab_reason}")

        # 保存主模型配置，用于故障回退
        primary_cfg = None
        if collab_config and collab_config.fallback_enabled:
            primary_model = model_map.get(collab_config.primary_model_id) if 'model_map' in locals() else None
            if primary_model and (cfg is None or cfg.model_id != primary_model.get('id')):
                reasoning_effort = original_reasoning_effort
                p_name = primary_model.get('modelName', '')
                if p_name and any(
                    re.search(pattern, p_name, re.IGNORECASE)
                    for pattern in REASONING_EFFORT_MAPPING_MODELS
                ):
                    reasoning_effort = REASONING_EFFORT_MAP.get(reasoning_effort, reasoning_effort)
                primary_cfg = ModelConfig(
                    type=primary_model.get('type', 'local'),
                    name=primary_model.get('name', ''),
                    model_id=primary_model.get('id'),
                    model_name=p_name,
                    base_url=primary_model.get('baseUrl'),
                    api_key=primary_model.get('apiKey'),
                    thinking='enabled',
                    reasoning_effort=reasoning_effort
                )

        # 创建 LLM 服务实例（故障回退时会在 _call_with_model 中重新创建）
        if not cfg:
            # 无协作策略时，使用用户选中的模型或全局实例
            service = LLMService.instance
            if not service:
                raise HTTPException(status_code=400, detail="请先选择或配置模型")
            # 包装为统一接口
            async def _call_with_model(model_cfg: ModelConfig):
                async for chunk in service.generate_response(
                    messages=messages,
                    enable_tools=request.enable_tools,
                    tools=final_tools,
                    request=fastapi_request,
                    mcp_manager=mcp_manager,
                    params=final_params,
                    profile_id=profile.id if profile else None,
                    model_id=model_cfg.model_id if model_cfg else None,
                    chat_id=request.chat_id,
                    turn_index=request.turn_index,
                    blueprint_mode=request.params.blueprint_mode if request.params else False,
                    plan_id=request.plan_id if request.plan_id else None,
                    is_executing_plan=request.is_executing_plan
                ):
                    yield chunk

            async def response_generator():
                async for chunk in _call_with_model(cfg):
                    yield chunk

            return StreamingResponse(response_generator(), media_type="text/event-stream")

        # 使用深拷贝，避免修改原始请求中的消息对象
        import copy
        messages = copy.deepcopy(request.messages)

        # 保存一份不含 System Prompt 的原始对话消息，用于后续记忆提取
        # 避免将 System Prompt 内容混入记忆库
        chat_messages_for_memory = copy.deepcopy(request.messages)

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

        # ========== 记忆检索注入 ==========
        memory_mgr = fastapi_request.app.state.memory_manager
        fts_mgr = fastapi_request.app.state.fts_manager
        
        if memory_mgr:
            from backend.memory import MemoryRetriever, StateManager
            
            retriever = MemoryRetriever(memory_mgr, fts_mgr)
            
            # 获取最后一条用户消息作为检索 query
            last_user_msg = ""
            for msg in reversed(request.messages):
                if msg.get("role") == "user":
                    content = msg.get("content", "")
                    if isinstance(content, str):
                        last_user_msg = content
                    break
            
            memory_block = ""
            state_block = ""
            
            if request.mode == "life":
                # Life Mode：检索 life + work，加载 state
                memory_block = await retriever.retrieve_for_life(last_user_msg)
                
                # 读取 state.md
                state_mgr = StateManager()
                state_data = await state_mgr.read_state()
                state_block = state_mgr.format_state_for_prompt(state_data)
            else:
                # Chat Mode：仅检索 work，带 project_tag 过滤
                memory_block = await retriever.retrieve_for_chat(
                    last_user_msg,
                    project_tag=request.project_tag,
                )
                # logger.info(f"检索结果: {memory_block}")
            
            # 将记忆块追加到 System Prompt
            if state_block:
                system_prompt += "\n\n" + state_block
            if memory_block:
                system_prompt += "\n\n" + memory_block
        # ==========================================

        # 插入最终的 System Prompt
        messages.insert(0, {"role": "system", "content": system_prompt})

        # ========== 包装流式响应，先发送实际使用的模型信息，支持故障回退 ==========
        async def _call_with_model(model_cfg: ModelConfig):
            """用指定模型配置创建服务并调用生成"""
            reasoning_effort = model_cfg.reasoning_effort
            if model_cfg.model_name and any(
                re.search(pattern, model_cfg.model_name, re.IGNORECASE)
                for pattern in REASONING_EFFORT_MAPPING_MODELS
            ):
                reasoning_effort = REASONING_EFFORT_MAP.get(reasoning_effort, reasoning_effort)

            if model_cfg.type == "local":
                svc = LLMService(
                    model_type="local", model_name=model_cfg.model_name,
                    base_url=model_cfg.base_url, api_key=model_cfg.api_key,
                    thinking=model_cfg.thinking, reasoning_effort=reasoning_effort
                )
            else:
                if not model_cfg.api_key:
                    raise HTTPException(status_code=400, detail="线上模型必须提供 API Key")
                svc = LLMService(
                    model_type="online", model_name=model_cfg.model_name,
                    base_url=model_cfg.base_url, api_key=model_cfg.api_key,
                    thinking=model_cfg.thinking, reasoning_effort=reasoning_effort
                )

            gen = svc.generate_response(
                messages=messages,
                enable_tools=request.enable_tools,
                tools=final_tools,
                request=fastapi_request,
                mcp_manager=mcp_manager,
                params=final_params,
                profile_id=profile.id if profile else None,
                model_id=model_cfg.model_id,
                chat_id=request.chat_id,
                turn_index=request.turn_index,
                blueprint_mode=request.params.blueprint_mode if request.params else False,
                plan_id=request.plan_id if request.plan_id else None,
                is_executing_plan=request.is_executing_plan
            )

            # 手动迭代：检测到 orchestrator 内部吞掉的错误消息时，转成异常抛出以触发回退
            try:
                while True:
                    chunk = await gen.__anext__()
                    # orchestrator 在超时/异常时会 yield "❌ 模型服务错误..."
                    if chunk.startswith("❌ 模型服务错误") or chunk.startswith("\n❌ 模型服务错误"):
                        raise Exception(f"模型 {model_cfg.model_name} 服务错误: {chunk.strip()}")
                    yield chunk
            except StopAsyncIteration:
                pass

        async def response_generator():
            current_cfg = cfg
            current_reason = collab_reason

            # 发送当前选用的模型信息
            if current_cfg and current_reason:
                model_info = {
                    "model_id": current_cfg.model_id,
                    "model_name": current_cfg.model_name,
                    "type": current_cfg.type,
                    "reason": current_reason
                }
                yield f"<!--model_info:{json.dumps(model_info, ensure_ascii=False)}-->"

            try:
                async for chunk in _call_with_model(current_cfg):
                    yield chunk
            except Exception as e:
                # 故障回退：如果当前不是主模型且开启了回退，尝试主模型
                if (primary_cfg and 
                    current_cfg and 
                    current_cfg.model_id != primary_cfg.model_id):
                    # logger.warning(f"[故障回退] 模型 {current_cfg.model_name} 调用失败: {str(e)[:200]}，尝试回退到主模型 {primary_cfg.model_name}")
                    # logger.info(f"故障回退主模型配置: {primary_cfg}")
                    fallback_reason = f"[故障回退] 原模型调用失败，已切换至主模型 「 {primary_cfg.name} · {get_typeName(primary_cfg.type)} 」"
                    fallback_info = {
                        "model_id": primary_cfg.model_id,
                        "model_name": primary_cfg.model_name,
                        "type": primary_cfg.type,
                        "reason": fallback_reason
                    }
                    yield f"<!--model_info:{json.dumps(fallback_info, ensure_ascii=False)}-->"

                    async for chunk in _call_with_model(primary_cfg):
                        yield chunk
                else:
                    # 无法回退：错误消息已 yield 给用户，直接结束不再抛 500
                    error_msg = f"模型 {current_cfg.name if current_cfg else '未知'} 调用失败，且无法回退到主模型。错误：{str(e)[:300]}"
                    yield f"<!--error:{json.dumps({'message': error_msg}, ensure_ascii=False)}-->"
                    return
            
            # === 流式结束后异步提取记忆 ===
            # 保存 Task 引用，避免被 GC 提前回收且便于异常追踪
            memory_task = asyncio.create_task(_after_chat_memory_task(
                request=request,
                messages=chat_messages_for_memory,
                fastapi_request=fastapi_request,
                cfg=current_cfg,
            ))
            # 将任务存入 app.state，防止被垃圾回收
            if not hasattr(fastapi_request.app.state, 'background_tasks'):
                fastapi_request.app.state.background_tasks = set()
            fastapi_request.app.state.background_tasks.add(memory_task)
            # 添加回调，完成后从集合中移除
            def _remove_task(t):
                fastapi_request.app.state.background_tasks.discard(t)
            memory_task.add_done_callback(_remove_task)
            # =============================================

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
    dangerous_tools = [t for t in local_tools if t["function"]["name"] in disabled_tools]
    mcp_tools = await get_mcp_tools(mcp_manager)
    dangerous_tools.extend(mcp_tools)
    return {"tools": dangerous_tools}

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