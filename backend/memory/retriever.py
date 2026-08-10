# backend/memory/retriever.py
"""
Lumneo 长期记忆系统 - MemoryRetriever 检索层
"""
import re
from pathlib import Path
from typing import List, Optional, Dict
from datetime import datetime, timedelta

from backend.memory.config import (
    TOKEN_BUDGET_RETRIEVAL,
    TOKEN_BUDGET_SKILL,
    TOKEN_BUDGET_ANAPHORA,
    ANAPHORA_TRIGGER_WORDS,
    TIME_DECAY_CUTOFF,
)
from backend.memory.models import MemoryEntry
from backend.memory.utils import estimate_tokens
from backend.memory.fts_index import FTSIndexManager
from backend.memory.manager import MemoryManager


class MemoryRetriever:
    """记忆检索器"""

    def __init__(
        self,
        memory_manager: MemoryManager,
        fts_manager: Optional[FTSIndexManager] = None,
    ):
        self.memory_mgr = memory_manager
        self.fts = fts_manager
        self._last_anaphora: List[MemoryEntry] = []

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

        # 2. @skill 显式引用 (传入 project_tag)
        explicit_skills = await self._retrieve_explicit_skill(query, project_tag)

        # 3. 常规 work 记忆检索（带 project_tag 过滤）
        work_memories = await self._retrieve_scope(
            query=query, scope="work", project_tag=project_tag, limit=20,
        )

        # 4. Skill 动态注入（domain 投票在 project_tag 过滤之后）
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

        # 8. Token 预算分配 (防负数)
        self._last_anaphora = anaphora_memories  # 保存 anaphora 引用
        
        # 1. anaphora 先扣（必须保留）
        selected_anaphora = self._truncate_anaphora(anaphora_memories, TOKEN_BUDGET_ANAPHORA)
        anaphora_used = sum(
            estimate_tokens(self._format_single_memory(m, full_content=True)) 
            for m in selected_anaphora
        )
        remaining = max(0, token_budget - anaphora_used)

        # 2. skills 再扣
        skill_items = [m for m in filtered if m.frontmatter.category == "skill"]
        skill_budget = min(TOKEN_BUDGET_SKILL, remaining)
        selected_skills = self._truncate_by_token(skill_items, skill_budget)
        skills_used = sum(
            estimate_tokens(self._format_single_memory(m, full_content=True)) 
            for m in selected_skills
        )
        remaining = max(0, remaining - skills_used)

        # 3. 其他 work 记忆用剩余预算
        non_skill = [m for m in filtered if m.frontmatter.category != "skill"]
        selected_work = self._truncate_by_token(non_skill, remaining)

        # 合并：work + skills + anaphora
        final = selected_work + selected_skills + selected_anaphora

        formatted = self._format_memory_block(final, mode="chat")

        # 对整体格式化文本做最终 Token 截断，防止 System Prompt 超长
        total_tokens = estimate_tokens(formatted)
        if total_tokens > token_budget:
            # 保守截断：按 token_budget 的 2 倍字符数作为安全上限
            max_chars = token_budget * 2
            if len(formatted) > max_chars:
                formatted = formatted[:max_chars]
                # 尝试在最后一个段落边界截断
                last_para = formatted.rfind("\n\n")
                if last_para > int(max_chars * 0.8):
                    formatted = formatted[:last_para]
                formatted += "\n\n[记忆内容因长度限制被截断]"

        return formatted

    # ==================== 检索子方法 ====================

    async def _retrieve_scope(
        self,
        query: str,
        scope: str,
        project_tag: Optional[str] = None,
        exclude_sensitivity: Optional[str] = None,
        limit: int = 20,
    ) -> List[MemoryEntry]:
        """检索指定 scope 的记忆（FTS5 优先 + 兜底遍历）"""
        candidates: List[MemoryEntry] = []

        # === 第一优先级：FTS5 全文检索 ===
        if self.fts and query and query.strip():
            try:
                fts_results = await self.fts.search(
                    query=query,
                    scope=scope,
                    project_tag=project_tag,
                    limit=limit * 3,  # 多召回一些，供后续过滤
                )
                for row in fts_results:
                    path = Path(row["path"])
                    if not path.exists():
                        continue
                    entry = await self.memory_mgr.read_memory(path)
                    if entry:
                        candidates.append(entry)
            except Exception:
                # FTS 失败时静默回退到文件遍历
                candidates = []

        # === 第二优先级：文件遍历兜底 ===
        if not candidates:
            candidates = await self.memory_mgr.search_memories(
                scope=scope,
                status="active",
                project_tag=project_tag,
                limit=500,
            )

        # === 过滤 ===
        filtered = []
        for entry in candidates:
            # 排除 pending 目录文件（待确认状态，不应参与检索）
            if entry.file_path and "/pending/" in entry.file_path:
                continue
            if exclude_sensitivity and entry.frontmatter.sensitivity == exclude_sensitivity:
                continue
            if entry.effective_importance < TIME_DECAY_CUTOFF:
                continue
            # project_tag 过滤（FTS 结果可能未过滤，这里补一刀）
            if project_tag:
                fm = entry.frontmatter
                source_project = fm.source_project or "global"
                used_projects = fm.used_in_projects or []
                if source_project != project_tag and project_tag not in used_projects:
                    continue
            filtered.append(entry)

        # === 无 query 时按更新时间倒序 ===
        if not query or not query.strip():
            filtered.sort(key=lambda x: x.frontmatter.updated_at or "", reverse=True)
            return filtered[:limit]

        # === 有 query 时做关键词粗筛（FTS 已做大部分工作，这里做补充） ===
        query_lower = query.lower().strip()
        keywords = [w for w in re.findall(r'[一-鿿]{1,}|[a-zA-Z]{2,}', query_lower)]

        if keywords:
            matched = []
            for entry in filtered:
                text = (entry.frontmatter.key + " " + entry.content).lower()
                if any(kw in text for kw in keywords):
                    matched.append(entry)
            if matched:
                filtered = matched
            else:
                # FTS 没命中且关键词也没命中，取最近更新的前 5 条兜底
                filtered.sort(key=lambda x: x.frontmatter.updated_at or "", reverse=True)
                return filtered[:min(limit, 5)]

        filtered = self._sort_by_effective_importance(filtered)
        return filtered[:limit]

    async def _retrieve_skills_dynamic(
        self,
        query: str,
        project_tag: Optional[str] = None,
        limit: int = 10,
    ) -> List[MemoryEntry]:
        """
        Skill 动态注入（先 project_tag 过滤，再 domain 投票）：
        1. 召回所有 active skills
        2. 关键词粗筛
        3. project_tag 过滤 + 熟练度门槛
        4. domain 投票聚类（取 Top 1-2 domain）
        5. 自动注入时同步更新 used_in_projects / usage_count
        """
        # 1. 召回所有 active skills
        all_skills = await self.memory_mgr.search_memories(
            scope="work", category="skill", status="active", limit=100,
        )

        # 2. 关键词粗筛
        if query:
            query_lower = query.lower()
            keywords = re.findall(r'[一-鿿]{2,}|[a-zA-Z]{2,}', query_lower)
            filtered = []
            for s in all_skills:
                text = (s.frontmatter.key + " " + s.content + " " + (s.frontmatter.domain or "")).lower()
                if any(kw in text for kw in keywords):
                    filtered.append(s)
            all_skills = filtered

        # 先 project_tag 过滤 + 熟练度门槛
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

        # 再 domain 投票聚类（基于过滤后的结果）
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
        selected = qualified[:limit]

        # === 自动注入时更新 used_in_projects / usage_count ===
        for skill in selected:
            fm = skill.frontmatter
            used_projects = list(fm.used_in_projects or [])
            current_project = project_tag or "global"
            need_update = False

            if current_project != "global" and current_project not in used_projects:
                used_projects.append(current_project)
                need_update = True

            new_usage = (fm.usage_count or 0) + 1
            if not need_update:
                # 即使 project 已存在，也至少更新 usage_count
                need_update = True

            if need_update and skill.file_path:
                try:
                    await self.memory_mgr.update_memory(
                        Path(skill.file_path),
                        frontmatter_updates={
                            "usage_count": new_usage,
                            "used_in_projects": used_projects,
                        },
                    )
                    # 文件写入成功后再同步内存对象
                    fm.usage_count = new_usage
                    fm.used_in_projects = used_projects
                except Exception as e:
                    import logging
                    logging.getLogger(__name__).warning(f"更新 skill 动态注入统计失败 {skill.file_path}: {e}")
                    # 静默失败，不影响检索

        return selected

    async def _retrieve_explicit_skill(
        self,
        query: str,
        project_tag: Optional[str] = None,
    ) -> List[MemoryEntry]:
        """
        解析 @skill_技能名 显式引用。
        完全跳过 project_tag 过滤，强制加载最新版本。
        更新 used_in_projects 和 usage_count
        """
        import re
        pattern = r'@skill_([\w一-鿿]+)'
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

                new_usage = (fm.usage_count or 0) + 1

                used_projects = list(fm.used_in_projects or [])
                current_project = project_tag or "global"
                if current_project not in used_projects:
                    used_projects.append(current_project)

                try:
                    await self.memory_mgr.update_memory(
                        Path(skill.file_path),
                        frontmatter_updates={
                            "usage_count": new_usage,
                            "used_in_projects": used_projects,
                        },
                    )
                    # 文件写入成功后再更新内存对象，避免状态不一致
                    fm.usage_count = new_usage
                    fm.used_in_projects = used_projects
                    results.append(skill)
                except Exception as e:
                    import logging
                    logging.getLogger(__name__).warning(f"更新 skill 使用统计失败 {skill.file_path}: {e}")

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

        # search_memories 已用 updated_since 过滤，无需二次过滤
        all_memories = await self.memory_mgr.search_memories(
            scope="work", status="active", updated_since=cutoff, limit=50,
        )

        # 直接按 updated_at 倒序取 Top 3
        all_memories.sort(key=lambda x: x.frontmatter.updated_at or "", reverse=True)
        return all_memories[:3]

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
                # 降级为保留 content[:50] 的摘要，而非清空
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
            # 降级时保留前 50 字
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

        facts = [m for m in memories if m.frontmatter.category not in ("skill", "pending") and m.file_path not in anaphora_paths]
        skills = [m for m in memories if m.frontmatter.category == "skill"]
        # 使用 file_path 集合比对，避免对象身份比较失效
        anaphora_paths = {m.file_path for m in getattr(self, '_last_anaphora', []) if m.file_path}
        anaphora = [m for m in memories if m.file_path in anaphora_paths]

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