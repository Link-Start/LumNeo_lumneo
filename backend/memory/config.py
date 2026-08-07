# backend/memory/config.py
"""
Lumneo 长期记忆系统 - 配置常量
Phase 0 基础设施
"""
from pathlib import Path
from typing import Set, List

# 从项目根目录的 config_loader 导入（config_loader.py 与 main.py 同级）
from config_loader import config as app_config

# ==================== 动态路径（对接 config_loader）====================
DEFAULT_MEMORY_DIR: Path = app_config.memory_dir

# ==================== 领域白名单 ====================
DOMAIN_WHITELIST: Set[str] = {
    "backend",
    "frontend", 
    "devops",
    "ai",
    "product",
    "design",
    "infra",
    "security",
    "general",  # fallback
}

# ==================== 敏感度级别 ====================
SENSITIVITY_LEVELS = ["normal", "private", "secret"]

# ==================== 记忆类别 ====================
MEMORY_CATEGORIES = ["fact", "preference", "person", "decision", "skill", "pending"]

# ==================== 记忆状态 ====================
MEMORY_STATUS = ["active", "superseded", "archived"]

# ==================== 触发阈值 ====================
TRIGGER_THRESHOLD_ROUNDS: int = 20      # 累计轮次阈值
TRIGGER_THRESHOLD_HOURS: float = 2.0    # 对话间隔阈值（小时）

# ==================== Token 预算 ====================
TOKEN_BUDGET_RETRIEVAL: int = 1500      # 常规检索注入预算
TOKEN_BUDGET_RETRIEVAL_MAX: int = 2000  # 检索注入上限
TOKEN_BUDGET_SKILL: int = 800           # Skill 动态注入预算
TOKEN_BUDGET_ANAPHORA: int = 400        # 强指代回溯独立预算

# ==================== Consolidator 熔断 ====================
CONSOLIDATOR_DAILY_LIMIT: int = 10      # 每日最多触发次数
CONSOLIDATOR_QUEUE_LIMIT: int = 50      # 队列积压上限
CONSOLIDATOR_MAX_INPUT_TOKENS: int = 8000  # 单次输入 Token 上限

# ==================== access_count 批量写优化 ====================
ACCESS_COUNT_BATCH_SIZE: int = 50       # 累积次数阈值
ACCESS_COUNT_FLUSH_INTERVAL: int = 300  # 刷盘间隔（秒）

# ==================== 时间衰减 ====================
TIME_DECAY_LAMBDA: float = 0.01         # 衰减系数
TIME_DECAY_CUTOFF: float = 1.0          # effective_importance 低于此值不参与常规检索

# ==================== Pending 过期 ====================
PENDING_EXPIRE_DAYS: int = 7            # pending 文件默认过期天数

# ==================== 目录结构（相对 memory 根目录）====================
MEMORY_DIRS = {
    "life": {
        "core": "life/core",
        "timeline": "life/timeline",
        "facts": "life/facts", 
        "pending": "life/pending",
        "archive": "life/archive",
    },
    "work": {
        "facts": "work/facts",
        "preferences": "work/preferences",
        "people": "work/people",
        "skills": "work/skills",
        "projects": "work/projects",
    }
}

# ==================== FTS5 配置 ====================
FTS5_TABLE_NAME: str = "fts_index"
FTS5_META_TABLE_NAME: str = "fts_index_meta"
FTS5_TOKENIZER: str = "unicode61"       # 支持中文的分词器

# ==================== 强指代回溯触发词 ====================
ANAPHORA_TRIGGER_WORDS: List[str] = [
    "上次", "之前", "先前", "类似", "像上次", "跟之前", "上回", "前一次"
]

# ==================== 文件编码 ====================
FILE_ENCODING: str = "utf-8"
