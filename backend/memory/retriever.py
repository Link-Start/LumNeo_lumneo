# backend/memory/retriever.py
"""
Lumneo 长期记忆系统 - MemoryRetriever 检索层
Phase 3 完整修复版

修复：
- #3: 格式化输出使用 \n 而非 \\n
- #4: 强指代回溯设置 self._last_anaphora
- #7: Token 预算防负数
- #8: domain 投票在 project_tag 过滤之后
- #9: @skill 显式引用更新 used_in_projects
- #10: 摘要降级保留 content[:50] 而非清空
"""
import re
import math
from pathlib import Path
from typing import List, Optional, Dict, Any, Tuple
from datetime import datetime, timedelta

from backend.memory.config import (
    TOKEN_BUDGET_RETRIEVAL,
    TOKEN_BUDGET_SKILL,
    TOKEN_BUDGET_ANAPHORA,
    ANAPHORA_TRIGGER_WORDS,
    TIME_DECAY_CUTOFF,
    DOMAIN_WHITELIST,
)
from backend.memory.models import MemoryEntry, MemoryFrontmatter
from backend.memory.utils import read_markdown_file_sync
from backend.memory.fts_index import FTSIndexManager
from backend.memory.manager import MemoryManager


def estimate_tokens(text: str) -> int:
    """粗略估算 Token 数"""
    if not text:
        return 0
    chinese_chars = len(re.findall(r'[\u4e00-\u9fff]', text))
    english_words = len(re.findall(r'[a-zA-Z]+', text))
    return chinese_chars + int(english_words * 1.3) + 10


class MemoryRetriever:
    """记忆检索器"""

    def __init__(
        self,
        memory_manager: MemoryManager,
        fts_manager: Optional[FTSIndexManager] = None,
    ):
        self.memory_mgr = memory_manager
        self.fts = fts_manager
        self._last_anaphora: List[MemoryEntry] = []  # #4 修复：初始化

    # ==================== 主入口 ====================

    async def retrieve_for_life(
        self,
        query: str,
        token_budget: int = TOKEN_BUDGET_RETRIEVAL,
    ) -> str:
        """Life Mode：读取 life + work（含 skills，过滤 secret）"""
        # 1. 检索 life 记忆（过滤 secret）
        life_memories = await self._retrieve_scope(
            query=query, scope="life",
            exclude_sensitivity="secret", limit=20,
        )

        # 2. 检索 work 记忆（含 skills）
        work_memories = await self._retrieve_scope(
            query=query, scope="work", limit=20,
        )

        # 3. 合并、去重、排序
        all_memories = self._deduplicate(life_memories + work_memories)
        all_memories = self._sort_by_effective_importance(all_memories)

        # 4. Token 截断
        selected = self._truncate_by_token(all_memories, token_budget)

        return self._format_memory_block(selected, mode="life")

    async def retrieve_for_chat(
        self,
        query: str,
        project_tag: Optional[str] = None,
        token_budget: int = TOKEN_BUDGET_RETRIEVAL,
    ) -> str:
        """Chat Mode：仅读取 work，带 project_tag 过滤 + @skill 引用"""
        # 1. 强指代回溯
        anaphora_memories = await self._retrieve_anaphora(query)

        # 2. @skill 显式引用 (#9 修复：传入 project_tag)
        explicit_skills = await self._retrieve_explicit_skill(query, project_tag)

        # 3. 常规 work 记忆检索
        work_memories = await self._retrieve_scope(
            query=query, scope="work", limit=20,
        )

        # 4. Skill 动态注入（#8 修复：domain 投票在 project_tag 过滤之后）
        dynamic_skills = await self._retrieve_skills_dynamic(
            query=query, project_tag=project_tag, limit=10,
        )

        # 5. 合并、去重
        all_memories = self._deduplicate(
            work_memories + dynamic_skills + explicit_skills + anaphora_memories
        )

        # 6. 与强指代回溯去重（anaphora 已单独获取，这里从常规结果中移除重复的）
        anaphora_paths = {m.file_path for m in anaphora_memories}
        filtered = [m for m in all_memories if m.file_path not in anaphora_paths]

        # 7. 按 effective_importance 排序
        filtered = self._sort_by_effective_importance(filtered)

        # 8. Token 预算分配 (#7 修复：防负数)
        # - 强指代回溯：独立 400 Token 池
        # - Skills：独立 800 Token 池
        # - 其他 work 记忆：剩余预算
        self._last_anaphora = anaphora_memories  # #4 修复：保存 anaphora 引用
        selected_anaphora = self._truncate_anaphora(anaphora_memories, TOKEN_BUDGET_ANAPHORA)

        non_skill = [m for m in filtered if m.frontmatter.category != "skill"]
        skill_items = [m for m in filtered if m.frontmatter.category == "skill"]

        # #7 修复：防负数预算
        work_budget = max(0, token_budget - TOKEN_BUDGET_SKILL)
        selected_work = self._truncate_by_token(non_skill, work_budget)
        selected_skills = self._truncate_by_token(skill_items, TOKEN_BUDGET_SKILL)

        # 合并：work + skills + anaphora
        final = selected_work + selected_skills + selected_anaphora

        return self._format_memory_block(final, mode="chat")

    # ==================== 检索子方法 ====================

    async def _retrieve_scope(
        self,
        query: str,
        scope: str,
        exclude_sensitivity: Optional[str] = None,
        limit: int = 20,
    ) -> List[MemoryEntry]:
        """检索指定 scope 的记忆（宽松匹配 + 兜底）"""
        all_memories = await self.memory_mgr.search_memories(
            scope=scope, status="active", limit=500,
        )

        candidates = []
        for entry in all_memories:
            if exclude_sensitivity and entry.frontmatter.sensitivity == exclude_sensitivity:
                continue
            if entry.effective_importance < TIME_DECAY_CUTOFF:
                continue
            candidates.append(entry)

        if not query or not query.strip():
            candidates.sort(key=lambda x: x.frontmatter.updated_at or "", reverse=True)
            return candidates[:limit]

        query_lower = query.lower().strip()
        keywords = [w for w in re.findall(r'[\u4e00-\u9fff]{2,}|[a-zA-Z]{2,}', query_lower)]

        matched = []
        for entry in candidates:
            text = (entry.frontmatter.key + " " + entry.content).lower()
            if any(kw in text for kw in keywords):
                matched.append(entry)

        if not matched:
            candidates.sort(key=lambda x: x.frontmatter.updated_at or "", reverse=True)
            return candidates[:min(limit, 5)]

        matched = self._sort_by_effective_importance(matched)
        return matched[:limit]

    async def _retrieve_skills_dynamic(
        self,
        query: str,
        project_tag: Optional[str] = None,
        limit: int = 10,
    ) -> List[MemoryEntry]:
        """
        Skill 动态注入（#8 修复：先 project_tag 过滤，再 domain 投票）：
        1. 召回所有 active skills
        2. 关键词粗筛
        3. project_tag 过滤 + 熟练度门槛
        4. domain 投票聚类（取 Top 1-2 domain）
        """
        # 1. 召回所有 active skills
        all_skills = await self.memory_mgr.search_memories(
            scope="work", category="skill", status="active", limit=100,
        )

        # 2. 关键词粗筛
        if query:
            query_lower = query.lower()
            keywords = re.findall(r'[\u4e00-\u9fff]{2,}|[a-zA-Z]{2,}', query_lower)
            filtered = []
            for s in all_skills:
                text = (s.frontmatter.key + " " + s.content + " " + (s.frontmatter.domain or "")).lower()
                if any(kw in text for kw in keywords):
                    filtered.append(s)
            all_skills = filtered

        # #8 修复：先 project_tag 过滤 + 熟练度门槛
        project_filtered = []
        for s in all_skills:
            fm = s.frontmatter

            # project_tag 过滤
            source_project = fm.source_project or "global"
            used_projects = fm.used_in_projects or []

            if project_tag:
                if source_project != project_tag and project_tag not in used_projects:
                    continue
            else:
                if source_project != "global":
                    continue

            # 熟练度门槛：verified=true 或 usage_count>=2 才自动注入
            # proficiency=1 的新技能不参与自动注入（除非用户显式 @ 引用）
            if fm.verified or (fm.usage_count or 0) >= 2:
                project_filtered.append(s)

        # #8 修复：再 domain 投票聚类（基于过滤后的结果）
        domain_votes: Dict[str, int] = {}
        for s in project_filtered:
            d = s.frontmatter.domain or "general"
            domain_votes[d] = domain_votes.get(d, 0) + 1

        top_domains = sorted(domain_votes.keys(), key=lambda d: domain_votes[d], reverse=True)[:2]

        # domain 过滤（只保留 Top 1-2 domain 的 skills）
        qualified = []
        for s in project_filtered:
            fm = s.frontmatter
            if fm.domain not in top_domains and fm.domain != "general":
                continue
            qualified.append(s)

        # 按 effective_importance 排序，避免随机取 limit
        qualified = self._sort_by_effective_importance(qualified)
        return qualified[:limit]

    async def _retrieve_explicit_skill(
        self,
        query: str,
        project_tag: Optional[str] = None,  # #9 修复：接收 project_tag
    ) -> List[MemoryEntry]:
        """
        解析 @skill_技能名 显式引用。
        完全跳过 project_tag 过滤，强制加载最新版本。
        #9 修复：更新 used_in_projects 和 usage_count
        """
        import re
        pattern = r'@skill_([\w\u4e00-\u9fff]+)'
        matches = re.findall(pattern, query)

        if not matches:
            return []

        results = []
        for skill_key in matches:
            # 按 key 精确搜索
            skills = await self.memory_mgr.search_memories(
                scope="work", category="skill", key=skill_key, limit=1,
            )
            if skills:
                skill = skills[0]
                fm = skill.frontmatter

                # #9 修复：更新 usage_count
                new_usage = (fm.usage_count or 0) + 1

                # #9 修复：追加 used_in_projects
                used_projects = list(fm.used_in_projects or [])
                current_project = project_tag or "global"
                if current_project not in used_projects:
                    used_projects.append(current_project)

                await self.memory_mgr.update_memory(
                    Path(skill.file_path),
                    frontmatter_updates={
                        "usage_count": new_usage,
                        "used_in_projects": used_projects,
                    },
                )
                # 更新内存对象
                fm.usage_count = new_usage
                fm.used_in_projects = used_projects
                results.append(skill)

        return results

    async def _retrieve_anaphora(self, query: str) -> List[MemoryEntry]:
        """
        强指代回溯：
        - 命中触发词白名单
        - 以 updated_at 为准，最近 24h Top 3
        - 独立 Token 池，三级降级
        """
        has_anaphora = any(word in query for word in ANAPHORA_TRIGGER_WORDS)
        if not has_anaphora:
            return []

        cutoff = (datetime.now() - timedelta(hours=24)).isoformat()

        all_memories = await self.memory_mgr.search_memories(
            scope="work", status="active", limit=50,
        )

        recent = [m for m in all_memories if m.frontmatter.updated_at and m.frontmatter.updated_at > cutoff]
        recent.sort(key=lambda x: x.frontmatter.updated_at or "", reverse=True)

        return recent[:3]

    # ==================== 工具方法 ====================

    def _deduplicate(self, memories: List[MemoryEntry]) -> List[MemoryEntry]:
        seen = set()
        result = []
        for m in memories:
            if m.file_path and m.file_path not in seen:
                seen.add(m.file_path)
                result.append(m)
        return result

    def _sort_by_effective_importance(self, memories: List[MemoryEntry]) -> List[MemoryEntry]:
        return sorted(memories, key=lambda x: x.effective_importance, reverse=True)

    def _truncate_by_token(self, memories: List[MemoryEntry], budget: int) -> List[MemoryEntry]:
        selected = []
        used = 0
        for entry in memories:
            text = self._format_single_memory(entry, full_content=True)
            tokens = estimate_tokens(text)
            if used + tokens <= budget:
                selected.append(entry)
                used += tokens
            else:
                # #10 修复：降级为保留 content[:50] 的摘要，而非清空
                summary_text = self._format_single_memory(entry, full_content=False)
                summary_tokens = estimate_tokens(summary_text)
                if used + summary_tokens <= budget:
                    # 保留前 50 字摘要
                    truncated_content = entry.content[:50] if entry.content else ""
                    truncated = MemoryEntry(
                        frontmatter=entry.frontmatter,
                        content=truncated_content,
                        file_path=entry.file_path,
                    )
                    selected.append(truncated)
                    used += summary_tokens
        return selected

    def _truncate_anaphora(self, memories: List[MemoryEntry], budget: int) -> List[MemoryEntry]:
        """强指代回溯独立 Token 池 + 三级降级"""
        selected = []
        used = 0
        for entry in memories:
            # 第一级：完整正文
            text = self._format_single_memory(entry, full_content=True)
            tokens = estimate_tokens(text)
            if used + tokens <= budget:
                selected.append(entry)
                used += tokens
                continue

            # 第二级：仅 Frontmatter + 前 50 字摘要
            fm_text = f"[{entry.frontmatter.category}] {entry.frontmatter.key}: {entry.content[:50]}"
            fm_tokens = estimate_tokens(fm_text)
            if used + fm_tokens <= budget:
                truncated = MemoryEntry(
                    frontmatter=entry.frontmatter,
                    content=entry.content[:50],
                    file_path=entry.file_path,
                )
                selected.append(truncated)
                used += fm_tokens
                continue

            # 第三级：仅 key + category（约 60 Token）
            mini_text = f"[{entry.frontmatter.category}] {entry.frontmatter.key}"
            mini_tokens = estimate_tokens(mini_text)
            if used + mini_tokens <= budget:
                mini = MemoryEntry(
                    frontmatter=entry.frontmatter,
                    content="",
                    file_path=entry.file_path,
                )
                selected.append(mini)
                used += mini_tokens
        return selected

    def _format_single_memory(self, entry: MemoryEntry, full_content: bool = True) -> str:
        fm = entry.frontmatter
        scope_label = "生活" if entry.scope == "life" else "工作"
        if fm.category == "skill":
            prefix = f"[skill-{fm.domain or 'general'}]"
        else:
            prefix = f"[{scope_label}]"
        if full_content and entry.content:
            return f"{prefix} {fm.key}: {entry.content}"
        else:
            # #10 修复：降级时保留前 50 字
            snippet = entry.content[:50] if entry.content else ""
            return f"{prefix} {fm.key}: {snippet}"

    def _format_memory_block(self, memories: List[MemoryEntry], mode: str = "life") -> str:
        if not memories:
            return ""

        lines = []
        if mode == "life":
            lines.append("## 相关记忆")
        else:
            lines.append("## 工作记忆")

        facts = [m for m in memories if m.frontmatter.category not in ("skill", "pending")]
        skills = [m for m in memories if m.frontmatter.category == "skill"]
        anaphora = [m for m in memories if m in getattr(self, '_last_anaphora', [])]

        if anaphora:
            lines.append("\n### 近期相关")
            for entry in anaphora:
                fm = entry.frontmatter
                scope_label = "生活" if entry.scope == "life" else "工作"
                content = entry.content[:150] if entry.content else ""
                lines.append(f"· [{scope_label}] {fm.key}: {content}")

        if facts:
            for entry in facts:
                fm = entry.frontmatter
                scope_label = "生活" if entry.scope == "life" else "工作"
                content = entry.content[:150] if entry.content else ""
                lines.append(f"· [{scope_label}] {fm.key}: {content}")

        if skills:
            lines.append("\n## 当前相关技能")
            for entry in skills:
                fm = entry.frontmatter
                prof = fm.proficiency or 1
                verified = "已验证" if fm.verified else "待验证"
                content = entry.content[:100] if entry.content else ""
                lines.append(
                    f"· [skill-{fm.domain or 'general'}] {fm.key}: {content} "
                    f"(熟练度:{prof}, {verified})"
                )

        return "\n".join(lines)