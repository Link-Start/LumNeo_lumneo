# backend/memory/fts_index.py
"""
Lumneo 长期记忆系统 - FTS5 全文索引管理
Phase 0 基础设施

设计原则：
- MD 文件为唯一真相源，FTS5 为可重建缓存
- 启动时扫描时间戳差异自动修复
- 写入时先删后插保证一致性
"""
import os
import asyncio
import aiosqlite
from pathlib import Path
from typing import List, Optional, Dict, Any, Tuple
from datetime import datetime

from backend.memory.config import (
    FTS5_TABLE_NAME,
    FTS5_META_TABLE_NAME, 
    FTS5_TOKENIZER,
    FILE_ENCODING,
    DEFAULT_MEMORY_DIR,
)
from backend.memory.utils import parse_frontmatter


class FTSIndexManager:
    """
    FTS5 全文索引管理器。

    负责：
    1. Schema 初始化（虚拟表 + 辅助表）
    2. 增量同步（MD 文件写入后同步到 FTS5）
    3. 全文检索
    4. 启动一致性校验与重建
    """

    def __init__(self, db_connection: aiosqlite.Connection):
        self.db = db_connection

    async def init_schema(self):
        """
        初始化 FTS5 虚拟表和辅助表。
        幂等操作，可安全重复调用。
        """
        # 主 FTS5 虚拟表
        # content='' 表示不存储内容，仅索引
        await self.db.execute(f"""
            CREATE VIRTUAL TABLE IF NOT EXISTS {FTS5_TABLE_NAME} USING fts5(
                path UNINDEXED,
                content,
                key,
                category,
                domain,
                project_tag,
                indexed_at UNINDEXED,
                content='',
                tokenize='{FTS5_TOKENIZER}'
            )
        """)

        # 辅助表：记录每个 path 的最新 indexed_at 和 md_updated_at
        await self.db.execute(f"""
            CREATE TABLE IF NOT EXISTS {FTS5_META_TABLE_NAME} (
                path TEXT PRIMARY KEY,
                indexed_at TEXT NOT NULL,
                md_updated_at TEXT NOT NULL
            )
        """)

        await self.db.commit()

    async def sync_file(
        self,
        file_path: Path,
        project_tag: Optional[str] = None
    ):
        """
        同步单个 MD 文件到 FTS5 索引。

        策略：
        - 新文件：直接 INSERT
        - 更新文件：先 DELETE 再 INSERT
        - 同时更新 fts_index_meta
        """
        if not file_path.exists():
            # 文件不存在则删除索引
            await self._remove_from_index(str(file_path))
            return

        # 读取文件内容
        try:
            with open(file_path, "r", encoding=FILE_ENCODING) as f:
                raw_text = f.read()
        except Exception:
            return

        frontmatter, content = parse_frontmatter(raw_text)

        path_str = str(file_path)
        now = datetime.now().isoformat()
        md_updated_at = now

        key = ""
        category = ""
        domain = ""

        if frontmatter:
            key = frontmatter.key or ""
            category = frontmatter.category or ""
            domain = frontmatter.domain or ""
            if frontmatter.updated_at:
                md_updated_at = frontmatter.updated_at

        # 从文件名推断 category（如果 frontmatter 没有）
        if not category and file_path.name:
            parts = file_path.name.split("_", 1)
            if parts:
                category = parts[0]

        # 从文件路径推断 project_tag（如果未提供）
        if not project_tag:
            project_tag = self._infer_project_tag(file_path)

        # 检查是否已存在
        cursor = await self.db.execute(
            f"SELECT path FROM {FTS5_META_TABLE_NAME} WHERE path = ?",
            (path_str,)
        )
        exists = await cursor.fetchone()

        if exists:
            # 更新：先删后插
            await self.db.execute(
                f"DELETE FROM {FTS5_TABLE_NAME} WHERE path = ?",
                (path_str,)
            )

        # 插入新记录
        await self.db.execute(f"""
            INSERT INTO {FTS5_TABLE_NAME}(path, content, key, category, domain, project_tag, indexed_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (path_str, content, key, category, domain, project_tag or "global", now))

        # 更新/插入 meta
        if exists:
            await self.db.execute(f"""
                UPDATE {FTS5_META_TABLE_NAME} 
                SET indexed_at = ?, md_updated_at = ?
                WHERE path = ?
            """, (now, md_updated_at, path_str))
        else:
            await self.db.execute(f"""
                INSERT INTO {FTS5_META_TABLE_NAME}(path, indexed_at, md_updated_at)
                VALUES (?, ?, ?)
            """, (path_str, now, md_updated_at))

        await self.db.commit()

    async def remove_file(self, file_path: Path):
        """从索引中移除文件"""
        await self._remove_from_index(str(file_path))

    async def _remove_from_index(self, path_str: str):
        """内部：从 FTS5 和 meta 表中删除指定路径"""
        await self.db.execute(
            f"DELETE FROM {FTS5_TABLE_NAME} WHERE path = ?",
            (path_str,)
        )
        await self.db.execute(
            f"DELETE FROM {FTS5_META_TABLE_NAME} WHERE path = ?",
            (path_str,)
        )
        await self.db.commit()

    async def search(
        self,
        query: str,
        scope: Optional[str] = None,
        category: Optional[str] = None,
        domain: Optional[str] = None,
        project_tag: Optional[str] = None,
        limit: int = 20
    ) -> List[Dict[str, Any]]:
        """
        FTS5 全文检索。

        Args:
            query: 搜索关键词（FTS5 MATCH 语法）
            scope: 过滤 scope（life/work），通过 path 匹配
            category: 过滤类别
            domain: 过滤领域
            project_tag: 过滤项目标签
            limit: 返回数量上限

        Returns:
            结果列表，每项包含 path, content, key, category, domain, project_tag
        """
        # 构建 WHERE 子句
        conditions = [f"{FTS5_TABLE_NAME} MATCH ?"]
        params: List[Any] = [query]

        if category:
            conditions.append("category = ?")
            params.append(category)

        if domain:
            conditions.append("domain = ?")
            params.append(domain)

        if project_tag:
            conditions.append("project_tag = ?")
            params.append(project_tag)

        where_clause = " AND ".join(conditions)

        sql = f"""
            SELECT path, content, key, category, domain, project_tag
            FROM {FTS5_TABLE_NAME}
            WHERE {where_clause}
            ORDER BY rank
            LIMIT ?
        """
        params.append(limit)

        cursor = await self.db.execute(sql, params)
        rows = await cursor.fetchall()

        results = []
        for row in rows:
            # scope 过滤（通过后处理）
            path = row[0]
            if scope:
                if scope == "life" and "/life/" not in path:
                    continue
                if scope == "work" and "/work/" not in path:
                    continue

            results.append({
                "path": path,
                "content": row[1],
                "key": row[2],
                "category": row[3],
                "domain": row[4],
                "project_tag": row[5],
            })

        return results

    async def startup_consistency_check(
        self,
        memory_dir: Optional[Path] = None
    ) -> Tuple[int, int]:
        """
        启动一致性校验：扫描所有 MD 文件，与 FTS5 索引对比。

        Returns:
            (rebuilt_count, total_count) - 重建的文件数和扫描的总数
        """
        root = memory_dir or DEFAULT_MEMORY_DIR
        if not root.exists():
            return 0, 0

        rebuilt = 0
        total = 0

        # 获取所有已索引的路径
        cursor = await self.db.execute(
            f"SELECT path, md_updated_at FROM {FTS5_META_TABLE_NAME}"
        )
        indexed_rows = await cursor.fetchall()
        indexed_map = {row[0]: row[1] for row in indexed_rows}

        # 扫描文件系统
        md_files = list(root.rglob("*.md"))

        for file_path in md_files:
            total += 1
            path_str = str(file_path)

            # 读取文件 updated_at
            try:
                with open(file_path, "r", encoding=FILE_ENCODING) as f:
                    raw = f.read()
                frontmatter, _ = parse_frontmatter(raw)
                md_updated = frontmatter.updated_at if frontmatter else None
                if not md_updated:
                    stat = os.stat(file_path)
                    md_updated = datetime.fromtimestamp(stat.st_mtime).isoformat()
            except Exception:
                continue

            indexed_updated = indexed_map.get(path_str)

            if not indexed_updated or md_updated > indexed_updated:
                # 需要重建
                await self.sync_file(file_path)
                rebuilt += 1

        # 清理已不存在文件的索引
        current_paths = {str(p) for p in md_files}
        for indexed_path in list(indexed_map.keys()):
            if indexed_path not in current_paths:
                await self._remove_from_index(indexed_path)

        return rebuilt, total

    async def rebuild_index(
        self,
        memory_dir: Optional[Path] = None
    ) -> int:
        """
        全量重建 FTS5 索引。

        Returns:
            重建的文件数量
        """
        # 清空现有索引
        await self.db.execute(f"DELETE FROM {FTS5_TABLE_NAME}")
        await self.db.execute(f"DELETE FROM {FTS5_META_TABLE_NAME}")
        await self.db.commit()

        root = memory_dir or DEFAULT_MEMORY_DIR
        if not root.exists():
            return 0

        count = 0
        md_files = list(root.rglob("*.md"))

        for file_path in md_files:
            await self.sync_file(file_path)
            count += 1

        return count

    @staticmethod
    def _infer_project_tag(file_path: Path) -> str:
        """
        从文件路径推断 project_tag。
        例如：work/projects/支付网关重构/... -> "支付网关重构"
        """
        parts = file_path.parts
        if "projects" in parts:
            idx = parts.index("projects")
            if idx + 1 < len(parts):
                return parts[idx + 1]

        # 从 frontmatter 的 source_project 推断（在 sync_file 中已处理）
        # 默认返回 global
        return "global"

    async def get_stats(self) -> Dict[str, Any]:
        """获取索引统计信息"""
        cursor = await self.db.execute(f"SELECT COUNT(*) FROM {FTS5_TABLE_NAME}")
        total = (await cursor.fetchone())[0]

        cursor = await self.db.execute(f"""
            SELECT category, COUNT(*) FROM {FTS5_TABLE_NAME}
            GROUP BY category
        """)
        category_counts = {row[0]: row[1] for row in await cursor.fetchall()}

        cursor = await self.db.execute(f"""
            SELECT domain, COUNT(*) FROM {FTS5_TABLE_NAME}
            WHERE domain IS NOT NULL AND domain != ''
            GROUP BY domain
        """)
        domain_counts = {row[0]: row[1] for row in await cursor.fetchall()}

        return {
            "total_indexed": total,
            "by_category": category_counts,
            "by_domain": domain_counts,
        }

    async def close(self):
        """关闭内部数据库连接，释放资源"""
        if hasattr(self, 'db') and self.db is not None:
            await self.db.close()
            await asyncio.sleep(0.05)
            self.db = None
