# backend/routes/chat.py
import re
import json
import traceback
import os
from fastapi import APIRouter, HTTPException, Depends, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from typing import List, Dict, Optional, Any
import backend
from backend.services.llm_service import LLMService
from backend.services.tools import get_local_tools, get_mcp_tools, get_all_tools
from backend.db.profiles import get_profile_by_id
from backend.db.skills import get_skills_by_profile
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
default_tools = ['system_get_weather', 'system_read_file', 'system_use_skill', 'system_execute_script']

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

class ModelConfig(BaseModel):
    type: str
    model_id: str
    model_name: str
    base_url: Optional[str] = None
    api_key: Optional[str] = None
    thinking: str = 'enabled'
    reasoning_effort: str = 'high'

class ChatRequest(BaseModel):
    messages: List[Dict[str, Any]]
    enable_tools: bool = False
    llm_config: Optional[ModelConfig] = None
    profile_id: Optional[int] = None
    message_id: Optional[int] = None
    chat_id: Optional[str] = None
    turn_index: Optional[int] = None

async def get_mcp_manager(request: Request):
    return request.app.state.mcp_manager

@router.post("/chat")
async def chat(
    request: ChatRequest,
    fastapi_request: Request,
    mcp_manager=Depends(get_mcp_manager)
):
    try:
        # 创建 LLM 服务实例
        if request.llm_config:
            cfg = request.llm_config
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

        # 初始化工具列表
        tools = []
        
        # 处理 Profile 和 Skills
        profile = None
        if request.profile_id is not None:
            profile = await get_profile_by_id(request.profile_id)
            if profile:
                # 注入角色 Prompt
                if profile.profile_prompt:
                    system_prompt += f"\n\n ## 当前角色人设 \n\n{profile.profile_prompt}"
                
                # --- 核心：加载技能（懒加载） ---
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

        # 合并所有工具 (系统工具 + 技能工具)
        final_tools = system_tools + tools

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

        # 插入最终的 System Prompt
        messages.insert(0, {"role": "system", "content": system_prompt})

        # 流式响应
        return StreamingResponse(
            service.generate_response(
                messages=messages,
                enable_tools=request.enable_tools,
                tools=final_tools,
                request=fastapi_request,
                mcp_manager=mcp_manager,
                params={
                    'temperature': profile.temperature,
                    'top_p': profile.top_p,
                    'top_k': profile.top_k,
                    'frequency_penalty': profile.frequency_penalty,
                    'presence_penalty': profile.presence_penalty,
                } if profile else {},
                profile_id=profile.id if profile else None,
                model_id=request.llm_config.model_id,
                chat_id=request.chat_id,
                turn_index=request.turn_index
            ),
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
