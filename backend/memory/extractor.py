"""
Lumneo 长期记忆系统 - MemoryExtractor 提取层
Phase 1 核心记忆闭环

职责：
- 对话结束后异步调用 LLM，提取结构化记忆
- 自动判定 scope（life/work）
- 识别 Skill 提取模式
- 输出标准化 JSON
"""
import json
import asyncio
from typing import List, Dict, Any, Optional
from datetime import datetime

from backend.memory.config import DOMAIN_WHITELIST
from backend.memory.utils import normalize_domain, sensitivity_precheck
from backend.memory.manager import MemoryManager


# ==================== 提取 Prompt 模板 ====================

FACT_EXTRACTION_PROMPT = """你是一个记忆提取助手。请从以下对话中提取值得长期保存的事实、偏好、决策或技能。

**提取规则**：
1. 只提取用户明确表达或双方确认的信息，不要推测
2. 事实类：技术栈、项目信息、用户习惯、重要事件
3. 偏好类：用户喜欢/讨厌的事物、风格选择
4. 决策类：明确做出的技术选型、方案决定
5. 技能类（重要）：包含方法论、踩坑经验、最佳实践、可复用的解决方案
   - Skill 必须包含"场景-方案"结构
   - 触发信号："原来这样可以..."、"下次可以用..."、"总结下这个方法"

**输出格式**：JSON 数组，每个元素包含：
- category: "fact" | "preference" | "decision" | "skill"
- key: 简短关键词（如"技术栈"、"IDE主题偏好"）
- content: 详细描述（Markdown 格式）
- importance: 1-5 的重要性评分
- domain: 领域（仅 skill 需要，可选值: backend/frontend/devops/ai/product/design/infra/security/general）
- source_project: 来源项目名（skill 必填）

**注意**：
- 如果对话中没有值得提取的内容，返回空数组 []
- 不要提取临时性、时效性太强的信息
- 不要提取敏感个人信息（身份证号、密码等）
- 所有 skill 的 proficiency 固定为 1，verified 固定为 false（由系统自动设置）

请只输出 JSON，不要有任何其他文字。

对话内容：
{conversation}
"""


class MemoryExtractor:
    """
    记忆提取器。

    在对话结束后异步调用 LLM，从近期对话中提取结构化记忆。
    """

    def __init__(
        self,
        llm_service=None,  # LLMService 实例，Phase 1 可传入已有服务
    ):
        self.llm_service = llm_service

    async def extract(
        self,
        messages: List[Dict[str, str]],
        scope: str,
        chat_id: Optional[str] = None,
        source_project: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """
        从对话消息中提取结构化记忆。

        Args:
            messages: 对话历史（最近 N 轮）
            scope: "life" 或 "work"
            chat_id: 当前对话 ID
            source_project: 来源项目标签（skill 需要）

        Returns:
            提取的记忆列表，每项为 dict，可直接用于 MemoryManager.create_memory
        """
        # 1. 构造对话文本
        conversation = self._build_conversation_text(messages)

        if not conversation.strip():
            return []

        # 2. 调用 LLM 提取
        prompt = FACT_EXTRACTION_PROMPT.format(conversation=conversation)

        try:
            raw_response = await self._call_llm(prompt)
            extracted = self._parse_extraction(raw_response)
        except Exception as e:
            # 提取失败不阻塞主流程，返回空
            return []

        # 3. 后处理：填充元数据、domain 归一化、敏感度预检
        results = []
        for item in extracted:
            # 基础字段
            item.setdefault("category", "fact")
            item.setdefault("importance", 3)
            item.setdefault("key", "未命名记忆")

            # 自动填充元数据
            item["chat_id"] = chat_id
            item["source_chat_id"] = chat_id
            item["created_at"] = datetime.now().isoformat()
            item["updated_at"] = datetime.now().isoformat()
            item["status"] = "active"

            # Skill 专属处理
            if item.get("category") == "skill":
                item["proficiency"] = 1  # 固定初始值
                item["verified"] = False
                item["verification_count"] = 0
                item["usage_count"] = 0
                item["domain"] = normalize_domain(item.get("domain"))
                item["source_project"] = source_project or item.get("source_project", "global")
                item["used_in_projects"] = [item["source_project"]]

            # 敏感度预检（仅 life 模式下的 fact/preference）
            if scope == "life" and item["category"] in ("fact", "preference"):
                text_to_check = item.get("content", "") + " " + item.get("key", "")
                item["sensitivity"] = sensitivity_precheck(text_to_check)

            results.append(item)

        return results

    def _build_conversation_text(self, messages: List[Dict[str, str]]) -> str:
        """将消息列表格式化为对话文本"""
        lines = []
        for msg in messages:
            role = msg.get("role", "")
            content = msg.get("content", "")
            if role == "user":
                lines.append(f"用户: {content}")
            elif role == "assistant":
                lines.append(f"AI: {content}")
        return "\n".join(lines)

    async def _call_llm(self, prompt: str) -> str:
        """
        调用 LLM 获取提取结果。

        Phase 1 MVP：如果传入了 llm_service 则使用，否则用简单的 httpx 调用。
        实际项目中应该复用已有的 LLMService。
        """
        if self.llm_service:
            # 使用项目已有的 LLMService
            # 构造一条 system prompt + user prompt 的消息
            messages = [
                {"role": "system", "content": "你是一个记忆提取助手，只输出 JSON。"},
                {"role": "user", "content": prompt}
            ]

            # 收集流式输出
            chunks = []
            async for chunk in self.llm_service.generate_response(
                messages=messages,
                enable_tools=False,
            ):
                chunks.append(chunk)

            return "".join(chunks)
        else:
            # MVP 兜底：如果没有 LLMService，返回空（Phase 1 先不实现离线提取）
            # 实际集成时应该传入 LLMService
            return "[]"

    def _parse_extraction(self, raw: str) -> List[Dict[str, Any]]:
        """
        解析 LLM 返回的 JSON。
        处理各种可能的格式问题（markdown 代码块、多余文字等）。
        """
        if not raw or not raw.strip():
            return []

        text = raw.strip()

        # 尝试提取 markdown 代码块中的 JSON
        import re
        code_block = re.search(r'```(?:json)?\s*([\s\S]*?)```', text)
        if code_block:
            text = code_block.group(1).strip()

        # 尝试找到 JSON 数组的起止
        arr_start = text.find('[')
        arr_end = text.rfind(']')
        if arr_start != -1 and arr_end != -1 and arr_end > arr_start:
            text = text[arr_start:arr_end+1]

        try:
            parsed = json.loads(text)
            if isinstance(parsed, list):
                return parsed
            elif isinstance(parsed, dict):
                # 有时 LLM 返回 {"memories": [...]} 这样的结构
                for key in ("memories", "facts", "skills", "results", "data"):
                    if key in parsed and isinstance(parsed[key], list):
                        return parsed[key]
                return [parsed]
            else:
                return []
        except json.JSONDecodeError:
            return []


class MemoryExtractorTrigger:
    """
    提取触发器。

    根据确定性启发式规则判断是否应该触发记忆提取。
    避免每轮对话都调用 LLM，控制成本。
    """

    @staticmethod
    def should_extract(
        messages: List[Dict[str, str]],
        round_count: int,
        last_extract_round: int,
    ) -> bool:
        """
        判断是否触发记忆提取。

        触发条件（满足任一）：
        1. 最近 3 轮包含代码块
        2. 包含决策动词："决定"、"选择"、"改用"、"放弃"
        3. 包含情感/偏好表达："喜欢"、"讨厌"、"觉得"
        4. 对话轮次 >= 10 且包含上述任一特征
        5. 距离上次提取已满 20 轮

        Args:
            messages: 近期对话消息
            round_count: 当前总轮次
            last_extract_round: 上次提取时的轮次
        """
        # 轮次阈值
        if round_count - last_extract_round >= 20:
            return True

        # 取最近 3 轮消息
        recent = messages[-6:] if len(messages) > 6 else messages
        recent_text = " ".join(m.get("content", "") for m in recent)

        # 特征检测
        has_code = "```" in recent_text

        decision_words = ["决定", "选择", "改用", "放弃", "确定", "选定"]
        has_decision = any(w in recent_text for w in decision_words)

        preference_words = ["喜欢", "讨厌", "觉得", "偏好", "习惯", "想要"]
        has_preference = any(w in recent_text for w in preference_words)

        skill_words = ["总结", "方法", "方案", "最佳实践", "踩坑", "经验", "复用"]
        has_skill = any(w in recent_text for w in skill_words)

        # 触发判断
        if has_code or has_decision or has_preference or has_skill:
            if round_count >= 10:
                return True
            # 即使轮次不够，如果有强信号也触发
            if has_decision or has_preference:
                return True

        return False
