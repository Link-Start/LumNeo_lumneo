# backend/memory/extractor.py
"""
Lumneo 长期记忆系统 - MemoryExtractor 提取层

职责：
- 对话结束后异步调用 LLM，提取结构化记忆
- Skill 强制三段式结构（场景-方案-反模式）
- domain 白名单归一化
- proficiency 固定为 1，verified 固定为 false
"""
import json
import re
from typing import List, Dict, Any, Optional
from datetime import datetime

from backend.memory.utils import normalize_domain, sensitivity_precheck
from backend.memory.config import TRIGGER_THRESHOLD_HOURS


# ==================== 提取 Prompt 模板 ====================

FACT_EXTRACTION_PROMPT = """你是一个记忆提取助手。请从以下对话中提取值得长期保存的事实、偏好、决策或技能。

**提取规则**：
1. 只提取用户明确表达或双方确认的信息
2. 事实类：技术栈、项目信息、用户习惯
3. 偏好类：用户喜欢/讨厌的事物、风格选择
4. 决策类：明确做出的技术选型、方案决定
5. 技能类（重要）：包含方法论、踩坑经验、最佳实践、可复用解决方案
   - 触发信号："原来这样可以..."、"下次可以用..."、"总结下这个方法"、"这个方案可以复用"
   - 必须包含代码示例、性能数据、踩坑记录的方法论讨论

**Skill 强制格式**（category="skill" 时）：
- key: 简短技能名（如"异步数据库批量写入"）
- domain: 必须从以下选择：backend/frontend/devops/ai/product/design/infra/security/general
- scenario: 场景描述（如"高并发下 SQLite 写性能瓶颈"）
- solution: 方案描述（如"使用 aiosqlite + 连接池 + executemany"）
- pitfalls: 反模式/踩坑（如"避免每请求新建连接"）
- source_project: 来源项目名（必填）
- proficiency: 1（固定，不要改）
- verified: false（固定，不要改）

**输出格式**：JSON 数组
[
  {
    "category": "fact" | "preference" | "decision" | "skill",
    "key": "关键词",
    "content": "详细描述（Markdown）",
    "importance": 1-5,
    "domain": "backend/frontend/...（仅 skill）",
    "source_project": "项目名（skill 必填）",
    "scenario": "...（仅 skill）",
    "solution": "...（仅 skill）",
    "pitfalls": "...（仅 skill）"
  }
]

**注意**：
- 没有值得提取的内容返回空数组 []
- 不要提取临时性、时效性太强的信息
- 不要提取敏感个人信息（身份证号、密码等）
- key 优先使用用户原文语言

请只输出 JSON，不要有任何其他文字。

对话内容：
{conversation}
"""


class MemoryExtractor:
    """记忆提取器"""

    def __init__(self, llm_service=None):
        self.llm_service = llm_service

    async def extract(
        self,
        messages: List[Dict[str, str]],
        scope: str,
        chat_id: Optional[str] = None,
        source_project: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """从对话中提取结构化记忆"""
        conversation = self._build_conversation_text(messages)

        if not conversation.strip():
            return []

        prompt = FACT_EXTRACTION_PROMPT.format(conversation=conversation)

        try:
            raw_response = await self._call_llm(prompt)
            extracted = self._parse_extraction(raw_response)
        except Exception as e:
            import logging
            logging.getLogger(__name__).warning(f"LLM 提取调用失败: {e}")
            return []

        # 后处理
        results = []
        for item in extracted:
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
                item["proficiency"] = 1
                item["verified"] = False
                item["verification_count"] = 0
                item["usage_count"] = 0
                item["domain"] = normalize_domain(item.get("domain"))
                item["source_project"] = source_project or item.get("source_project", "global")
                item["used_in_projects"] = [item["source_project"]]
                # 添加 confirmed_by 字段
                item["confirmed_by"] = "ai_auto"

                # 三段式结构写入 content
                scenario = item.get("scenario", "")
                solution = item.get("solution", "")
                pitfalls = item.get("pitfalls", "")

                parts = []
                if scenario:
                    parts.append(f"## 场景\n{scenario}")
                if solution:
                    parts.append(f"## 方案\n{solution}")
                if pitfalls:
                    parts.append(f"## 反模式 / 踩坑\n{pitfalls}")

                if parts:
                    item["content"] = "\n\n".join(parts)

            # 敏感度预检（仅 life 模式）
            if scope == "life" and item["category"] in ("fact", "preference"):
                text_to_check = item.get("content", "") + " " + item.get("key", "")
                item["sensitivity"] = sensitivity_precheck(text_to_check)

            results.append(item)

        return results

    def _build_conversation_text(self, messages: List[Dict[str, str]]) -> str:
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
        if self.llm_service:
            messages = [
                {"role": "system", "content": "你是一个记忆提取助手，只输出 JSON。"},
                {"role": "user", "content": prompt}
            ]
            chunks = []
            async for chunk in self.llm_service.generate_response(
                messages=messages,
                enable_tools=False,
            ):
                chunks.append(chunk)
            return "".join(chunks)
        return "[]"

    def _parse_extraction(self, raw: str) -> List[Dict[str, Any]]:
        if not raw or not raw.strip():
            return []

        text = raw.strip()
        code_block = re.search(r"```(?:json)?\s*([\s\S]*?)```", text)
        if code_block:
            text = code_block.group(1).strip()

        arr_start = text.find("[")
        arr_end = text.rfind("]")
        if arr_start != -1 and arr_end != -1 and arr_end > arr_start:
            text = text[arr_start:arr_end+1]

        # 清洗不可见控制字符，避免 json.loads 失败
        text = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]', '', text)

        try:
            parsed = json.loads(text)
            if isinstance(parsed, list):
                return parsed
            elif isinstance(parsed, dict):
                for key in ("memories", "facts", "skills", "results", "data"):
                    if key in parsed and isinstance(parsed[key], list):
                        return parsed[key]
                return [parsed]
        except json.JSONDecodeError:
            import logging
            logging.getLogger(__name__).warning(f"JSON 解析失败，尝试备选解析: {text[:200]}")
            # 备选：尝试 ast.literal_eval 解析
            try:
                import ast
                parsed = ast.literal_eval(text)
                if isinstance(parsed, list):
                    return parsed
                elif isinstance(parsed, dict):
                    return [parsed]
            except (ValueError, SyntaxError) as e2:
                logging.getLogger(__name__).warning(f"备选解析也失败: {e2}")
            return []


class MemoryExtractorTrigger:
    """提取触发器"""

    @staticmethod
    def should_extract(
        messages: List[Dict[str, str]],
        round_count: int,
        last_extract_round: int,
        last_extract_time: Optional[float] = None,
    ) -> bool:
        """判断是否触发记忆提取"""
        # 轮次阈值
        if round_count - last_extract_round >= 20:
            return True

        # 时间间隔阈值（小时）
        if last_extract_time is not None:
            from time import time
            hours_since_last = (time() - last_extract_time) / 3600
            if hours_since_last >= TRIGGER_THRESHOLD_HOURS:
                return True

        recent = messages[-6:] if len(messages) > 6 else messages
        recent_text = " ".join(m.get("content", "") for m in recent)

        has_code = "```" in recent_text

        decision_words = ["决定", "选择", "改用", "放弃", "确定", "选定"]
        has_decision = any(w in recent_text for w in decision_words)

        preference_words = ["喜欢", "讨厌", "觉得", "偏好", "习惯", "想要"]
        has_preference = any(w in recent_text for w in preference_words)

        skill_words = ["总结", "方法", "方案", "最佳实践", "踩坑", "经验", "复用"]
        has_skill = any(w in recent_text for w in skill_words)

        # has_code 独立判断，不受轮次门槛限制
        if has_code:
            return True
        # decision / preference：轮次 ≥ 10
        if (has_decision or has_preference) and round_count >= 10:
                return True
        # skill：独立低门槛（≥5 轮即可触发），技能信号不应被埋没
        if has_skill and round_count >= 5:
            return True

        return False