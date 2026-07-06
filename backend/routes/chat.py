# backend/routes/chat.py
import re
import json
import traceback
import os
from fastapi import APIRouter, HTTPException, Depends, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from typing import List, Dict, Optional, Any

from backend.services.llm_service import LLMService
from backend.services.tools import get_local_tools, get_mcp_tools, get_all_tools
from backend.db.profiles import get_profile_by_id
from backend.db.skills import get_skills_by_profile
from backend.utils.base import resource_path, get_current_time, get_local_ip
from config_loader import config
import backend

router = APIRouter(prefix="/api", tags=["chat"])

BASE_SYSTEM_PROMPT = ""
full_path = resource_path("system_prompt.md")
with open(full_path, 'r', encoding="utf-8") as f:
    BASE_SYSTEM_PROMPT = f.read()
BASE_SYSTEM_PROMPT = BASE_SYSTEM_PROMPT.replace("{{uploads_dir}}", str(config.uploads_dir))

disabled_tools = ['system_write_file', 'system_patch_file', 'system_create_project_tree', 'system_read_file_list']
default_tools = ['system_get_weather', 'system_read_file']

class ModelConfig(BaseModel):
    type: str
    model_name: str
    base_url: Optional[str] = None
    api_key: Optional[str] = None
    thinking: str = 'enabled'

class ChatRequest(BaseModel):
    messages: List[Dict[str, Any]]
    enable_tools: bool = False
    llm_config: Optional[ModelConfig] = None
    profile_id: Optional[int] = None
    message_id: Optional[int] = None

async def get_mcp_manager(request: Request):
    return request.app.state.mcp_manager

@router.post("/chat")
async def chat(
    request: ChatRequest,
    fastapi_request: Request,
    mcp_manager=Depends(get_mcp_manager)
):
    try:
        # 1. 创建 LLM 服务实例
        if request.llm_config:
            cfg = request.llm_config
            if cfg.type == "local":
                service = LLMService(
                    model_type="local", model_name=cfg.model_name,
                    base_url=cfg.base_url, api_key=cfg.api_key, thinking=cfg.thinking
                )
            else:
                if not cfg.api_key:
                    raise HTTPException(status_code=400, detail="线上模型必须提供 API Key")
                service = LLMService(
                    model_type="online", model_name=cfg.model_name,
                    base_url=cfg.base_url, api_key=cfg.api_key, thinking=cfg.thinking
                )
        else:
            service = LLMService.instance
            if not service:
                raise HTTPException(status_code=400, detail="请先选择或配置模型")

        # 2. 准备 System Prompt 和 Tools
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
                    system_prompt += f"\n\n ## 角色扮演 \n\n{profile.profile_prompt}"
                
                # --- 核心：加载并注入自定义技能 ---
                if request.enable_tools:
                    db_skills = await get_skills_by_profile(request.profile_id)
                    
                    skill_prompts_block = []
                    
                    for skill in db_skills:
                        # 1. 如果有 prompt_content (SKILL.md 正文)，注入到 System Prompt
                        if skill.prompt_content:
                            skill_prompts_block.append(
                                f"### 技能指令: {skill.name}\n"
                                f"{skill.prompt_content}"
                            )
                        
                        # 2. 如果有 skill.json (函数定义)，注入到 Tools 列表
                        if skill.metadata.get('has_function_definition'):
                            json_path = os.path.join(skill.file_path, "skill.json")
                            if os.path.exists(json_path):
                                try:
                                    with open(json_path, 'r', encoding='utf-8') as f:
                                        func_def = json.load(f)
                                        tools.append(func_def)
                                except Exception as e:
                                    print(f"加载 skill.json 失败 {skill.id}: {e}")
                    
                    # 将技能指令拼接到 System Prompt
                    if skill_prompts_block:
                        system_prompt += "\n\n ## 激活的技能 \n\n" + "\n\n".join(skill_prompts_block)

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

        print(system_prompt)
        # 插入最终的 System Prompt
        messages.insert(0, {"role": "system", "content": system_prompt})

        # 3. 流式响应
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
                message_id=request.message_id
            ),
            media_type="text/event-stream"
        )
    except Exception as e:
        print(e)
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
