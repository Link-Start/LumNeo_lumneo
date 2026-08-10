# backend/memory/models.py
"""
Lumneo 长期记忆系统 - 数据模型
"""
from dataclasses import dataclass, field, asdict
from typing import Optional, List, Dict, Any
from datetime import datetime
from enum import Enum


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


class Sensitivity(str, Enum):
    NORMAL = "normal"
    PRIVATE = "private"
    SECRET = "secret"


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
    """完整记忆条目（Frontmatter + 正文）"""
    frontmatter: MemoryFrontmatter
    content: str = ""           # Markdown 正文（不含 frontmatter）
    file_path: Optional[str] = None  # 文件绝对路径

    @property
    def scope(self) -> str:
        """根据文件路径推断 scope"""
        if self.file_path:
            if "/life/" in self.file_path:
                return "life"
            elif "/work/" in self.file_path:
                return "work"
        return "unknown"

    @property
    def effective_importance(self) -> float:
        """计算经时间衰减后的有效重要性"""
        import math
        from backend.memory.config import TIME_DECAY_LAMBDA

        base = self.frontmatter.importance
        # last_accessed 为空时 fallback 到 created_at，避免新记忆永不衰减
        time_ref = self.frontmatter.last_accessed or self.frontmatter.created_at
        if not time_ref:
            return float(base)

        try:
            ref_time = datetime.fromisoformat(time_ref)
            days = (datetime.now() - ref_time).total_seconds() / 86400
            return base * math.exp(-TIME_DECAY_LAMBDA * days)
        except (ValueError, TypeError):
            return float(base)


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