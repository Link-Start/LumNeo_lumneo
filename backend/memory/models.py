# backend/memory/models.py
"""
Lumneo 长期记忆系统 - 数据模型
"""
from enum import Enum
import uuid
from datetime import datetime, timezone
from dataclasses import dataclass, field, asdict
from typing import Optional, List, Dict, Any


class MemoryScope(str, Enum):
    LIFE = "life"
    WORK = "work"

class MemoryCategory(str, Enum):
    FACT = "fact"
    PREFERENCE = "preference"
    PERSON = "person"
    DECISION = "decision"
    SKILL = "skill"
    PENDING = "pending"

class MemoryStatus(str, Enum):
    ACTIVE = "active"
    SUPERSEDED = "superseded"
    ARCHIVED = "archived"
    RETRY_PENDING = "retry_pending"

class Sensitivity(str, Enum):
    NORMAL = "normal"
    PRIVATE = "private"
    SECRET = "secret"

class VerificationSource(str, Enum):
    """
    记忆可信来源
    LLM: 模型推断
    SYSTEM: 系统规则验证
    USER: 用户明确确认
    """
    LLM = "llm"
    SYSTEM = "system"
    USER = "user"

class CandidateStatus(str, Enum):
    PENDING = "pending"
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    NEED_CONFIRM = "need_confirm"

@dataclass
class MemoryIdentity:
    id: str = field(
        default_factory=lambda:
        "mem_" + uuid.uuid4().hex[:12]
    )

@dataclass
class MemoryTrust:
    confidence: float = 0.5
    verification_source: VerificationSource = (VerificationSource.LLM)

@dataclass
class MemoryProvenance:
    evidence: str = ""
    source_message: str = ""
    conversation_id: Optional[str] = None
    extracted_by: str = ("memory_extractor")

@dataclass
class MemoryCandidate:
    content: str
    category: str
    confidence: float = 0.5
    evidence: str = ""
    source_message: str = ""
    status: CandidateStatus = (CandidateStatus.PENDING)
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

@dataclass
class MemoryFrontmatter:
    """记忆文件 YAML Frontmatter 数据结构"""
    # 通用字段
    chat_id: Optional[str] = None
    profile_id: Optional[int] = None
    category: str = "fact"
    key: str = ""
    importance: int = 3
    source_turn_index: Optional[int] = None
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now().isoformat())
    access_count: int = 0
    last_accessed: Optional[str] = None

    # 状态与版本链
    status: str = "active"
    supersedes: List[str] = field(default_factory=list)
    superseded_by: Optional[str] = None

    # Skill 专属字段
    domain: Optional[str] = None
    proficiency: Optional[int] = None          # 1-5
    confirmed_by: Optional[str] = None         # user | ai_auto
    verification_count: Optional[int] = None
    verified: Optional[bool] = None
    usage_count: Optional[int] = None
    used_in_projects: Optional[List[str]] = None
    related_skills: Optional[List[str]] = None
    source_project: Optional[str] = None
    source_chat_id: Optional[str] = None

    # State 专属字段（life/core/state.md）
    mood: Optional[str] = None
    energy_level: Optional[str] = None
    focus_topic: Optional[str] = None
    last_user_emotion: Optional[str] = None
    pending_tasks: Optional[List[str]] = None

    # Timeline 专属字段
    date: Optional[str] = None
    sensitivity: Optional[str] = None          # normal | private | secret
    retry_count: int = 0

    # Pending 专属字段
    expires_at: Optional[str] = None
    source_timeline: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典，自动过滤 None 值"""
        d = asdict(self)
        # 过滤 None 值，保持 frontmatter 简洁
        return {k: v for k, v in d.items() if v is not None}

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "MemoryFrontmatter":
        """从字典创建，忽略未知字段"""
        known_fields = {f.name for f in cls.__dataclass_fields__.values()}
        filtered = {k: v for k, v in data.items() if k in known_fields}
        return cls(**filtered)

@dataclass
class MemoryEntry:
    identity: MemoryIdentity = field(default_factory=MemoryIdentity)
    frontmatter: MemoryFrontmatter = field(default_factory=MemoryFrontmatter)   # 新增
    content: str = ""
    category: str = ""
    scope: str = ""
    importance: float = 0.5
    trust: MemoryTrust = field(default_factory=MemoryTrust)
    provenance: MemoryProvenance = field(default_factory=MemoryProvenance)
    status: str = "active"
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    access_count: int = 0
    supersedes: List[str] = field(default_factory=list)
    derived_from: List[str] = field(default_factory=list)
    file_path: Optional[str] = None   # 新增

    @property
    def id(self):
        return self.identity.id

    @property
    def effective_importance(self) -> float:
        """计算时间衰减后的有效重要性，用于排序"""
        import math
        from datetime import datetime, timezone
        try:
            from backend.memory.config import TIME_DECAY_LAMBDA
        except Exception:
            TIME_DECAY_LAMBDA = 0.01

        # 优先使用 frontmatter.importance（int 1-5），否则回退到 self.importance（float）
        if getattr(self, "frontmatter", None) is not None and self.frontmatter.importance is not None:
            importance = float(self.frontmatter.importance)
        else:
            importance = float(self.importance)

        # 时间基准：last_accessed > updated_at > created_at（frontmatter 优先）
        fm = getattr(self, "frontmatter", None)
        base = None
        if fm is not None:
            base = fm.last_accessed or fm.updated_at or fm.created_at
        if not base:
            base = self.created_at

        try:
            last_dt = datetime.fromisoformat(base)
            if last_dt.tzinfo is None:
                last_dt = last_dt.replace(tzinfo=timezone.utc)
        except (ValueError, TypeError):
            last_dt = datetime.now(timezone.utc)

        now = datetime.now(timezone.utc)
        days = (now - last_dt).total_seconds() / 86400
        decay = math.exp(-TIME_DECAY_LAMBDA * days)
        return importance * decay
    
@dataclass
class TimelineEntry:
    """Timeline 日文件条目"""
    date: str
    sensitivity: str = "normal"
    status: str = "active"
    content: str = ""
    file_path: Optional[str] = None


@dataclass
class PendingEntry:
    """Pending 待确认条目"""
    category: str = "pending"
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    source_timeline: Optional[str] = None
    expires_at: Optional[str] = None
    summary: str = ""
    original_quote: str = ""
    file_path: Optional[str] = None