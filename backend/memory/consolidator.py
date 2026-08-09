# backend/memory/consolidator.py
"""
Lumneo 长期记忆系统 - Consolidator 记忆压缩/归档
Phase 4 完整版

增强：
- 成本追踪与告警（日成本上限 $0.5）
- 指数退避重试（1s → 2s → 4s，最多 3 次）
- 失败标记 retry_pending，下次优先重试
- 单次 Token 截断保留完整句子边界
"""
import os
import json
import asyncio
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple
from datetime import datetime, timedelta

from backend.memory.config import (
    CONSOLIDATOR_DAILY_LIMIT,
    CONSOLIDATOR_QUEUE_LIMIT,
    CONSOLIDATOR_MAX_INPUT_TOKENS,
    PENDING_EXPIRE_DAYS,
    FILE_ENCODING,
)
from backend.memory.models import MemoryFrontmatter, MemoryEntry
from backend.memory.utils import (
    parse_frontmatter,
    read_markdown_file_sync,
    sensitivity_precheck,
    normalize_domain,
)
from backend.memory.manager import MemoryManager


# ==================== Consolidator Prompt ====================

CONSOLIDATOR_PROMPT = """你是一个记忆归档助手。请从以下 Timeline 内容中提取值得长期保存的事实、偏好、决策或技能。

**提取规则**：
1. 跳过日常闲聊、临时性信息
2. 提取关键决策、偏好变化、重要事件、方法论
3. Skill 必须包含"场景-方案-反模式"结构
4. 如果内容与已有记忆冲突（如用户改变了偏好），标记为冲突

**输出格式**：JSON 数组
[
  {
    "category": "fact" | "preference" | "decision" | "skill",
    "key": "简短关键词",
    "content": "详细描述（Markdown）",
    "importance": 1-5,
    "domain": "backend/frontend/devops/ai/product/design/infra/security/general（仅 skill）",
    "source_project": "来源项目名（skill 必填）",
    "conflict_with": "已有记忆的 key（如果有冲突）",
    "scenario": "场景描述（仅 skill）",
    "solution": "方案描述（仅 skill）",
    "pitfalls": "反模式/踩坑（仅 skill）"
  }
]

如果没有值得提取的内容，返回空数组 []。
请只输出 JSON，不要有任何其他文字。

Timeline 内容：
{timeline_content}
"""


class Consolidator:
    """
    记忆压缩/归档器。

    核心原则：永不覆盖历史事实，只做追加与归档。
    """

    def __init__(
        self,
        memory_manager: MemoryManager,
        llm_service=None,
        daily_cost_limit: float = 0.5,  # 日成本上限 $0.5
    ):
        self.memory_mgr = memory_manager
        self.llm_service = llm_service
        self.daily_cost_limit = daily_cost_limit

        # 熔断计数器
        self._daily_call_count = 0
        self._daily_cost_usd = 0.0
        self._last_reset_date = datetime.now().date()
        self._lock = asyncio.Lock()

    async def run(self, force: bool = False) -> Tuple[int, int]:
        """
        执行一次 Consolidator 归档流程。

        Args:
            force: 是否强制运行（忽略触发门控和熔断）

        Returns:
            (processed_count, extracted_count) - 处理的 timeline 数和提取的记忆数
        """
        async with self._lock:
            # 1. 日上限熔断 + 成本重置
            today = datetime.now().date()
            if today != self._last_reset_date:
                self._daily_call_count = 0
                self._daily_cost_usd = 0.0
                self._last_reset_date = today

            if not force and self._daily_call_count >= CONSOLIDATOR_DAILY_LIMIT:
                return 0, 0  # 已达日上限

            if not force and self._daily_cost_usd >= self.daily_cost_limit:
                # 成本告警：已达日成本上限
                return 0, 0

            # 2. 队列上限熔断
            active_timelines = await self._list_active_timelines()
            if not force and len(active_timelines) > CONSOLIDATOR_QUEUE_LIMIT:
                return 0, 0  # 队列积压，暂停新触发

            # 3. 触发门控（非强制模式下）
            if not force:
                eligible = [t for t in active_timelines if self._should_process(t)]
            else:
                eligible = active_timelines

            if not eligible:
                return 0, 0

            processed = 0
            extracted_total = 0

            for timeline_entry in eligible:
                # 日上限检查
                if self._daily_call_count >= CONSOLIDATOR_DAILY_LIMIT:
                    break

                # 成本检查
                if self._daily_cost_usd >= self.daily_cost_limit:
                    break

                # 处理单条 timeline
                count = await self._process_single_timeline(timeline_entry)
                if count >= 0:
                    processed += 1
                    extracted_total += count
                    self._daily_call_count += 1

            return processed, extracted_total

    async def _list_active_timelines(self) -> List[MemoryEntry]:
        """列出所有 status=active 或 retry_pending 的 timeline 文件"""
        timeline_dir = self.memory_mgr.memory_dir / "life" / "timeline"
        results = []

        if not timeline_dir.exists():
            return results

        for md_file in timeline_dir.rglob("*.md"):
            # 跳过 monthly 摘要文件
            if "monthly" in md_file.parts:
                continue

            try:
                entry = await self.memory_mgr.read_memory(md_file)
                if entry and entry.frontmatter.status in ("active", "retry_pending"):
                    results.append(entry)
            except Exception:
                continue

        # retry_pending 优先处理，然后按日期排序（旧的优先）
        results.sort(
            key=lambda x: (0 if x.frontmatter.status == "retry_pending" else 1, x.frontmatter.date or "")
        )
        return results

    def _should_process(self, timeline_entry: MemoryEntry) -> bool:
        """
        确定性触发门控。
        满足以下任一才触发 LLM 处理：
        1. 包含代码块
        2. 包含决策动词
        3. 包含情感/偏好表达
        4. 内容较长且有实质信息
        """
        content = timeline_entry.content or ""

        # 包含代码块
        if "```" in content:
            return True

        # 决策动词
        decision_words = ["决定", "选择", "改用", "放弃", "确定", "选定", "确定要"]
        if any(w in content for w in decision_words):
            return True

        # 情感/偏好表达
        preference_words = ["喜欢", "讨厌", "觉得", "偏好", "习惯", "想要", "不喜欢"]
        if any(w in content for w in preference_words):
            return True

        # 技能/方法论信号
        skill_words = ["总结", "方法", "方案", "最佳实践", "踩坑", "经验", "复用", "优化"]
        if any(w in content for w in skill_words):
            return True

        # 内容较长且有实质信息（>100 字且包含具体名词）
        if len(content) > 100:
            concrete_indicators = ["项目", "技术", "代码", "数据库", "接口", "架构", "设计"]
            if any(w in content for w in concrete_indicators):
                return True

        return False

    async def _process_single_timeline(self, timeline_entry: MemoryEntry) -> int:
        """
        处理单条 timeline。

        Returns:
            提取的记忆数量，-1 表示处理失败
        """
        fm = timeline_entry.frontmatter
        content = timeline_entry.content or ""
        file_path = Path(timeline_entry.file_path) if timeline_entry.file_path else None

        if not file_path:
            return -1

        # 隐私分级过滤
        sensitivity = fm.sensitivity or "normal"

        if sensitivity == "secret":
            # 永不提取，直接标记 archived
            await self.memory_mgr.update_status(file_path, "archived")
            return 0

        if sensitivity == "private":
            # 生成 pending 文件，不进入 facts
            await self.memory_mgr.create_pending(
                source_timeline=str(file_path.relative_to(self.memory_mgr.memory_dir)),
                summary=self._generate_summary(content),
                original_quote=content[:500],
                expires_days=PENDING_EXPIRE_DAYS,
            )
            # 标记 timeline 为 archived（pending 已生成，不再重复处理）
            await self.memory_mgr.update_status(file_path, "archived")
            return 0

        # normal 内容：调用 LLM 提取
        # Token 上限截断（保留完整句子边界）
        if len(content) > CONSOLIDATOR_MAX_INPUT_TOKENS:
            truncated = content[:CONSOLIDATOR_MAX_INPUT_TOKENS]
            last_period = max(truncated.rfind("。"), truncated.rfind("\n"))
            if last_period > 0:
                content = truncated[:last_period + 1] + "\n[内容截断，剩余部分待续处理]"
            else:
                content = truncated + "\n[内容截断]"

        # Phase 4 修复：指数退避重试调用 LLM
        extracted = None
        for attempt in range(3):  # 最多 3 次
            try:
                extracted = await self._call_llm_for_extraction(content)
                break
            except Exception:
                wait_time = 2 ** attempt  # 1s, 2s, 4s
                await asyncio.sleep(wait_time)

        if extracted is None:
            # 全部重试失败，标记为 retry_pending，下次优先处理
            await self.memory_mgr.update_status(file_path, "retry_pending")
            return -1

        if not extracted:
            # 无内容可提取，标记 archived
            await self.memory_mgr.update_status(file_path, "archived")
            return 0

        # 写入记忆 + 冲突检测
        count = 0
        for item in extracted:
            try:
                await self._write_extracted_memory(item, fm.date)
                count += 1
            except Exception:
                continue

        # 标记 timeline 为 archived
        await self.memory_mgr.update_status(file_path, "archived")

        return count

    def _generate_summary(self, content: str) -> str:
        """为 private 内容生成摘要"""
        summary = content[:200].strip()
        if len(content) > 200:
            summary += "..."
        return summary

    async def _call_llm_for_extraction(self, timeline_content: str) -> List[Dict[str, Any]]:
        """调用 LLM 提取结构化记忆（带成本估算）"""
        if not self.llm_service:
            return []

        prompt = CONSOLIDATOR_PROMPT.format(timeline_content=timeline_content)

        try:
            chunks = []
            # 粗略估算 input tokens（1 token ≈ 4 字符）
            input_tokens_estimate = len(prompt) // 4

            async for chunk in self.llm_service.generate_response(
                messages=[
                    {"role": "system", "content": "你是一个记忆归档助手，只输出 JSON。"},
                    {"role": "user", "content": prompt}
                ],
                enable_tools=False,
            ):
                chunks.append(chunk)

            raw = "".join(chunks)
            output_tokens_estimate = len(raw) // 4

            # Phase 4：成本估算（按 GPT-4o-mini 费率估算：$0.0015/1K input, $0.002/1K output）
            cost = (input_tokens_estimate / 1000 * 0.0015) + (output_tokens_estimate / 1000 * 0.002)
            self._daily_cost_usd += cost

            return self._parse_json_extraction(raw)
        except Exception:
            raise  # 抛出异常让上层处理重试

    def _parse_json_extraction(self, raw: str) -> List[Dict[str, Any]]:
        """解析 LLM 返回的 JSON"""
        if not raw or not raw.strip():
            return []

        import re
        text = raw.strip()

        # 提取 markdown 代码块
        code_block = re.search(r"```(?:json)?\s*([\s\S]*?)```", text)
        if code_block:
            text = code_block.group(1).strip()

        # 找 JSON 数组
        arr_start = text.find("[")
        arr_end = text.rfind("]")
        if arr_start != -1 and arr_end != -1 and arr_end > arr_start:
            text = text[arr_start:arr_end+1]

        try:
            parsed = json.loads(text)
            if isinstance(parsed, list):
                return parsed
            elif isinstance(parsed, dict):
                for key in ("memories", "facts", "skills", "results"):
                    if key in parsed and isinstance(parsed[key], list):
                        return parsed[key]
                return [parsed]
        except json.JSONDecodeError:
            return []

    async def _write_extracted_memory(self, item: Dict[str, Any], source_date: Optional[str]):
        """写入提取的记忆，处理冲突"""
        category = item.get("category", "fact")
        key = item.get("key", "未命名")
        content = item.get("content", "")

        if not key or not content:
            return

        # 构建 frontmatter
        fm_data = {
            "importance": item.get("importance", 3),
            "created_at": datetime.now().isoformat(),
            "updated_at": datetime.now().isoformat(),
            "status": "active",
        }

        # Skill 专属
        if category == "skill":
            fm_data["domain"] = normalize_domain(item.get("domain"))
            fm_data["proficiency"] = 1
            fm_data["verified"] = False
            fm_data["verification_count"] = 0
            fm_data["usage_count"] = 0
            fm_data["source_project"] = item.get("source_project", "global")
            fm_data["used_in_projects"] = [fm_data["source_project"]]

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
                content = "\n".join(parts)

        # 冲突检测
        conflict_key = item.get("conflict_with")
        if conflict_key:
            await self.memory_mgr.create_with_supersedes(
                scope="life" if category != "skill" else "work",
                category=category,
                key=key,
                content=content,
                frontmatter_data=fm_data,
            )
        else:
            conflict = await self.memory_mgr.check_conflict(
                key=key,
                scope="life" if category != "skill" else "work",
                category=category,
            )

            if conflict.has_conflict:
                await self.memory_mgr.create_with_supersedes(
                    scope="life" if category != "skill" else "work",
                    category=category,
                    key=key,
                    content=content,
                    frontmatter_data=fm_data,
                )
            else:
                await self.memory_mgr.create_memory(
                    scope="life" if category != "skill" else "work",
                    category=category,
                    key=key,
                    content=content,
                    frontmatter_data=fm_data,
                )

    async def generate_monthly_summary(self, year: int, month: int) -> Optional[Path]:
        """
        生成月度摘要（每月 1 号调用）。
        读取上月所有 archived timeline，生成摘要文件。
        """
        from backend.memory.utils import generate_monthly_summary_path

        monthly_path = generate_monthly_summary_path(year, month, self.memory_mgr.memory_dir)

        # 读取该月所有 archived timeline
        month_str = f"{year}/{month:02d}"
        timeline_dir = self.memory_mgr.memory_dir / "life" / "timeline" / month_str / "days"

        if not timeline_dir.exists():
            return None

        entries = []
        for md_file in sorted(timeline_dir.glob("*.md")):
            try:
                entry = await self.memory_mgr.read_memory(md_file)
                if entry and entry.frontmatter.status == "archived":
                    entries.append(entry)
            except Exception:
                continue

        if not entries:
            return None

        # 生成摘要内容
        lines = [f"# {year}年{month}月 月度摘要", ""]

        for entry in entries:
            date = entry.frontmatter.date or "未知日期"
            content_summary = (entry.content or "")[:100].replace("\n", " ")
            lines.append(f"- **{date}**: {content_summary}...")

        summary_content = "\n".join(lines)

        # 写入 monthly 文件
        monthly_path.parent.mkdir(parents=True, exist_ok=True)
        with open(monthly_path, "w", encoding=FILE_ENCODING) as f:
            f.write(summary_content)

        return monthly_path