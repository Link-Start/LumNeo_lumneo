# src/lumneo/application/facade.py
# 应用层管理门面（资源/管理域的统一对外边界）。
#
# 与 ConversationFacade（对话域）并列。API 路由只通过本门面访问管理域；内部编排
# 各 Repository 端口（聊天/消息/画像/模型/技能/工具调用/计划）、文件存储适配器
# （StoragePort）与配置（AppConfig），不直接持有数据库会话。
import asyncio
import os
import shutil
import uuid
from typing import Any, Dict, List, Optional, Tuple

import yaml
from openai import AsyncOpenAI

import lumneo
from lumneo.kernel.config.app_config import config
from lumneo.kernel.common.logger import logger
from lumneo.conversation.ports.conversation_repository import ConversationRepository
from lumneo.conversation.ports.message_repository import MessageRepository
from lumneo.conversation.ports.profile_repository import ProfileRepository
from lumneo.conversation.ports.provider_repository import ProviderRepository
from lumneo.conversation.ports.skill_repository import SkillRepository
from lumneo.conversation.ports.tool_call_repository import ToolCallRepository
from lumneo.conversation.ports.plan_repository import PlanRepository
from lumneo.infrastructure.filesystem.storage_port import StoragePort
from lumneo.runtime.context.collaboration import select_model_by_strategy


class ApplicationFacade:
    """管理/资源域门面：聊天、画像、模型、技能、工具调用、计划、文件、工作区、协作。"""

    def __init__(self, *, chat_repo: ConversationRepository, message_repo: MessageRepository,
                 profile_repo: ProfileRepository, provider_repo: ProviderRepository,
                 skill_repo: SkillRepository, tool_call_repo: ToolCallRepository,
                 plan_repo: PlanRepository, storage: StoragePort):
        self.chat_repo = chat_repo
        self.message_repo = message_repo
        self.profile_repo = profile_repo
        self.provider_repo = provider_repo
        self.skill_repo = skill_repo
        self.tool_call_repo = tool_call_repo
        self.plan_repo = plan_repo
        self.storage = storage

    # ===================== 聊天管理 =====================
    async def create_chat(self) -> Dict:
        record = await self.chat_repo.create()
        return record.to_dict()

    async def update_chat_title(self, chat_id: str, title: str) -> Dict:
        await self.chat_repo.update_title(chat_id, title)
        return {"status": "ok"}

    async def list_chats(self) -> List[Dict]:
        records = await self.chat_repo.list()
        return [r.to_dict() for r in records]

    async def delete_chat(self, chat_id: str) -> Dict:
        disk_files = await self.chat_repo.delete(chat_id)
        if disk_files:
            self.storage.delete_many(disk_files)
        return {"status": "ok"}

    async def get_messages(self, chat_id: str) -> List[Dict]:
        records = await self.message_repo.get_by_chat(chat_id)
        return [r.to_dict() for r in records]

    async def add_message(self, chat_id: str, role: str, content: Any,
                          profile_id: Optional[int] = None, plan_id: Optional[str] = None,
                          model_id: Optional[str] = None, file_ref: Any = None,
                          turn_index: Optional[int] = None) -> Dict:
        record = await self.message_repo.add(
            chat_id=chat_id, role=role, content=content, profile_id=profile_id,
            plan_id=plan_id, model_id=model_id, file_ref=file_ref, turn_index=turn_index,
        )
        return record.to_dict()

    async def update_message(self, message_id: int, chat_id: str, content: Any = None,
                             file_ref: Any = None, plan_id: Optional[str] = None,
                             model_id: Optional[str] = None) -> Optional[Dict]:
        ok = await self.message_repo.update(
            message_id=message_id, chat_id=chat_id, content=content, file_ref=file_ref,
            plan_id=plan_id, model_id=model_id,
        )
        return {"status": "ok"} if ok else None

    async def delete_messages_by_turn(self, chat_id: str, turn_index: int) -> Dict:
        disk_files = await self.message_repo.truncate(chat_id, from_turn_index=turn_index)
        if disk_files:
            self.storage.delete_many(disk_files)
        return {"status": "ok", "deleted_count": len(disk_files)}

    async def get_message_by_turn(self, chat_id: str, turn_index: int) -> Optional[Dict]:
        records = await self.message_repo.get_by_chat(chat_id)
        matches = [r for r in records if r.turn_index == turn_index]
        if not matches:
            return None
        matches.sort(key=lambda r: r.id, reverse=True)
        return matches[0].to_dict()

    # ===================== 画像 =====================
    async def create_profile(self, **fields) -> Dict:
        record = await self.profile_repo.create(**fields)
        return record.to_dict()

    async def update_profile(self, profile_id: int, **fields) -> Optional[Dict]:
        record = await self.profile_repo.update(profile_id, **fields)
        return record.to_dict() if record else None

    async def list_profiles(self) -> List[Dict]:
        records = await self.profile_repo.list()
        return [r.to_dict() for r in records]

    async def delete_profile(self, profile_id: int) -> None:
        await self.profile_repo.delete(profile_id)

    async def get_profile_skills(self, profile_id: int) -> List:
        skills = await self.skill_repo.list_by_profile(profile_id)
        return [s.id for s in skills]

    # ===================== 模型 =====================
    async def list_models(self) -> List[Dict]:
        records = await self.provider_repo.list()
        return [r.to_dict() for r in records]

    async def create_model(self, **fields) -> Dict:
        record = await self.provider_repo.create(**fields)
        return record.to_dict()

    async def update_model(self, model_id: str, **fields) -> Optional[Dict]:
        fields = {k: v for k, v in fields.items() if v is not None}
        record = await self.provider_repo.update(model_id, **fields)
        return record.to_dict() if record else None

    async def delete_model(self, model_id: str) -> None:
        await self.provider_repo.delete(model_id)

    async def list_remote_models(self, base_url: str, api_key: str) -> List[str]:
        """探测远程 OpenAI 兼容端点可用的模型列表。"""
        try:
            client = AsyncOpenAI(api_key=api_key or "none", base_url=base_url)
            models = await client.models.list()
            return [m.id for m in models.data]
        except Exception as e:
            raise RuntimeError(str(e))

    # ===================== 技能 =====================
    async def list_skills(self, profile_id: Optional[int] = None,
                          include_profiles: bool = False) -> List[Dict]:
        if profile_id is not None:
            records = await self.skill_repo.list_available_for_profile(profile_id)
        else:
            records = await self.skill_repo.list_all()
        result: List[Dict] = []
        for record in records:
            item = {
                "id": record.id,
                "name": record.name,
                "description": record.description or record.metadata.get("description", ""),
                "is_global": record.is_global,
            }
            if include_profiles:
                profiles = await self.skill_repo.get_profiles_using_skill(record.id)
                item["used_by_profiles"] = profiles
            result.append(item)
        return result

    async def update_skill(self, skill_id: str, name: Optional[str] = None,
                           description: Optional[str] = None,
                           is_global: Optional[bool] = None) -> Optional[Dict]:
        fields: Dict[str, Any] = {}
        if name is not None:
            fields["name"] = name
        if description is not None:
            fields["description"] = description
        if is_global is not None:
            fields["is_global"] = is_global
        record = await self.skill_repo.update(skill_id, **fields)
        if not record:
            return None
        return {
            "success": True, "id": record.id, "name": record.name,
            "description": record.description, "is_global": record.is_global,
        }

    async def delete_skill(self, skill_id: str) -> Dict:
        skill = await self.skill_repo.get_by_id(skill_id)
        if not skill:
            raise LookupError("技能不存在")
        file_path = skill.file_path
        ok = await self.skill_repo.delete(skill_id)
        if not ok:
            raise RuntimeError("删除失败")
        if file_path and os.path.exists(file_path):
            try:
                shutil.rmtree(file_path)
            except Exception as e:
                logger.error(f"删除技能文件夹失败 {file_path}: {e}")
        return {"success": True, "message": "技能已删除"}

    async def upload_skill(self, files: List[Tuple[str, bytes]], skill_name: Optional[str] = None,
                           is_global: bool = False, profile_id: Optional[int] = None) -> Dict:
        if not files:
            raise ValueError("没有接收到文件")

        first_path = files[0][0].replace("\\", "/")
        folder_name = first_path.split("/")[0]
        if not folder_name:
            raise ValueError("无法解析文件路径")

        skills_root = str(config.skills_dir)
        skill_path = os.path.join(skills_root, folder_name)
        abs_skills_dir = os.path.abspath(skill_path)
        abs_skills_root = os.path.abspath(skills_root)
        if not abs_skills_dir.startswith(abs_skills_root):
            raise ValueError("非法的技能名称")

        os.makedirs(abs_skills_dir, exist_ok=True)
        for filename, content in files:
            rel = filename.replace("\\", "/")
            internal = rel[len(folder_name) + 1:] if rel.startswith(folder_name + "/") else rel
            if not internal:
                continue
            target = os.path.join(abs_skills_dir, internal)
            os.makedirs(os.path.dirname(target), exist_ok=True)
            if isinstance(content, str):
                content = content.encode("utf-8")
            with open(target, "wb") as f:
                f.write(content)

        skill_id = str(uuid.uuid4())
        display_name = folder_name
        if skill_name and skill_name.strip():
            display_name = skill_name.strip()

        description = ""
        metadata: Dict[str, Any] = {}
        skill_md = os.path.join(skill_path, "SKILL.md")
        if os.path.exists(skill_md):
            try:
                with open(skill_md, "r", encoding="utf-8") as f:
                    md_content = f.read()
                fm = self._parse_skill_frontmatter(md_content)
                if fm:
                    if not (skill_name and skill_name.strip()):
                        display_name = fm.get("name", display_name)
                    description = fm.get("description", "")
                    metadata.update(fm)
            except Exception as e:
                logger.error(f"解析 SKILL.md 失败: {e}")

        await self.skill_repo.create_or_update(
            skill_id=skill_id, name=display_name, file_path=skill_path,
            metadata=metadata, is_global=is_global,
        )
        if profile_id is not None:
            await self.skill_repo.link_to_profile(profile_id, skill_id)
        return {
            "success": True, "id": skill_id, "name": display_name,
            "description": description, "is_global": is_global,
        }

    async def batch_select_skills(self, profile_id: int, selected_skill_ids: List[str]) -> None:
        await self.skill_repo.set_selected_skills(profile_id, selected_skill_ids)

    @staticmethod
    def _parse_skill_frontmatter(content: str) -> Dict:
        """解析 SKILL.md 的 YAML 前置元数据（--- ... --- 之间）。"""
        if content.startswith("---"):
            parts = content.split("---", 2)
            if len(parts) >= 3:
                try:
                    return yaml.safe_load(parts[1]) or {}
                except Exception:
                    return {}
        return {}

    # ===================== 工具调用 =====================
    async def get_tool_call(self, call_id: str) -> Dict:
        record = await self.tool_call_repo.get_by_id(call_id)
        if not record:
            raise LookupError("Tool call not found")
        data = record.to_dict()
        meta = record.meta_data if isinstance(record.meta_data, dict) else {}
        if meta.get("storage_type") == "file":
            file_path = meta.get("file_path")
            abs_path = os.path.join(str(config.cache_dir), file_path) if file_path else None
            if abs_path and os.path.exists(abs_path):
                try:
                    full = await asyncio.to_thread(self.storage.read_text, abs_path)
                    data["result"] = full
                except Exception as e:
                    data["result"] = f"[读取完整内容失败: {str(e)}]"
            else:
                data["result"] = "[错误：本地结果文件已丢失或路径无效]"
        return data

    async def batch_get_tool_calls(self, call_ids: List[str]) -> Dict:
        if not call_ids:
            return {}
        records = await self.tool_call_repo.list_by_call_ids(call_ids)
        result_map: Dict[str, Dict] = {}
        MAX_MODEL_CHARS = 6000
        for r in records:
            meta = r.meta_data if isinstance(r.meta_data, dict) else {}
            if meta.get("storage_type") == "file":
                file_path = meta.get("file_path")
                abs_path = os.path.join(str(config.cache_dir), file_path) if file_path else None
                try:
                    if abs_path and os.path.exists(abs_path):
                        full = await asyncio.to_thread(self.storage.read_text, abs_path)
                        truncated = (
                            full[:4000] + "\n\n...(中间内容过长已省略)...\n\n" + full[-2000:]
                            if len(full) > MAX_MODEL_CHARS else full
                        )
                        result_map[r.call_id] = {"arguments": r.arguments, "result": truncated}
                    else:
                        result_map[r.call_id] = {
                            "arguments": r.arguments,
                            "result": "[错误：本地文件缺失，无法提供上下文]",
                        }
                except Exception as e:
                    result_map[r.call_id] = {
                        "arguments": r.arguments,
                        "result": f"[读取完整内容失败: {str(e)}]",
                    }
            else:
                result_map[r.call_id] = {"arguments": r.arguments, "result": r.result}
        return result_map

    async def delete_tool_calls(self, call_ids: List[str]) -> Dict:
        if not call_ids:
            return {"message": "No call_ids provided", "deleted_count": 0}
        disk_files = await self.tool_call_repo.delete_by_call_ids(call_ids)
        if disk_files:
            self.storage.delete_many(disk_files)
        return {
            "message": "Tool calls deleted successfully",
            "deleted_count": len(disk_files),
        }

    async def confirm_tool_call(self, call_id: str, confirmed: bool) -> Dict:
        record = await self.tool_call_repo.get_by_id(call_id)
        if not record:
            raise LookupError("Tool call not found")
        if record.status != "pending_confirmation":
            raise ValueError(f"操作无效，当前状态为: {record.status}")
        status = "confirmed" if confirmed else "cancelled"
        await self.tool_call_repo.update_status(call_id, status)
        return {"message": f"Tool call {status}", "call_id": call_id}

    # ===================== 计划 =====================
    async def update_plan(self, plan_id: str, steps: List[Dict]) -> Dict:
        existing = await self.plan_repo.get(plan_id)
        if existing is None:
            raise LookupError("Plan not found")
        ok = await self.plan_repo.update(plan_id, steps)
        if not ok:
            raise RuntimeError("Failed to update plan")
        return {"status": "ok"}

    # ===================== 文件 =====================
    async def upload_file(self, filename: str, content: bytes,
                          content_type: Optional[str]) -> Dict:
        os.makedirs(str(config.uploads_dir), exist_ok=True)
        ext = os.path.splitext(filename)[1]
        unique_name = f"{uuid.uuid4()}{ext}"
        file_path = os.path.join(str(config.uploads_dir), unique_name)
        with open(file_path, "wb") as f:
            f.write(content)
        return {
            "filename": filename, "stored_name": unique_name,
            "type": content_type, "url": f"/files/uploads/{unique_name}",
        }

    async def delete_files(self, body: Any) -> Dict:
        text = body.decode("utf-8") if isinstance(body, bytes) else body
        self.storage.delete_uploaded_files(text)
        return {"message": "File deleted successfully"}

    # ===================== 工作区 =====================
    async def set_workspace(self, path: str) -> Dict:
        if not os.path.isdir(path):
            raise ValueError("提供的路径不是一个有效目录")
        lumneo.workspace_path = path
        return {"status": "ok", "path": lumneo.workspace_path}

    async def get_workspace(self) -> Dict:
        return {"path": lumneo.workspace_path}

    # ===================== 协作预览 =====================
    async def preview_collaboration(self, req: Dict) -> Dict:
        collab = req.get("collaboration")
        if not collab or not collab.get("enabled"):
            return {"strategy": "disabled", "selected": None, "reason": "协作模式未启用"}

        models = await self.provider_repo.list()
        model_map = {m.id: m.to_dict() for m in models}

        message = req.get("message", "")
        enable_tools = req.get("enable_tools", False)

        # 用轻量配置对象承载协作参数（与原 _FakeConfig 等价）
        cfg = type("CollaborationConfig", (), {})()
        for k, v in collab.items():
            setattr(cfg, k, v)

        selected_id, reason = await select_model_by_strategy(cfg, message, enable_tools, model_map)
        return {
            "strategy": collab.get("strategy"),
            "selected": model_map.get(selected_id),
            "selected_id": selected_id,
            "reason": reason,
            "primary_model": model_map.get(collab.get("primary_model_id")),
            "secondary_model": model_map.get(collab.get("secondary_model_id")),
        }
