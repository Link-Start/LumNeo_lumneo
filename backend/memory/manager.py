# backend/memory/manager.py
"""
Lumneo 长期记忆系统 - MemoryManager
Phase 4 完整版

修复：
- 4.6: write_timeline 集成 sensitivity 自动预检
"""
import os
import asyncio
from pathlib import Path
from typing import Optional, List, Dict, Any, Tuple
from datetime import datetime
from dataclasses import dataclass

from filelock import FileLock

from backend.memory.config import (
    DEFAULT_MEMORY_DIR,
    FILE_ENCODING,
    MEMORY_STATUS,
    ACCESS_COUNT_BATCH_SIZE,
    ACCESS_COUNT_FLUSH_INTERVAL,
)
from backend.memory.models import MemoryFrontmatter, MemoryEntry
from backend.memory.utils import (
    parse_frontmatter,
    serialize_frontmatter,
    generate_memory_path,
    generate_timeline_path,
    generate_pending_path,
    sanitize_filename,
    read_markdown_file_sync,
    sensitivity_precheck,  # Phase 4: 自动预检
)


@dataclass
class ConflictResult:
    """冲突检测结果"""
    has_conflict: bool
    existing_path: Optional[str] = None
    existing_frontmatter: Optional[MemoryFrontmatter] = None


class MemoryManager:
    """
    记忆文件管理器。

    线程/进程安全：
    - 文件级 filelock（进程间互斥）
    - 文件级 asyncio.Lock（协程级互斥）
    - access_count 内存批量计数（减少文件写竞争）
    """

    def __init__(
        self,
        memory_dir: Optional[Path] = None,
        fts_manager=None,
    ):
        self.memory_dir = memory_dir or DEFAULT_MEMORY_DIR
        self.fts_manager = fts_manager
        # 确保目录存在
        self._ensure_directories()

        # 协程级锁字典：path -> asyncio.Lock
        self._async_locks: Dict[str, asyncio.Lock] = {}
        self._locks_lock = asyncio.Lock()  # 保护 _async_locks 字典本身

        # access_count 批量计数器
        self._pending_access_updates: Dict[str, Tuple[int, str]] = {}
        self._access_flush_task: Optional[asyncio.Task] = None
        self._shutdown = False

    def _ensure_directories(self):
        """确保所有记忆目录存在"""
        from backend.memory.config import MEMORY_DIRS

        for scope_dirs in MEMORY_DIRS.values():
            for subdir in scope_dirs.values():
                (self.memory_dir / subdir).mkdir(parents=True, exist_ok=True)

        # Timeline 目录（按年月动态创建，这里只确保基础结构）
        (self.memory_dir / "life" / "timeline").mkdir(parents=True, exist_ok=True)

    # ==================== 锁管理 ====================

    async def _get_async_lock(self, file_path: str) -> asyncio.Lock:
        """获取指定文件的协程级锁"""
        async with self._locks_lock:
            if file_path not in self._async_locks:
                self._async_locks[file_path] = asyncio.Lock()
            return self._async_locks[file_path]

    def _get_file_lock(self, file_path: str) -> FileLock:
        """获取指定文件的进程级锁（filelock）"""
        lock_path = f"{file_path}.lock"
        return FileLock(lock_path, timeout=30)

    async def _acquire_locks(self, file_path: str):
        """
        同时获取协程锁和文件锁。
        返回 (async_lock, file_lock)，需要配合 async with 使用。
        """
        async_lock = await self._get_async_lock(file_path)
        file_lock = self._get_file_lock(file_path)
        return async_lock, file_lock

    # ==================== FTS5 同步辅助 ====================

    async def _sync_to_fts(self, file_path: Path):
        """写入后同步 FTS5 索引"""
        if self.fts_manager is not None:
            try:
                await self.fts_manager.sync_file(file_path)
            except Exception:
                pass

    # ==================== 基础 CRUD ====================

    async def create_memory(
        self,
        scope: str,
        category: str,
        key: str,
        content: str,
        frontmatter_data: Optional[Dict[str, Any]] = None,
        file_path: Optional[Path] = None,
    ) -> MemoryEntry:
        """
        创建新的记忆文件。
        """
        if file_path is None:
            file_path = generate_memory_path(scope, category, key, self.memory_dir)
        else:
            file_path = Path(file_path)

        # 构建 frontmatter
        fm_data = frontmatter_data or {}
        fm_data.setdefault("category", category)
        fm_data.setdefault("key", key)
        fm_data.setdefault("created_at", datetime.now().isoformat())
        fm_data.setdefault("updated_at", datetime.now().isoformat())
        fm_data.setdefault("status", "active")

        frontmatter = MemoryFrontmatter.from_dict(fm_data)

        # 序列化并写入
        raw_text = serialize_frontmatter(frontmatter, content)

        path_str = str(file_path)
        async_lock, file_lock = await self._acquire_locks(path_str)

        async with async_lock:
            with file_lock:
                file_path.parent.mkdir(parents=True, exist_ok=True)
                with open(file_path, "w", encoding=FILE_ENCODING) as f:
                    f.write(raw_text)

        await self._sync_to_fts(file_path)

        return MemoryEntry(
            frontmatter=frontmatter,
            content=content,
            file_path=path_str,
        )

    async def read_memory(self, file_path: Path) -> Optional[MemoryEntry]:
        """
        读取记忆文件，并自动更新 access_count（内存批量计数）。
        """
        if not file_path.exists():
            return None

        path_str = str(file_path)

        frontmatter, content = read_markdown_file_sync(file_path)
        if frontmatter is None:
            frontmatter = MemoryFrontmatter()

        await self._bump_access_count(path_str)

        return MemoryEntry(
            frontmatter=frontmatter,
            content=content,
            file_path=path_str,
        )

    async def update_memory(
        self,
        file_path: Path,
        content: Optional[str] = None,
        frontmatter_updates: Optional[Dict[str, Any]] = None,
    ) -> Optional[MemoryEntry]:
        """
        更新记忆文件。支持只更新正文、只更新 frontmatter、或两者都更新。
        """
        if not file_path.exists():
            return None

        path_str = str(file_path)
        async_lock, file_lock = await self._acquire_locks(path_str)

        async with async_lock:
            with file_lock:
                with open(file_path, "r", encoding=FILE_ENCODING) as f:
                    raw_text = f.read()

                frontmatter, old_content = parse_frontmatter(raw_text)
                if frontmatter is None:
                    frontmatter = MemoryFrontmatter()

                new_content = content if content is not None else old_content
                if frontmatter_updates:
                    for k, v in frontmatter_updates.items():
                        if hasattr(frontmatter, k):
                            setattr(frontmatter, k, v)

                frontmatter.updated_at = datetime.now().isoformat()

                new_raw = serialize_frontmatter(frontmatter, new_content)
                with open(file_path, "w", encoding=FILE_ENCODING) as f:
                    f.write(new_raw)

        await self._sync_to_fts(file_path)

        return MemoryEntry(
            frontmatter=frontmatter,
            content=new_content,
            file_path=path_str,
        )

    async def delete_memory(self, file_path: Path, hard: bool = False) -> bool:
        """
        删除记忆文件。
        """
        if not file_path.exists():
            return False

        path_str = str(file_path)

        if hard:
            async_lock, file_lock = await self._acquire_locks(path_str)
            async with async_lock:
                with file_lock:
                    os.remove(file_path)
            if self.fts_manager is not None:
                try:
                    await self.fts_manager.remove_file(file_path)
                except Exception:
                    pass
            return True
        else:
            entry = await self.update_memory(
                file_path,
                frontmatter_updates={"status": "archived"}
            )
            return entry is not None

    # ==================== 冲突检测与版本链 ====================

    async def check_conflict(
        self,
        key: str,
        scope: str,
        category: Optional[str] = None,
    ) -> ConflictResult:
        """
        检查同 key 是否已有活跃记忆。
        """
        candidates = await self.search_memories(
            scope=scope,
            category=category,
            key=key,
            status="active",
        )

        for entry in candidates:
            if entry.frontmatter.key == key:
                return ConflictResult(
                    has_conflict=True,
                    existing_path=entry.file_path,
                    existing_frontmatter=entry.frontmatter,
                )

        return ConflictResult(has_conflict=False)

    async def create_with_supersedes(
        self,
        scope: str,
        category: str,
        key: str,
        content: str,
        frontmatter_data: Optional[Dict[str, Any]] = None,
    ) -> Tuple[MemoryEntry, Optional[MemoryEntry]]:
        """
        创建新记忆并处理版本链（若存在冲突）。
        """
        conflict = await self.check_conflict(key, scope, category)

        now = datetime.now().isoformat()

        fm_data = frontmatter_data or {}
        fm_data["key"] = key
        fm_data["category"] = category
        fm_data["status"] = "active"
        fm_data["created_at"] = now
        fm_data["updated_at"] = now

        new_path = generate_memory_path(scope, category, key, self.memory_dir, suffix=now.replace(":", ""))

        old_entry = None

        if conflict.has_conflict and conflict.existing_path:
            old_path = Path(conflict.existing_path)
            old_filename = old_path.name

            fm_data["supersedes"] = [old_filename]

            old_entry = await self.update_memory(
                old_path,
                frontmatter_updates={
                    "status": "superseded",
                    "superseded_by": new_path.name,
                    "updated_at": now,
                }
            )

        new_entry = await self.create_memory(
            scope=scope,
            category=category,
            key=key,
            content=content,
            frontmatter_data=fm_data,
            file_path=new_path,
        )

        return new_entry, old_entry

    async def mark_superseded(self, file_path: Path, superseded_by: str) -> bool:
        """
        将指定记忆标记为 superseded。
        """
        entry = await self.update_memory(
            file_path,
            frontmatter_updates={
                "status": "superseded",
                "superseded_by": superseded_by,
            }
        )
        return entry is not None

    async def update_status(self, file_path: Path, status: str) -> bool:
        """
        更新记忆状态（active/superseded/archived/retry_pending）。
        """
        if status not in MEMORY_STATUS + ["retry_pending"]:
            raise ValueError(f"Invalid status: {status}")

        entry = await self.update_memory(
            file_path,
            frontmatter_updates={"status": status}
        )
        return entry is not None

    # ==================== 检索 ====================

    async def search_memories(
        self,
        scope: Optional[str] = None,
        category: Optional[str] = None,
        key: Optional[str] = None,
        status: Optional[str] = None,
        domain: Optional[str] = None,
        limit: int = 50,
    ) -> List[MemoryEntry]:
        """
        基于文件系统的轻量检索（非 FTS5，用于精确过滤）。
        """
        results = []

        if scope == "life":
            search_roots = [self.memory_dir / "life"]
        elif scope == "work":
            search_roots = [self.memory_dir / "work"]
        else:
            search_roots = [self.memory_dir / "life", self.memory_dir / "work"]

        for root in search_roots:
            if not root.exists():
                continue

            for md_file in root.rglob("*.md"):
                if len(results) >= limit:
                    break

                try:
                    entry = await self.read_memory(md_file)
                    if not entry:
                        continue

                    fm = entry.frontmatter

                    if category and fm.category != category:
                        continue
                    if key and fm.key != key:
                        continue
                    if status and fm.status != status:
                        continue
                    if domain and fm.domain != domain:
                        continue

                    results.append(entry)
                except Exception:
                    continue

        return results

    async def get_by_scope(
        self,
        scope: str,
        category: Optional[str] = None,
        limit: int = 50,
    ) -> List[MemoryEntry]:
        """
        按 scope 获取记忆。
        """
        return await self.search_memories(scope=scope, category=category, limit=limit)

    # ==================== Timeline 操作（4.6 修复）====================

    async def write_timeline(
        self,
        date_str: str,
        content: str,
        sensitivity: str = "normal",
        status: str = "active",
    ) -> Tuple[Path, str]:
        """
        写入 Timeline 日文件。

        Phase 4 修复：
        - 集成 sensitivity 自动预检
        - 追加时保留最严格的 sensitivity（secret > private > normal）
        - 追加时若现有 status 为 archived，保持 archived

        Returns:
            (file_path, final_sensitivity) - 文件路径和最终生效的敏感度
        """
        file_path = generate_timeline_path(date_str, self.memory_dir)
        file_path.parent.mkdir(parents=True, exist_ok=True)

        now = datetime.now().isoformat()

        # 读取现有文件以合并 frontmatter
        existing_fm = None
        existing_content = ""
        if file_path.exists():
            try:
                with open(file_path, "r", encoding=FILE_ENCODING) as f:
                    existing_raw = f.read()
                existing_fm, existing_content = parse_frontmatter(existing_raw)
            except Exception:
                pass

        # Phase 4: sensitivity 自动预检
        auto_detected = sensitivity_precheck(content)
        sensitivity_priority = {"secret": 3, "private": 2, "normal": 1}

        # 取传入值和自动检测的最严格者
        input_pri = sensitivity_priority.get(sensitivity, 0)
        auto_pri = sensitivity_priority.get(auto_detected, 0)
        final_sensitivity = auto_detected if auto_pri > input_pri else sensitivity

        # 与现有文件取最严格
        if existing_fm and existing_fm.sensitivity:
            old_pri = sensitivity_priority.get(existing_fm.sensitivity, 0)
            final_pri = sensitivity_priority.get(final_sensitivity, 0)
            if old_pri > final_pri:
                final_sensitivity = existing_fm.sensitivity

        # status 保持 archived（一旦归档不再自动激活）
        final_status = status
        if existing_fm and existing_fm.status == "archived":
            final_status = "archived"

        # Timeline 的 frontmatter
        fm = MemoryFrontmatter(
            category="timeline",
            key=date_str,
            date=date_str,
            sensitivity=final_sensitivity,
            status=final_status,
            created_at=existing_fm.created_at if existing_fm else now,
            updated_at=now,
        )

        # 内容追加
        if existing_content:
            content = existing_content + "\n\n---\n\n" + content

        raw_text = serialize_frontmatter(fm, content)

        path_str = str(file_path)
        async_lock, file_lock = await self._acquire_locks(path_str)

        async with async_lock:
            with file_lock:
                with open(file_path, "w", encoding=FILE_ENCODING) as f:
                    f.write(raw_text)

        await self._sync_to_fts(file_path)

        return file_path, final_sensitivity

    async def read_timeline(self, date_str: str) -> Optional[MemoryEntry]:
        """读取指定日期的 Timeline"""
        file_path = generate_timeline_path(date_str, self.memory_dir)
        return await self.read_memory(file_path)

    # ==================== Pending 操作 ====================

    async def create_pending(
        self,
        source_timeline: str,
        summary: str,
        original_quote: str = "",
        expires_days: int = 7,
    ) -> Path:
        """
        创建 Pending 待确认文件。
        """
        from datetime import timedelta

        now = datetime.now()
        expires_at = (now + timedelta(days=expires_days)).isoformat()

        file_path = generate_pending_path(now.strftime("%Y%m%d_%H%M%S"), self.memory_dir)
        file_path.parent.mkdir(parents=True, exist_ok=True)

        content = f"""## 待确认摘要
{summary}

## 原始引用
> {original_quote}

## 操作选项
- 输入 `确认记忆`：将该内容提取为 fact 并存入 `life/facts/`
- 输入 `忽略记忆`：删除本 pending 文件
- 输入 `标记为 secret`：删除本 pending 文件，原始 timeline 的 sensitivity 提升为 `secret`
"""

        fm = MemoryFrontmatter(
            category="pending",
            key=f"pending_{now.strftime('%Y%m%d_%H%M%S')}",
            source_timeline=source_timeline,
            expires_at=expires_at,
            created_at=now.isoformat(),
            updated_at=now.isoformat(),
        )

        raw_text = serialize_frontmatter(fm, content)

        path_str = str(file_path)
        async_lock, file_lock = await self._acquire_locks(path_str)

        async with async_lock:
            with file_lock:
                with open(file_path, "w", encoding=FILE_ENCODING) as f:
                    f.write(raw_text)

        await self._sync_to_fts(file_path)

        return file_path

    async def get_pending_list(self) -> List[Tuple[Path, MemoryFrontmatter, str]]:
        """
        获取所有未过期的 pending 文件列表。
        """
        now = datetime.now()
        pending_dir = self.memory_dir / "life" / "pending"
        results = []

        if not pending_dir.exists():
            return results

        for f in pending_dir.glob("*.md"):
            try:
                entry = await self.read_memory(f)
                if not entry:
                    continue

                if entry.frontmatter.expires_at:
                    try:
                        expires = datetime.fromisoformat(entry.frontmatter.expires_at)
                        if expires < now:
                            await self.delete_memory(f, hard=True)
                            continue
                    except ValueError:
                        pass

                results.append((f, entry.frontmatter, entry.content))
            except Exception:
                continue

        return results

    async def confirm_pending(
        self,
        pending_path: Path,
        action: str,
    ) -> bool:
        """
        处理 Pending 文件的用户确认。
        """
        entry = await self.read_memory(pending_path)
        if not entry:
            return False

        if action == "confirm":
            summary_match = entry.content.split("## 待确认摘要")
            if len(summary_match) > 1:
                summary = summary_match[1].split("##")[0].strip()
            else:
                summary = entry.content[:200]

            key_text = summary[:40].replace("\n", " ")
            if "。" in key_text:
                key_text = key_text.split("。")[0]
            if len(key_text) > 20:
                key_text = key_text[:20]
            fact_key = key_text.strip() or (entry.frontmatter.key or "pending_fact")

            await self.create_memory(
                scope="life",
                category="fact",
                key=fact_key,
                content=summary,
                frontmatter_data={
                    "source_timeline": entry.frontmatter.source_timeline,
                    "sensitivity": "normal",
                }
            )
            await self.delete_memory(pending_path, hard=True)
            return True

        elif action == "ignore":
            await self.delete_memory(pending_path, hard=True)
            return True

        elif action == "escalate":
            if entry.frontmatter.source_timeline:
                timeline_path = self.memory_dir / entry.frontmatter.source_timeline
                if timeline_path.exists():
                    await self.update_memory(
                        timeline_path,
                        frontmatter_updates={"sensitivity": "secret"}
                    )
            await self.delete_memory(pending_path, hard=True)
            return True

        return False

    # ==================== access_count 批量写 ====================

    async def _bump_access_count(self, path_str: str):
        """
        增加 access_count（内存批量计数）。
        """
        now = datetime.now().isoformat()

        if path_str in self._pending_access_updates:
            count, _ = self._pending_access_updates[path_str]
            self._pending_access_updates[path_str] = (count + 1, now)
        else:
            self._pending_access_updates[path_str] = (1, now)

        total_pending = sum(c for c, _ in self._pending_access_updates.values())
        if total_pending >= ACCESS_COUNT_BATCH_SIZE:
            await self._flush_access_counts()

    async def _flush_access_counts(self):
        """
        将内存中的 access_count 更新批量刷盘。
        """
        if not self._pending_access_updates:
            return

        updates = dict(self._pending_access_updates)
        self._pending_access_updates.clear()

        for path_str, (count, last_access) in updates.items():
            try:
                file_path = Path(path_str)
                if not file_path.exists():
                    continue

                async_lock, file_lock = await self._acquire_locks(path_str)
                async with async_lock:
                    with file_lock:
                        with open(file_path, "r", encoding=FILE_ENCODING) as f:
                            raw = f.read()

                        fm, content = parse_frontmatter(raw)
                        if fm is None:
                            continue

                        fm.access_count = (fm.access_count or 0) + count
                        fm.last_accessed = last_access

                        new_raw = serialize_frontmatter(fm, content)
                        with open(file_path, "w", encoding=FILE_ENCODING) as f:
                            f.write(new_raw)
            except Exception:
                continue

    async def start_access_flush_loop(self):
        """
        启动定时刷盘任务（每 ACCESS_COUNT_FLUSH_INTERVAL 秒）。
        """
        while not self._shutdown:
            await asyncio.sleep(ACCESS_COUNT_FLUSH_INTERVAL)
            await self._flush_access_counts()

    async def shutdown(self):
        """
        优雅关闭，确保所有 pending access_count 刷盘。
        """
        self._shutdown = True
        if self._access_flush_task:
            self._access_flush_task.cancel()
            try:
                await self._access_flush_task
            except asyncio.CancelledError:
                pass
        await self._flush_access_counts()