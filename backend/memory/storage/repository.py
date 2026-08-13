# backend/memory/storage/repository.py

import sqlite3
import json
from abc import ABC, abstractmethod
from datetime import datetime
from pathlib import Path
from typing import Literal, Optional, List, Dict, Any

from ..model import MemoryObject, Evidence, Source, MemoryNeed, MemoryStatus
from ..common.exceptions import PersistenceError, ValidationError, ConcurrentModificationError, NotFoundError
from ..common.time import utc_now
from ..common.id_gen import generate_evidence_id
from .serializer import write_memory_object, read_memory_object, memory_to_path


# ========== 辅助结构（ADR-006 §3） ==========
class ConsistencyReport:
    def __init__(
        self,
        status: Literal["healthy", "repaired", "critical"],
        missing_in_index: Optional[List[str]] = None,
        orphan_in_index: Optional[List[str]] = None,
        checksum_mismatch: Optional[List[str]] = None,
        repaired_count: int = 0,
        critical_details: Optional[str] = None,
    ):
        self.status = status
        self.missing_in_index = missing_in_index or []
        self.orphan_in_index = orphan_in_index or []
        self.checksum_mismatch = checksum_mismatch or []
        self.repaired_count = repaired_count
        self.critical_details = critical_details


class AuditLogEntry:
    def __init__(
        self,
        timestamp: datetime,
        action: Literal[
            "capture", "evaluation", "state_transition",
            "forget", "correct", "supersede", "conflict",
            "auto_action", "index_rebuild", "scope_violation"
        ],
        memory_id: Optional[str],
        reason: str,
        source: dict,
        payload: Optional[dict] = None,
    ):
        self.timestamp = timestamp
        self.action = action
        self.memory_id = memory_id
        self.reason = reason
        self.source = source
        self.payload = payload or {}


# ========== 抽象接口（ADR-006） ==========
class MemoryRepository(ABC):
    @abstractmethod
    def create(self, memory: MemoryObject) -> MemoryObject:
        """原子写入 Markdown，插入 SQLite + FTS5。"""
        ...

    @abstractmethod
    def update_with_version(
        self,
        memory: MemoryObject,
        expected_updated_at: Optional[datetime] = None
    ) -> MemoryObject:
        """更新记忆，乐观锁预留。"""
        ...

    @abstractmethod
    def append_audit_log(self, entry: AuditLogEntry) -> None:
        """追加审计日志。"""
        ...

    @abstractmethod
    def get_by_id(self, memory_id: str) -> Optional[MemoryObject]:
        """根据 ID 读取记忆。"""
        ...

    @abstractmethod
    def query_active(
        self,
        need: MemoryNeed,
        scope_filter: Optional[dict] = None
    ) -> List[MemoryObject]:
        """检索 active 状态记忆。"""
        ...

    @abstractmethod
    def query_by_status(
        self,
        status: MemoryStatus,
        scope_filter: Optional[dict] = None,
        limit: int = 100
    ) -> List[MemoryObject]:
        """按状态批量查询。"""
        ...

    @abstractmethod
    def rebuild_index(
        self,
        force_ids: Optional[List[str]] = None
    ) -> ConsistencyReport:
        """重建 FTS5 / SQLite 索引。"""
        ...

    @abstractmethod
    def check_consistency(self) -> ConsistencyReport:
        """执行一致性校验。"""
        ...

    @abstractmethod
    def close(self) -> None:
        """安全关闭连接。"""
        ...


# ========== 具体实现：SQLiteMemoryRepository ==========
class SQLiteMemoryRepository(MemoryRepository):
    def __init__(self, db_path: Path, data_root: Path):
        self.db_path = db_path
        self.data_root = data_root
        self.conn = None
        self._init_db()

    def _init_db(self):
        """初始化数据库连接，执行迁移。"""
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(str(self.db_path))
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA foreign_keys = ON")
        self.conn.execute("PRAGMA journal_mode = WAL")
        self._check_and_migrate()
        # 启动时自动执行一致性检查并修复
        report = self.check_consistency()
        if report.status != "healthy":
            # 自动重建全量索引
            self.rebuild_index()
            # 记录日志（简化为打印）
            print(f"[MemoryOS] 索引不一致，已自动重建。缺失: {len(report.missing_in_index)}, 孤儿: {len(report.orphan_in_index)}")

    def _check_and_migrate(self):
        """检查 schema 版本，执行 DDL。"""
        cursor = self.conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='_schema_meta'"
        )
        if cursor.fetchone() is None:
            self._execute_ddl()
        else:
            row = self.conn.execute(
                "SELECT value FROM _schema_meta WHERE key='storage_schema_version'"
            ).fetchone()
            if row is None or row[0] != "1.0":
                raise PersistenceError(f"不支持的 storage schema 版本: {row[0] if row else 'unknown'}, 仅支持 1.0")

    def _execute_ddl(self):
        """执行完整 DDL 脚本。"""
        migration_file = Path(__file__).parent.parent.parent.parent / "migrations" / "migrate_v0.0_to_v1.0.sql"
        if not migration_file.exists():
            raise PersistenceError(f"迁移文件不存在: {migration_file}")
        with open(migration_file, 'r', encoding='utf-8') as f:
            script = f.read()
        try:
            self.conn.executescript(script)
        except sqlite3.Error as e:
            raise PersistenceError(f"DDL 执行失败: {e}")

    def _update_memory(self, memory: MemoryObject):
        """更新 memories 和 evidence 表（不更新 Markdown，由调用方负责）"""
        source_json = json.dumps(memory.source.model_dump(mode='json'), ensure_ascii=False)
        privacy_json = json.dumps(memory.privacy.model_dump(mode='json') if memory.privacy else None, ensure_ascii=False)
        metadata_json = json.dumps(memory.metadata, ensure_ascii=False)
        tags_json = json.dumps(memory.tags, ensure_ascii=False)
        condition_json = json.dumps(memory.condition, ensure_ascii=False) if memory.condition else None

        self.conn.execute("""
            UPDATE memories SET
                schema_version = ?, layer = ?, type = ?, subject = ?, predicate = ?, object = ?,
                condition_json = ?, content = ?, confidence = ?, importance = ?, status = ?,
                origin = ?, supersedes = ?, superseded_by = ?, last_accessed = ?, access_count = ?,
                tags_json = ?, privacy_json = ?, updated_at = ?, metadata_json = ?, source_json = ?,
                evidence_count = ?
            WHERE id = ?
        """, (
            memory.schema_version, memory.layer, memory.type,
            memory.subject, memory.predicate, memory.object,
            condition_json, memory.content, memory.confidence, memory.importance,
            memory.status, memory.origin, memory.supersedes, memory.superseded_by,
            memory.last_accessed.isoformat() if memory.last_accessed else None,
            memory.access_count,
            tags_json, privacy_json,
            memory.updated_at.isoformat(),
            metadata_json, source_json,
            len(memory.evidence),
            memory.id
        ))

        # 证据：先删后插
        self.conn.execute("DELETE FROM evidence WHERE memory_id = ?", (memory.id,))
        for ev in memory.evidence:
            ev_source_json = json.dumps(ev.source.model_dump(mode='json'), ensure_ascii=False)
            ev_id = generate_evidence_id()
            self.conn.execute("""
                INSERT INTO evidence (
                    id, memory_id, type, weight, source_json, observation,
                    origin_actor, created_at, provenance_key
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                ev_id, memory.id,
                ev.type, ev.weight,
                ev_source_json, ev.observation,
                ev.origin_actor,
                ev.created_at.isoformat(),
                ev.provenance_key
            ))

        self.conn.commit()

    # ---------- 写操作 ----------
    def create(self, memory: MemoryObject) -> MemoryObject:
        try:
            write_memory_object(memory, self.data_root)
        except Exception as e:
            raise PersistenceError(f"Markdown 写入失败: {e}") from e

        try:
            self._insert_memory(memory)
            return memory
        except sqlite3.Error as e:
            raise PersistenceError(f"SQLite 插入失败: {e}") from e

    def update_with_version(
        self,
        memory: MemoryObject,
        expected_updated_at: Optional[datetime] = None
    ) -> MemoryObject:
        # ---------- 乐观锁检查（预留） ----------
        if expected_updated_at is not None:
            cursor = self.conn.execute(
                "SELECT updated_at FROM memories WHERE id = ?",
                (memory.id,)
            )
            row = cursor.fetchone()
            if row is None:
                raise NotFoundError(f"记忆 {memory.id} 不存在")
            current_updated = datetime.fromisoformat(row[0])
            if current_updated != expected_updated_at:
                raise ConcurrentModificationError(
                    f"乐观锁冲突：期望 {expected_updated_at.isoformat()}，实际 {current_updated.isoformat()}",
                    context={"id": memory.id, "expected": expected_updated_at.isoformat(), "actual": current_updated.isoformat()}
                )

        # ---------- 更新时间戳（强制） ----------
        memory.updated_at = utc_now()   # 新纳秒级时间

        # ---------- 原子写入 Markdown ----------
        try:
            write_memory_object(memory, self.data_root)
        except Exception as e:
            raise PersistenceError(f"Markdown 更新失败: {e}") from e

        # ---------- 更新 SQLite 和 FTS5 ----------
        try:
            self._update_memory(memory)
        except sqlite3.Error as e:
            # 如果 SQL 失败，Markdown 已写入，可能会不一致；但 Phase 1A 简单处理为异常
            raise PersistenceError(f"SQLite 更新失败: {e}") from e

        return memory

    def _insert_memory(self, memory: MemoryObject):
        # 转换 source.timestamp
        source_dict = memory.source.model_dump(mode='json')
        if source_dict.get('timestamp') and isinstance(source_dict['timestamp'], datetime):
            source_dict['timestamp'] = source_dict['timestamp'].isoformat()
        source_json = json.dumps(source_dict, ensure_ascii=False)

        privacy_json = json.dumps(memory.privacy.model_dump(mode='json') if memory.privacy else None, ensure_ascii=False)
        metadata_json = json.dumps(memory.metadata, ensure_ascii=False)
        tags_json = json.dumps(memory.tags, ensure_ascii=False)
        condition_json = json.dumps(memory.condition, ensure_ascii=False) if memory.condition else None

        self.conn.execute("""
            INSERT INTO memories (
                id, schema_version, layer, type, subject, predicate, object,
                condition_json, content, confidence, importance, status,
                origin, supersedes, superseded_by, last_accessed, access_count,
                tags_json, privacy_json, created_at, updated_at, metadata_json,
                source_json, evidence_count
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            memory.id, memory.schema_version, memory.layer, memory.type,
            memory.subject, memory.predicate, memory.object,
            condition_json, memory.content, memory.confidence, memory.importance,
            memory.status, memory.origin, memory.supersedes, memory.superseded_by,
            memory.last_accessed.isoformat() if memory.last_accessed else None,
            memory.access_count,
            tags_json, privacy_json,
            memory.created_at.isoformat(), memory.updated_at.isoformat(),
            metadata_json, source_json, len(memory.evidence)
        ))

        for ev in memory.evidence:
            ev_source_dict = ev.source.model_dump(mode='json')
            if ev_source_dict.get('timestamp') and isinstance(ev_source_dict['timestamp'], datetime):
                ev_source_dict['timestamp'] = ev_source_dict['timestamp'].isoformat()
            ev_source_json = json.dumps(ev_source_dict, ensure_ascii=False)

            ev_id = generate_evidence_id()
            self.conn.execute("""
                INSERT INTO evidence (
                    id, memory_id, type, weight, source_json, observation,
                    origin_actor, created_at, provenance_key
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                ev_id, memory.id,
                ev.type, ev.weight,
                ev_source_json, ev.observation,
                ev.origin_actor,
                ev.created_at.isoformat(),
                ev.provenance_key
            ))

        self.conn.commit()

    # ---------- 读操作（占位） ----------
    def get_by_id(self, memory_id: str) -> Optional[MemoryObject]:
        raise NotImplementedError("get_by_id 将在 T5.4 后实现")

    def query_active(self, need: MemoryNeed, scope_filter: Optional[dict] = None) -> List[MemoryObject]:
        raise NotImplementedError("query_active 将在 T6 实现")

    def query_by_status(self, status: MemoryStatus, scope_filter: Optional[dict] = None, limit: int = 100) -> List[MemoryObject]:
        raise NotImplementedError("query_by_status 将在 T6 实现")

    # ---------- 索引与一致性 ----------
    def rebuild_index(self, force_ids: Optional[List[str]] = None) -> ConsistencyReport:
        """重建 FTS5 索引。若 force_ids 为空则全量重建，否则只重建指定 ID。"""
        # 如果 force_ids 为 None，全量重建
        if force_ids is None:
            # 清空 memories 表（级联删除 evidence，FTS5 触发器自动处理）
            self.conn.execute("DELETE FROM memories")
            # 或者使用 TRUNCATE（SQLite 不支持，用 DELETE 即可）
            self.conn.commit()

            # 遍历所有 .md 重新插入
            for layer_dir in self.data_root.iterdir():
                if not layer_dir.is_dir() or layer_dir.name in ("governance", "index"):
                    continue
                for md_file in layer_dir.glob("*.md"):
                    try:
                        memory = read_memory_object(md_file)
                        self._insert_memory(memory)
                    except Exception as e:
                        # 记录错误但继续
                        # Phase 1A 简单处理：抛出异常或记录
                        raise PersistenceError(f"重建索引失败: {md_file} - {e}")
        else:
            # 仅重建指定 ID
            for memory_id in force_ids:
                # 查找对应的 .md 文件（需要知道 layer，可以从内容读取，或扫描所有层）
                found = False
                for layer_dir in self.data_root.iterdir():
                    if not layer_dir.is_dir() or layer_dir.name in ("governance", "index"):
                        continue
                    md_path = layer_dir / f"{memory_id}.md"
                    if md_path.exists():
                        memory = read_memory_object(md_path)
                        # 先删除旧记录（如果存在）
                        self.conn.execute("DELETE FROM memories WHERE id = ?", (memory_id,))
                        self.conn.commit()
                        self._insert_memory(memory)
                        found = True
                        break
                if not found:
                    # 如果找不到文件，则从索引中删除
                    self.conn.execute("DELETE FROM memories WHERE id = ?", (memory_id,))
                    self.conn.commit()

        # 返回一致性报告（仅作参考）
        return self.check_consistency()
    
    def check_consistency(self) -> ConsistencyReport:
        """遍历 Markdown SoT，与 SQLite 比对，返回一致性报告。"""
        missing_in_index = []
        orphan_in_index = []
        checksum_mismatch = []  # Phase 1A 暂不比较内容

        # 1. 从 SQLite 读取所有 memory id
        existing_ids = set()
        cursor = self.conn.execute("SELECT id FROM memories")
        for row in cursor.fetchall():
            existing_ids.add(row['id'])

        # 2. 遍历所有 layer 目录下的 .md 文件
        md_ids = set()
        for layer_dir in self.data_root.iterdir():
            if not layer_dir.is_dir() or layer_dir.name in ("governance", "index"):
                continue
            for md_file in layer_dir.glob("*.md"):
                # 提取 id（文件名去掉 .md）
                memory_id = md_file.stem
                md_ids.add(memory_id)

                # 检查是否在 SQLite 中
                if memory_id not in existing_ids:
                    missing_in_index.append(memory_id)

        # 3. 检查 SQLite 中是否存在孤儿
        for idx_id in existing_ids:
            if idx_id not in md_ids:
                orphan_in_index.append(idx_id)

        # 4. 确定状态
        if missing_in_index or orphan_in_index:
            # 如果缺失或孤儿，尝试修复（自动修复在 rebuild_index 中）
            status = "critical"
            critical_details = f"缺失 {len(missing_in_index)} 个，孤儿 {len(orphan_in_index)} 个"
        else:
            status = "healthy"
            critical_details = None

        return ConsistencyReport(
            status=status,
            missing_in_index=missing_in_index,
            orphan_in_index=orphan_in_index,
            checksum_mismatch=checksum_mismatch,
            repaired_count=0,
            critical_details=critical_details,
        )

    # ---------- 审计 ----------
    def append_audit_log(self, entry: AuditLogEntry) -> None:
        raise NotImplementedError("审计将在 T4.5 实现")

    # ---------- 生命周期 ----------
    def close(self) -> None:
        if self.conn:
            self.conn.close()
            self.conn = None