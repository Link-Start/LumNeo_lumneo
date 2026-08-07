"""
Lumneo 长期记忆系统 - StateManager 状态层
Phase 1 核心记忆闭环

职责：
- 管理 life/core/state.md 的动态更新
- 每次 Life Mode 对话结束后，评估并更新 mood/energy/focus 等字段
- 让 AI 具备情绪连续性
"""
import yaml
from pathlib import Path
from typing import Optional, Dict, Any
from datetime import datetime

from backend.memory.config import DEFAULT_MEMORY_DIR, FILE_ENCODING
from backend.memory.utils import parse_frontmatter, serialize_frontmatter
from backend.memory.models import MemoryFrontmatter


# ==================== State 评估 Prompt ====================

STATE_EVALUATION_PROMPT = """基于以下对话，评估 AI 伙伴的当前状态。

请输出一个 JSON 对象，包含以下字段：
- mood: 当前心情（如：专注、愉悦、疲惫、困惑、平静、兴奋）
- energy_level: 精力水平（high / medium / low）
- focus_topic: 当前专注领域（简短关键词，如"长期记忆架构设计"）
- last_user_emotion: 用户最后表达的情绪（如：焦虑、开心、疲惫、中性）
- pending_tasks: 用户提到的待办事项列表（字符串数组，没有则空数组）
- recent_notes: 近期观察笔记（1-2 句话，关于用户的近期状态）

请只输出 JSON，不要有任何其他文字。

对话内容：
{conversation}
"""


class StateManager:
    """
    状态管理器。

    负责读写 life/core/state.md，让 AI 在 Life Mode 下具备情绪连续性。
    """

    def __init__(self, memory_dir: Optional[Path] = None):
        self.memory_dir = memory_dir or DEFAULT_MEMORY_DIR
        self.state_path = self.memory_dir / "life" / "core" / "state.md"

    async def read_state(self) -> Dict[str, Any]:
        """
        读取当前 state。

        Returns:
            state 字典，若文件不存在则返回默认状态
        """
        if not self.state_path.exists():
            return self._default_state()

        try:
            with open(self.state_path, "r", encoding=FILE_ENCODING) as f:
                raw = f.read()
            frontmatter, content = parse_frontmatter(raw)

            if frontmatter:
                state = frontmatter.to_dict()
                state["_content"] = content
                return state
        except Exception:
            pass

        return self._default_state()

    async def update_state(
        self,
        llm_service=None,
        messages: Optional[list] = None,
        manual_updates: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        更新 state.md。

        两种方式：
        1. 传入 llm_service + messages：让 LLM 评估情绪状态
        2. 传入 manual_updates：直接覆盖指定字段

        Args:
            llm_service: LLMService 实例
            messages: 近期对话消息（用于 LLM 评估）
            manual_updates: 手动更新的字段

        Returns:
            更新后的 state 字典
        """
        # 读取现有 state
        current = await self.read_state()

        if manual_updates:
            current.update(manual_updates)

        if llm_service and messages:
            try:
                evaluated = await self._evaluate_state(llm_service, messages)
                if evaluated:
                    current.update(evaluated)
            except Exception:
                pass  # 评估失败不影响原有 state

        # 更新时间戳
        current["updated_at"] = datetime.now().isoformat()

        # 写入文件
        await self._write_state(current)

        return current

    async def _evaluate_state(
        self,
        llm_service,
        messages: list,
    ) -> Optional[Dict[str, Any]]:
        """
        调用 LLM 评估当前状态。
        """
        conversation = "\n".join(
            f"{'用户' if m.get('role') == 'user' else 'AI'}: {m.get('content', '')}"
            for m in messages[-10:]  # 取最近 10 轮
        )

        prompt = STATE_EVALUATION_PROMPT.format(conversation=conversation)

        try:
            chunks = []
            async for chunk in llm_service.generate_response(
                messages=[
                    {"role": "system", "content": "你是一个状态评估助手，只输出 JSON。"},
                    {"role": "user", "content": prompt}
                ],
                enable_tools=False,
            ):
                chunks.append(chunk)

            raw = "".join(chunks)

            # 解析 JSON
            import json, re
            text = raw.strip()
            code_block = re.search(r'```(?:json)?\s*([\s\S]*?)```', text)
            if code_block:
                text = code_block.group(1).strip()

            parsed = json.loads(text)
            if isinstance(parsed, dict):
                return parsed
        except Exception:
            pass

        return None

    async def _write_state(self, state: Dict[str, Any]):
        """将 state 写入 state.md"""
        self.state_path.parent.mkdir(parents=True, exist_ok=True)

        # 分离 frontmatter 和正文
        content_fields = ["_content", "recent_notes"]
        content_parts = []

        for field in content_fields:
            if field in state:
                val = state.pop(field)
                if val:
                    content_parts.append(str(val))

        content = "\n\n".join(content_parts) if content_parts else ""

        # 构建 frontmatter
        fm = MemoryFrontmatter.from_dict(state)
        fm.category = "state"
        fm.key = "current_state"

        raw = serialize_frontmatter(fm, content)

        with open(self.state_path, "w", encoding=FILE_ENCODING) as f:
            f.write(raw)

    def _default_state(self) -> Dict[str, Any]:
        """默认状态"""
        return {
            "category": "state",
            "key": "current_state",
            "mood": "平静",
            "energy_level": "medium",
            "focus_topic": "",
            "last_user_emotion": "中性",
            "pending_tasks": [],
            "created_at": datetime.now().isoformat(),
            "updated_at": datetime.now().isoformat(),
        }

    def format_state_for_prompt(self, state: Optional[Dict[str, Any]] = None) -> str:
        """
        将 state 格式化为 System Prompt 可注入的文本。

        Returns:
            如："## 当前状态\n心情：专注\n精力：高\n专注领域：长期记忆架构设计"
        """
        if state is None:
            # 同步读取（用于非 async 场景）
            if self.state_path.exists():
                try:
                    with open(self.state_path, "r", encoding=FILE_ENCODING) as f:
                        raw = f.read()
                    fm, _ = parse_frontmatter(raw)
                    if fm:
                        state = fm.to_dict()
                except Exception:
                    state = self._default_state()
            else:
                state = self._default_state()

        lines = ["## 当前状态"]

        mood = state.get("mood", "平静")
        energy = state.get("energy_level", "medium")
        focus = state.get("focus_topic", "")
        emotion = state.get("last_user_emotion", "中性")

        lines.append(f"心情：{mood}")
        lines.append(f"精力：{energy}")
        if focus:
            lines.append(f"专注领域：{focus}")
        lines.append(f"用户情绪：{emotion}")

        pending = state.get("pending_tasks", [])
        if pending:
            lines.append(f"待办：{', '.join(pending)}")

        return "\n".join(lines)
