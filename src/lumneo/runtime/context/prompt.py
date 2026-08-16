# runtime/context/prompt.py
# 上下文组装（原 backend/routes/chat.py 中的 System Prompt 拼装与消息清理逻辑）。
#
# 将“对话上下文如何组装”这一横切关注点从 API 路由中抽离，置于运行时上下文层。
# 只做字符串拼装与消息清洗，不触碰数据库 / 文件 I/O（§60）。
import os
import re
from typing import List, Dict, Optional

from lumneo.kernel.config.app_config import config
from lumneo import workspace_path
from lumneo.kernel.common.util import get_current_time
from lumneo.persistence.models.profile import ProfileModel
from lumneo.persistence.models.skill import SkillModel


# 系统提示词模板（构建时填充占位符）
_SYSTEM_PROMPT_PATH = config.resource_path("system_prompt.md")
try:
    with open(_SYSTEM_PROMPT_PATH, "r", encoding="utf-8") as _f:
        BASE_SYSTEM_PROMPT = _f.read()
except FileNotFoundError:
    BASE_SYSTEM_PROMPT = ""

# 工具白/黑名单
disabled_tools = ['system_write_file', 'system_patch_file', 'system_delete_file',
                  'system_create_project_tree', 'system_read_file_list']
default_tools = ['system_get_weather', 'system_read_file']

# 需要转义 reasoning_effort 的模型名称列表
REASONING_EFFORT_MAPPING_MODELS = [
    "agnes-2.0-flash",
]
REASONING_EFFORT_MAP = {
    "high": "low",
    "xhigh": "high",
}

BLUEPRINT_INSTRUCTION = """

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


def resolve_reasoning_effort(model_name: Optional[str], reasoning_effort: str) -> str:
    if model_name and any(re.search(p, model_name, re.IGNORECASE) for p in REASONING_EFFORT_MAPPING_MODELS):
        return REASONING_EFFORT_MAP.get(reasoning_effort, reasoning_effort)
    return reasoning_effort


def build_system_prompt(
    profile: Optional[ProfileModel] = None,
    skills: Optional[List[SkillModel]] = None,
    collab_reason: Optional[str] = None,
    blueprint_mode: bool = False,
    time_now: Optional[str] = None,
) -> str:
    """组装 System Prompt：注入上传目录、工作区、时间、角色人设与可用技能索引。"""
    system_prompt = BASE_SYSTEM_PROMPT.replace("{{uploads_dir}}", str(config.uploads_dir))
    system_prompt = system_prompt.replace("{{workspace_path}}", str(workspace_path))
    system_prompt = system_prompt.replace("{{time_now}}", time_now or get_current_time())

    if collab_reason:
        system_prompt += f"\n\n[系统提示] 当前由模型协作策略调度: {collab_reason}"

    if profile:
        if profile.profile_prompt:
            system_prompt += f"\n\n ## 当前角色人设 \n\n{profile.profile_prompt}"

        if skills:
            skill_descriptions = []
            for skill in skills:
                desc = skill.description or skill.metadata.get("description", "") or skill.name
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

    if blueprint_mode:
        system_prompt += BLUEPRINT_INSTRUCTION

    return system_prompt


REASONING_BLOCK = re.compile(r'<!--reasoning:start-->.*?<!--reasoning:end:\d+\.?\d*-->', re.DOTALL)
MISC_MARKERS = re.compile(r'<!--(?:token_usage|reasoning):[^>]*-->')


def clean_messages(messages: List[Dict]) -> List[Dict]:
    """清理历史消息中的推理块与杂项标记（避免污染模型上下文）。"""
    cleaned = []
    for msg in messages:
        msg = dict(msg)
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
                msg["content"] = json_dumps_safe(content)
            else:
                msg["content"] = json_dumps_safe(content) if content is not None else ""
        cleaned.append(msg)
    return cleaned


def json_dumps_safe(obj) -> str:
    import json
    try:
        return json.dumps(obj, ensure_ascii=False)
    except Exception:
        return str(obj)
