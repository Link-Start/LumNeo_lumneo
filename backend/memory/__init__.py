# backend/memory/__init__.py
"""
Lumneo 长期记忆系统

使用方式：
    from backend.memory import MemoryManager, FTSIndexManager, MemoryRetriever
    from backend.memory import MemoryExtractor, StateManager, Consolidator
"""
from backend.memory.manager import MemoryManager
from backend.memory.fts_index import FTSIndexManager
from backend.memory.retriever import MemoryRetriever
from backend.memory.extractor import MemoryExtractor, MemoryExtractorTrigger
from backend.memory.state_manager import StateManager
from backend.memory.consolidator import Consolidator
from backend.memory.models import (
    MemoryEntry,
    MemoryFrontmatter,
    MemoryScope,
    MemoryCategory,
    MemoryStatus,
    Sensitivity,
    TimelineEntry,
    PendingEntry,
)
from backend.memory.utils import (
    parse_frontmatter,
    serialize_frontmatter,
    generate_memory_path,
    generate_timeline_path,
    generate_pending_path,
    generate_monthly_summary_path,
    sensitivity_precheck,
    normalize_domain,
)

__all__ = [
    "MemoryManager",
    "FTSIndexManager",
    "MemoryRetriever",
    "MemoryExtractor",
    "MemoryExtractorTrigger",
    "StateManager",
    "Consolidator",
    "MemoryEntry",
    "MemoryFrontmatter",
    "MemoryScope",
    "MemoryCategory",
    "MemoryStatus",
    "Sensitivity",
    "TimelineEntry",
    "PendingEntry",
    "parse_frontmatter",
    "serialize_frontmatter",
    "generate_memory_path",
    "generate_timeline_path",
    "generate_pending_path",
    "generate_monthly_summary_path",
    "sensitivity_precheck",
    "normalize_domain",
]