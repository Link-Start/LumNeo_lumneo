"""
Lumneo 长期记忆系统 - MemoryRetriever 检索层
Phase 1 核心记忆闭环

职责：
- 按 scope + category 过滤检索
- FTS5 MATCH 全文检索
- 按 effective_importance 排序
- Token 预算硬截断
- 构造 System Prompt 记忆块
"""
import math
from pathlib import Path
from typing import List, Optional, Dict, Any, Tuple
from datetime import datetime

from backend.memory.config import (
    TOKEN_BUDGET_RETRIEVAL,
    TOKEN_BUDGET_SKILL,
    TOKEN_BUDGET_ANAPHORA,
    ANAPHORA_TRIGGER_WORDS,
    TIME_DECAY_CUTOFF,
)
from backend.memory.models import MemoryEntry, MemoryFrontmatter
from backend.memory.utils import read_markdown_file_sync
from backend.memory.fts_index import FTSIndexManager
from backend.memory.manager import MemoryManager


def estimate_tokens(text: str) -> int:
    """
    粗略估算文本的 Token 数。
    中文按 1 字 ≈ 1 token，英文按 1 word ≈ 1.3 token。
    """
    if not text:
        return 0

    # 简单启发式：中文字符数 + 英文单词数 * 1.3
    import re
    chinese_chars = len(re.findall(r'[\u4e00-\u9fff]', text))
    english_words = len(re.findall(r'[a-zA-Z]+', text))
    return chinese_chars + int(english_words * 1.3) + 10  # +10 作为 frontmatter 开销


class MemoryRetriever:
    """
    记忆检索器。

    负责从 memory 体系中检索相关记忆，按重要性排序，
    并在 Token 预算内截断，最终格式化为 System Prompt 可注入的文本块。
    """

    def __init__(
        self,
        memory_manager: MemoryManager,
        fts_manager: Optional[FTSIndexManager] = None,
    ):
        self.memory_mgr = memory_manager
        self.fts = fts_manager

    async def retrieve_for_life(
        self,
        query: str,
        token_budget: int = TOKEN_BUDGET_RETRIEVAL,
    ) -> str:
        """
        Life Mode 检索：读取 life + work（含 skills，过滤 secret）。

        Returns:
            格式化的记忆文本块，可直接注入 System Prompt
        """
        # 1. 检索 life 记忆（过滤 secret）
        life_memories = await self._retrieve_scope(
            query=query,
            scope="life",
            exclude_sensitivity="secret",
            limit=20,
        )

        # 2. 检索 work 记忆（含 skills）
        work_memories = await self._retrieve_scope(
            query=query,
            scope="work",
            limit=20,
        )

        # 3. 合并、去重、排序
        all_memories = life_memories + work_memories
        all_memories = self._deduplicate(all_memories)
        all_memories = self._sort_by_effective_importance(all_memories)

        # 4. Token 截断
        selected = self._truncate_by_token(all_memories, token_budget)

        # 5. 格式化
        return self._format_memory_block(selected, mode="life")

    async def retrieve_for_chat(
        self,
        query: str,
        project_tag: Optional[str] = None,
        token_budget: int = TOKEN_BUDGET_RETRIEVAL,
    ) -> str:
        """
        Chat Mode 检索：仅读取 work（含 skills），带 project_tag 过滤。

        Args:
            query: 用户输入作为检索 query
            project_tag: 当前 Chat 的项目标签（MVP 阶段可传 None）
            token_budget: Token 预算

        Returns:
            格式化的记忆文本块
        """
        # 1. 检索 work facts/preferences/people
        work_memories = await self._retrieve_scope(
            query=query,
            scope="work",
            limit=20,
        )

        # 2. 检索 skills（project_tag 过滤）
        skills = await self._retrieve_skills(
            query=query,
            project_tag=project_tag,
            limit=10,
        )

        # 3. 强指代回溯（如果 query 包含触发词）
        anaphora_memories = await self._retrieve_anaphora(query)

        # 4. 合并、去重、排序
        all_memories = work_memories + skills + anaphora_memories
        all_memories = self._deduplicate(all_memories)
        all_memories = self._sort_by_effective_importance(all_memories)

        # 5. Token 截断（skills 单独预留预算）
        selected_work = self._truncate_by_token(
            [m for m in all_memories if m.frontmatter.category != "skill"],
            token_budget - TOKEN_BUDGET_SKILL,
        )
        selected_skills = self._truncate_by_token(
            [m for m in all_memories if m.frontmatter.category == "skill"],
            TOKEN_BUDGET_SKILL,
        )

        selected = selected_work + selected_skills

        # 6. 格式化
        return self._format_memory_block(selected, mode="chat")

    async def _retrieve_scope(
        self,
        query: str,
        scope: str,
        exclude_sensitivity: Optional[str] = None,
        limit: int = 20,
    ) -> List[MemoryEntry]:
        """
        检索指定 scope 的记忆。
        匹配策略（从严格到宽松）：
        1. 关键词匹配 key + content
        2. 如果关键词没命中，至少匹配 key 字段
        3. 如果 query 很短或没匹配，返回最近更新的 active 记忆兜底
        """
        from backend.memory.config import TIME_DECAY_CUTOFF
        
        # 取所有 active 记忆
        all_memories = await self.memory_mgr.search_memories(
            scope=scope,
            status="active",
            limit=200,
        )
        
        # 过滤敏感度和 decay
        candidates = []
        for entry in all_memories:
            if exclude_sensitivity and entry.frontmatter.sensitivity == exclude_sensitivity:
                continue
            if entry.effective_importance < TIME_DECAY_CUTOFF:
                continue
            candidates.append(entry)
        
        if not query or not query.strip():
            # 无 query，返回最近更新的
            candidates.sort(key=lambda x: x.frontmatter.updated_at or "", reverse=True)
            return candidates[:limit]
        
        query_lower = query.lower().strip()
        keywords = [k for k in query_lower.split() if len(k) > 1]  # 过滤单字
        
        # 第一层：关键词匹配 key + content
        matched = []
        for entry in candidates:
            text = (entry.frontmatter.key + " " + entry.content).lower()
            if any(kw in text for kw in keywords):
                matched.append(entry)
        
        # 第二层：如果上面没命中，尝试只匹配 key（更宽松）
        if not matched:
            for entry in candidates:
                key_lower = entry.frontmatter.key.lower()
                # 简单同义词映射
                synonym_map = {
                    "后端": ["backend", "后端", "server"],
                    "前端": ["frontend", "前端", "client"],
                    "数据库": ["database", "db", "数据库", "sql"],
                    "框架": ["framework", "框架", "fastapi", "react", "vue"],
                }
                for kw in keywords:
                    # 直接匹配 key
                    if kw in key_lower:
                        matched.append(entry)
                        break
                    # 同义词匹配
                    for syn_key, syn_list in synonym_map.items():
                        if kw == syn_key or kw in syn_key:
                            for syn in syn_list:
                                if syn in key_lower:
                                    matched.append(entry)
                                    break
                            break
        
        # 第三层：还是没命中，返回最近更新的几条兜底
        if not matched:
            candidates.sort(key=lambda x: x.frontmatter.updated_at or "", reverse=True)
            return candidates[:min(limit, 5)]
        
        # 按 effective_importance 排序
        matched = self._sort_by_effective_importance(matched)
        return matched[:limit]

    # async def _retrieve_scope(
    #     self,
    #     query: str,
    #     scope: str,
    #     exclude_sensitivity: Optional[str] = None,
    #     limit: int = 20,
    # ) -> List[MemoryEntry]:
    #     """
    #     检索指定 scope 的记忆。
    #     优先使用 FTS5，FTS5 不可用时回退到文件系统遍历。
    #     """
    #     results = []

    #     # 尝试 FTS5 检索
    #     if self.fts:
    #         try:
    #             fts_results = await self.fts.search(
    #                 query=query,
    #                 scope=scope,
    #                 limit=limit * 2,  # 多取一些用于过滤
    #             )

    #             for r in fts_results:
    #                 entry = await self.memory_mgr.read_memory(Path(r["path"]))
    #                 if entry:
    #                     # 过滤敏感度
    #                     if exclude_sensitivity and entry.frontmatter.sensitivity == exclude_sensitivity:
    #                         continue
    #                     # 过滤 superseded
    #                     if entry.frontmatter.status == "superseded":
    #                         continue
    #                     # 过滤 Time-Decay 过低的（Phase 4 完整实现，这里简单过滤）
    #                     if entry.effective_importance < TIME_DECAY_CUTOFF:
    #                         continue
    #                     results.append(entry)
    #         except Exception:
    #             pass  # FTS5 失败则回退

    #     # FTS5 无结果或失败，回退文件系统检索
    #     if not results:
    #         results = await self.memory_mgr.search_memories(
    #             scope=scope,
    #             status="active",
    #             limit=limit,
    #         )

    #         # 简单关键词过滤（非 FTS5 的兜底方案）
    #         if query:
    #             keywords = query.lower().split()
    #             filtered = []
    #             for entry in results:
    #                 text = (entry.frontmatter.key + " " + entry.content).lower()
    #                 if any(kw in text for kw in keywords):
    #                     filtered.append(entry)
    #             results = filtered

    #     return results[:limit]

    async def _retrieve_skills(
        self,
        query: str,
        project_tag: Optional[str] = None,
        limit: int = 10,
    ) -> List[MemoryEntry]:
        """
        检索 Skill 记忆。
        MVP 简化：关键词匹配 + project_tag 过滤。
        Phase 3 会替换为 domain 投票聚类 + 熟练度门槛。
        """
        skills = await self.memory_mgr.search_memories(
            scope="work",
            category="skill",
            status="active",
            limit=limit * 2,
        )

        # project_tag 过滤
        if project_tag:
            filtered = []
            for s in skills:
                source_project = s.frontmatter.source_project or "global"
                used_projects = s.frontmatter.used_in_projects or []

                # 匹配 source_project 或 used_in_projects
                if source_project == project_tag or project_tag in used_projects:
                    filtered.append(s)
            skills = filtered
        else:
            # 无 project_tag 时只加载 global
            skills = [s for s in skills if (s.frontmatter.source_project or "global") == "global"]

        # 关键词过滤
        if query:
            keywords = query.lower().split()
            filtered = []
            for s in skills:
                text = (s.frontmatter.key + " " + s.content + " " + (s.frontmatter.domain or "")).lower()
                if any(kw in text for kw in keywords):
                    filtered.append(s)
            skills = filtered

        return skills[:limit]

    async def _retrieve_anaphora(self, query: str) -> List[MemoryEntry]:
        """
        强指代回溯：检测"上次""之前"等词，检索最近 24h 更新的记忆。
        Phase 3 会完善为独立 400 Token 池 + 三级降级。
        """
        # 检测触发词
        has_anaphora = any(word in query for word in ANAPHORA_TRIGGER_WORDS)
        if not has_anaphora:
            return []

        # 检索最近 24h 更新的记忆
        from datetime import timedelta
        cutoff = (datetime.now() - timedelta(hours=24)).isoformat()

        all_memories = await self.memory_mgr.search_memories(
            scope="work",
            status="active",
            limit=50,
        )

        # 按 updated_at 过滤最近 24h
        recent = []
        for m in all_memories:
            if m.frontmatter.updated_at and m.frontmatter.updated_at > cutoff:
                recent.append(m)

        # 按 updated_at 倒序取 Top 3
        recent.sort(key=lambda x: x.frontmatter.updated_at or "", reverse=True)
        return recent[:3]

    def _deduplicate(self, memories: List[MemoryEntry]) -> List[MemoryEntry]:
        """按 file_path 去重"""
        seen = set()
        result = []
        for m in memories:
            if m.file_path and m.file_path not in seen:
                seen.add(m.file_path)
                result.append(m)
        return result

    def _sort_by_effective_importance(self, memories: List[MemoryEntry]) -> List[MemoryEntry]:
        """按 effective_importance 降序排序"""
        return sorted(memories, key=lambda x: x.effective_importance, reverse=True)

    def _truncate_by_token(
        self,
        memories: List[MemoryEntry],
        budget: int,
    ) -> List[MemoryEntry]:
        """
        按 Token 预算硬截断。
        优先保留排在前面的记忆，超长记忆只保留 frontmatter 摘要。
        """
        selected = []
        used = 0

        for entry in memories:
            # 估算当前记忆的 Token 消耗
            text = self._format_single_memory(entry, full_content=True)
            tokens = estimate_tokens(text)

            if used + tokens <= budget:
                selected.append(entry)
                used += tokens
            else:
                # 尝试降级为仅 frontmatter
                summary_text = self._format_single_memory(entry, full_content=False)
                summary_tokens = estimate_tokens(summary_text)

                if used + summary_tokens <= budget:
                    # 创建一个"降级版"entry（不修改原文件，仅用于注入）
                    truncated_entry = MemoryEntry(
                        frontmatter=entry.frontmatter,
                        content="",  # 不注入正文
                        file_path=entry.file_path,
                    )
                    selected.append(truncated_entry)
                    used += summary_tokens
                # 否则跳过这条记忆

        return selected

    def _format_single_memory(self, entry: MemoryEntry, full_content: bool = True) -> str:
        """格式化单条记忆为文本"""
        fm = entry.frontmatter
        scope_label = "生活" if entry.scope == "life" else "工作"

        if fm.category == "skill":
            prefix = f"[skill-{fm.domain or 'general'}]"
        else:
            prefix = f"[{scope_label}]"

        if full_content and entry.content:
            return f"{prefix} {fm.key}: {entry.content}"
        else:
            return f"{prefix} {fm.key}"

    def _format_memory_block(
        self,
        memories: List[MemoryEntry],
        mode: str = "life",
    ) -> str:
        """
        将记忆列表格式化为 System Prompt 可注入的文本块。

        Args:
            memories: 记忆条目列表
            mode: "life" 或 "chat"
        """
        if not memories:
            return ""

        lines = []

        if mode == "life":
            lines.append("## 相关记忆")
        else:
            lines.append("## 工作记忆")

        # 分类输出
        facts = [m for m in memories if m.frontmatter.category not in ("skill", "pending")]
        skills = [m for m in memories if m.frontmatter.category == "skill"]

        if facts:
            for entry in facts:
                fm = entry.frontmatter
                scope_label = "生活" if entry.scope == "life" else "工作"

                if entry.content:
                    lines.append(f"· [{scope_label}] {fm.key}: {entry.content[:150]}")
                else:
                    lines.append(f"· [{scope_label}] {fm.key}")

        if skills:
            lines.append("\n## 当前相关技能")
            for entry in skills:
                fm = entry.frontmatter
                prof = fm.proficiency or 1
                verified = "已验证" if fm.verified else "待验证"
                lines.append(
                    f"· [skill-{fm.domain or 'general'}] {fm.key}: "
                    f"{entry.content[:100]}... (熟练度:{prof}, {verified})"
                )

        return "\n".join(lines)
