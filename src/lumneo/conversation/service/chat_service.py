# src/lumneo/conversation/service/chat_service.py
#
# 负责：模型协作策略选择、System Prompt 与技能注入、工具按 Profile 筛选、消息清理、
# 按模型配置构建 LLMProvider + LLMOrchestrator、流式响应与故障回退。
# 它依赖注入的 Repository Port 与运行时共享组件，不直接 import 数据库 / 文件 I/O。
import re
import json
from typing import Dict, List, Optional, AsyncGenerator, Any

from lumneo.infrastructure.providers.openai_provider import OpenAIProvider
from lumneo.runtime.agent.orchestrator import LLMOrchestrator
from lumneo.runtime.tools.registry import get_local_tools, get_mcp_tools
from lumneo.runtime.context.prompt import (
    build_system_prompt, clean_messages, disabled_tools, default_tools,
    resolve_reasoning_effort,
)
from lumneo.runtime.context.collaboration import select_model_by_strategy
from lumneo.conversation.ports.decision_repository import DecisionRepository
from lumneo.conversation.ports.message_repository import MessageRepository
from lumneo.conversation.ports.plan_repository import PlanRepository
from lumneo.conversation.ports.profile_repository import ProfileRepository
from lumneo.conversation.ports.provider_repository import ProviderRepository
from lumneo.conversation.ports.skill_repository import SkillRepository
from lumneo.kernel.common.util import get_typeName


class ChatService:
    def __init__(
        self,
        *,
        tool_executor,
        stream_parser,
        approval_handler,
        persister,
        suggestion_gen,
        decision_repo: DecisionRepository,
        message_repo: MessageRepository,
        plan_repo: PlanRepository,
        profile_repo: ProfileRepository,
        provider_repo: ProviderRepository,
        skill_repo: SkillRepository,
    ):
        self.tool_executor = tool_executor
        self.stream_parser = stream_parser
        self.approval_handler = approval_handler
        self.persister = persister
        self.suggestion_gen = suggestion_gen
        self.decision_repo = decision_repo
        self.message_repo = message_repo
        self.plan_repo = plan_repo
        self.profile_repo = profile_repo
        self.provider_repo = provider_repo
        self.skill_repo = skill_repo

    # ───────────────────────── 内部工具 ─────────────────────────

    @staticmethod
    def _build_provider(cfg: Dict[str, Any]) -> OpenAIProvider:
        return OpenAIProvider(
            model_type=cfg.get("type", "local"),
            model_name=cfg.get("model_name") or cfg.get("name") or "",
            api_key=cfg.get("api_key") or "",
            base_url=cfg.get("base_url"),
            thinking=cfg.get("thinking", "enabled"),
            reasoning_effort=cfg.get("reasoning_effort", "high"),
        )

    def _build_orchestrator(self, provider: OpenAIProvider) -> LLMOrchestrator:
        return LLMOrchestrator(
            llm_provider=provider,
            tool_executor=self.tool_executor,
            stream_parser=self.stream_parser,
            approval_handler=self.approval_handler,
            persister=self.persister,
            decision_repo=self.decision_repo,
            message_repo=self.message_repo,
            suggestion_gen=self.suggestion_gen,
            plan_repo=self.plan_repo,
        )

    # ───────────────────────── 主流程 ─────────────────────────

    async def generate_chat(
        self,
        *,
        messages: List[Dict[str, Any]],
        enable_tools: bool = False,
        llm_config: Optional[Dict[str, Any]] = None,
        profile_id: Optional[int] = None,
        chat_id: Optional[str] = None,
        turn_index: Optional[int] = None,
        plan_id: Optional[str] = None,
        is_executing_plan: bool = False,
        params: Optional[Dict[str, Any]] = None,
        collaboration: Optional[Dict[str, Any]] = None,
        fastapi_request: Optional[Any] = None,
        mcp_manager: Optional[Any] = None,
    ) -> AsyncGenerator[str, None]:
        params = params or {}
        cfg = llm_config
        collab_reason = None

        # 构建模型映射（供协作策略选择与故障回退复用）
        models = await self.provider_repo.list()
        model_map = {m.id: m.to_dict() for m in models}

        collab_config = None
        if collaboration and collaboration.get("enabled"):
            collab_config = _CollabConfigAdapter(collaboration)

        # ========== 模型协作策略介入 ==========
        if not is_executing_plan and collab_config:
            last_user_msg = ""
            for msg in reversed(messages):
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
                collab_config, last_user_msg, enable_tools, model_map
            )

            if cfg is None or cfg.get("model_id") != selected_id:
                selected_model = model_map.get(selected_id)
                if selected_model:
                    reasoning_effort = cfg.get("reasoning_effort", "high") if cfg else "high"
                    model_name = selected_model.get("modelName", "")
                    reasoning_effort = resolve_reasoning_effort(model_name, reasoning_effort)
                    cfg = {
                        "type": selected_model.get("type", "local"),
                        "name": selected_model.get("name", ""),
                        "model_id": selected_model.get("id"),
                        "model_name": model_name,
                        "base_url": selected_model.get("baseUrl"),
                        "api_key": selected_model.get("apiKey"),
                        "thinking": "enabled",
                        "reasoning_effort": reasoning_effort,
                    }

        # 保存主模型配置，用于故障回退
        primary_cfg = None
        if collab_config and collaboration.get("fallback_enabled"):
            primary_model = model_map.get(collab_config.primary_model_id)
            if primary_model and (cfg is None or cfg.get("model_id") != primary_model.get("id")):
                reasoning_effort = cfg.get("reasoning_effort", "high") if cfg else "high"
                p_name = primary_model.get("modelName", "")
                reasoning_effort = resolve_reasoning_effort(p_name, reasoning_effort)
                primary_cfg = {
                    "type": primary_model.get("type", "local"),
                    "name": primary_model.get("name", ""),
                    "model_id": primary_model.get("id"),
                    "model_name": p_name,
                    "base_url": primary_model.get("baseUrl"),
                    "api_key": primary_model.get("apiKey"),
                    "thinking": "enabled",
                    "reasoning_effort": reasoning_effort,
                }

        # 无协作策略且未指定模型：尝试取默认 Provider
        if not cfg:
            providers = await self.provider_repo.list_all()
            if providers:
                p = providers[0]
                cfg = {
                    "type": p.type, "name": p.name, "model_id": p.id,
                    "model_name": p.model_name, "base_url": p.base_url,
                    "api_key": p.api_key, "thinking": "enabled", "reasoning_effort": "high",
                }

        messages = clean_messages(messages)

        # 基础 System Prompt
        system_prompt = build_system_prompt(collab_reason=collab_reason,
                                            blueprint_mode=bool(params.get("blueprint_mode")) and not plan_id)

        # 处理 Profile 和 Skills
        profile = None
        has_available_skills = False
        skills: List[Any] = []
        if profile_id is not None:
            profile = await self.profile_repo.get_by_id(profile_id)
            if profile:
                if profile.profile_prompt:
                    system_prompt += f"\n\n ## 当前角色人设 \n\n{profile.profile_prompt}"
                if enable_tools:
                    skills = await self.skill_repo.list_by_profile(profile_id)
                    skill_descriptions = []
                    for skill in skills:
                        desc = skill.description or skill.metadata.get("description", "") or skill.name
                        import os
                        if skill.file_path:
                            skill_md_path = os.path.join(skill.file_path, "SKILL.md")
                            if os.path.exists(skill_md_path):
                                skill_descriptions.append(
                                    f"- 技能ID: `{skill.id}` | 名称：{skill.name} | 描述：{desc}"
                                )
                            else:
                                skill_descriptions.append(
                                    f"- 技能ID: `{skill.id}` | 名称：{skill.name} | 描述：{desc} (⚠️ 指令文件缺失，请检查)"
                                )
                    if skill_descriptions:
                        system_prompt += "\n\n## 可用技能索引\n\n"
                        system_prompt += "\n".join(skill_descriptions)
                        has_available_skills = True

        # 处理系统工具
        local_tools = get_local_tools()
        system_tools = [t for t in local_tools if t["function"]["name"] in default_tools]

        if profile and enable_tools:
            mcp_tools = await get_mcp_tools(mcp_manager) if enable_tools else []
            allowed_tools = profile.tools

            enable_tools_list = [t for t in local_tools if t["function"]["name"] in disabled_tools]
            enable_tools_list.extend(mcp_tools)

            use_tools = [t for t in enable_tools_list if t["function"]["name"] in allowed_tools]
            system_tools.extend(use_tools)

        skill_tools = []
        if has_available_skills:
            skill_tools = [t for t in local_tools if t["function"]["name"] in ['system_use_skill', 'system_execute_script']]
        final_tools = system_tools + skill_tools

        base_params = {}
        if profile:
            base_params = {
                'temperature': profile.temperature,
                'top_p': profile.top_p,
                'top_k': profile.top_k,
                'frequency_penalty': profile.frequency_penalty,
                'presence_penalty': profile.presence_penalty,
            }
        final_params = {**base_params, **params}

        # 插入最终的 System Prompt
        messages.insert(0, {"role": "system", "content": system_prompt})

        # ========== 流式响应（含故障回退） ==========
        async def _stream_with_model(model_cfg: Dict[str, Any]):
            reasoning_effort = model_cfg.get("reasoning_effort", "high")
            reasoning_effort = resolve_reasoning_effort(model_cfg.get("model_name"), reasoning_effort)

            provider = self._build_provider(model_cfg)
            orchestrator = self._build_orchestrator(provider)

            gen = orchestrator.generate_response(
                messages=messages,
                enable_tools=enable_tools,
                tools=final_tools,
                request=fastapi_request,
                mcp_manager=mcp_manager,
                params=final_params,
                profile_id=profile.id if profile else None,
                model_id=model_cfg.get("model_id"),
                chat_id=chat_id,
                turn_index=turn_index,
                blueprint_mode=bool(params.get("blueprint_mode")) and not plan_id,
                plan_id=plan_id if plan_id else None,
                is_executing_plan=is_executing_plan,
            )

            try:
                while True:
                    chunk = await gen.__anext__()
                    if chunk.startswith("❌ 模型服务错误") or chunk.startswith("\n❌ 模型服务错误"):
                        raise Exception(f"模型 {model_cfg.get('model_name')} 服务错误: {chunk.strip()}")
                    yield chunk
            except StopAsyncIteration:
                pass

        current_cfg = cfg
        current_reason = collab_reason

        if current_cfg and current_reason:
            model_info = {
                "model_id": current_cfg.get("model_id"),
                "model_name": current_cfg.get("model_name"),
                "type": current_cfg.get("type"),
                "reason": current_reason,
            }
            yield f"<!--model_info:{json.dumps(model_info, ensure_ascii=False)}-->"

        try:
            async for chunk in _stream_with_model(current_cfg):
                yield chunk
        except Exception as e:
            error_str = str(e)
            # 只有明确是模型服务错误才触发回退
            if "模型服务错误" in error_str and primary_cfg and current_cfg.get("model_id") != primary_cfg.get("model_id"):
                if (primary_cfg and current_cfg and current_cfg.get("model_id") != primary_cfg.get("model_id")):
                    fallback_reason = (f"[故障回退] 原模型调用失败，已切换至主模型 「 "
                                    f"{primary_cfg.get('name')} · {get_typeName(primary_cfg.get('type'))} 」")
                    fallback_info = {
                        "model_id": primary_cfg.get("model_id"),
                        "model_name": primary_cfg.get("model_name"),
                        "type": primary_cfg.get("type"),
                        "reason": fallback_reason,
                    }
                    yield f"<!--model_info:{json.dumps(fallback_info, ensure_ascii=False)}-->"
                    async for chunk in _stream_with_model(primary_cfg):
                        yield chunk
                else:
                    error_msg = (f"模型 {current_cfg.get('name') if current_cfg else '未知'} 调用失败，"
                                f"且无法回退到主模型。错误：{str(e)[:300]}")
                    yield f"<!--error:{json.dumps({'message': error_msg}, ensure_ascii=False)}-->"
                    return


class _CollabConfigAdapter:
    """将协作策略字典适配为 select_model_by_strategy 所需的属性访问接口。"""

    def __init__(self, data: Dict[str, Any]):
        self._data = data or {}

    @property
    def strategy(self):
        return self._data.get("strategy", "auto")

    @property
    def primary_model_id(self):
        return self._data.get("primary_model_id")

    @property
    def secondary_model_id(self):
        return self._data.get("secondary_model_id")

    @property
    def conditions(self):
        return self._data.get("conditions") or {}

    @property
    def primary_ratio(self):
        return self._data.get("primary_ratio", 70)
