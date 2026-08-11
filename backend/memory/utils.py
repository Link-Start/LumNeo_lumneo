# backend/memory/utils.py
"""
Lumneo 长期记忆系统 - 工具函数
"""
import re
import yaml
from pathlib import Path
from typing import Tuple, Optional, List, Dict, Any
from datetime import datetime

from backend.memory.config import (
    DOMAIN_WHITELIST, MEMORY_DIRS, DEFAULT_MEMORY_DIR, FILE_ENCODING
)
from backend.memory.models import MemoryFrontmatter


# ==================== Frontmatter 解析与序列化 ====================

FRONTMATTER_PATTERN = re.compile(r"^---\s*\n(.*?)\n---\s*\n?(.*)$", re.DOTALL)


def parse_frontmatter(raw_text: str) -> Tuple[Optional[MemoryFrontmatter], str]:
    """
    解析 Markdown 文件的 YAML Frontmatter。

    Returns:
        (frontmatter, content) - 若无 frontmatter 则 frontmatter 为 None
    """
    match = FRONTMATTER_PATTERN.match(raw_text.strip())
    if not match:
        return None, raw_text.strip()

    yaml_text = match.group(1).strip()
    content = match.group(2).strip()

    try:
        data = yaml.safe_load(yaml_text) or {}
        if not isinstance(data, dict):
            data = {}
        frontmatter = MemoryFrontmatter.from_dict(data)
        return frontmatter, content
    except yaml.YAMLError:
        # YAML 解析失败，返回 None frontmatter
        return None, raw_text.strip()


def serialize_frontmatter(frontmatter: MemoryFrontmatter, content: str, update_updated_at: bool = True) -> str:
    """
    将 Frontmatter 和正文序列化为完整的 Markdown 文件内容。
    """
    data = frontmatter.to_dict()
    if update_updated_at:
        data["updated_at"] = datetime.now().isoformat()

    # 确保基础字段存在
    data.setdefault("category", frontmatter.category)
    data.setdefault("key", frontmatter.key)
    data.setdefault("created_at", frontmatter.created_at)
    data.setdefault("updated_at", datetime.now().isoformat())

    yaml_text = yaml.safe_dump(
        data,
        allow_unicode=True,
        sort_keys=False,
        default_flow_style=False,
        width=1000,  # 避免自动换行
    )

    return f"---\n{yaml_text}---\n\n{content.strip()}\n"


# ==================== 文件路径生成 ====================

def sanitize_filename(key: str) -> str:
    """
    将 key 转换为安全的文件名。
    移除/替换非法字符，限制长度。
    """
    # 替换常见非法字符
    safe = re.sub(r'[\\/:*?"<>|]', '_', key)
    # 限制长度
    if len(safe) > 100:
        safe = safe[:100]
    safe = safe.strip()
    # 处理空字符串或仅含非法字符的情况
    if not safe:
        safe = "untitled"
    return safe


def generate_memory_path(
    scope: str,
    category: str,
    key: str,
    memory_dir: Optional[Path] = None,
    suffix: Optional[str] = None
) -> Path:
    """
    根据 scope、category、key 生成记忆文件的存储路径。

    Args:
        scope: "life" 或 "work"
        category: fact | preference | person | decision | skill | pending
        key: 记忆的 key（如 "技术栈"）
        memory_dir: 记忆根目录，默认使用 DEFAULT_MEMORY_DIR
        suffix: 可选的文件名后缀（如时间戳），用于版本链

    Returns:
        完整的文件 Path
    """
    root = memory_dir or DEFAULT_MEMORY_DIR

    # 确定子目录
    if scope == "life":
        if category == "skill":
            raise ValueError("skill category is not allowed in life scope")
        elif category in ("fact", "preference", "person"):
            subdir = MEMORY_DIRS["life"]["facts"]
        elif category == "pending":
            subdir = MEMORY_DIRS["life"]["pending"]
        else:
            subdir = MEMORY_DIRS["life"]["facts"]
    else:  # work
        if category in MEMORY_DIRS["work"]:
            subdir = MEMORY_DIRS["work"][category]
        else:
            subdir = MEMORY_DIRS["work"]["facts"]

    safe_key = sanitize_filename(key)

    # 构建文件名
    if suffix:
        filename = f"{category}_{safe_key}_{suffix}.md"
    else:
        filename = f"{category}_{safe_key}.md"

    return root / subdir / filename


def generate_timeline_path(
    date_str: str,
    memory_dir: Optional[Path] = None
) -> Path:
    """
    生成 Timeline 日文件路径。

    Args:
        date_str: 日期字符串，格式 "YYYY-MM-DD"
        memory_dir: 记忆根目录

    Returns:
        Path 如 data/memory/life/timeline/2026/08/days/2026-08-07.md
    """
    root = memory_dir or DEFAULT_MEMORY_DIR
    date_obj = datetime.strptime(date_str, "%Y-%m-%d")
    year = date_obj.strftime("%Y")
    month = date_obj.strftime("%m")

    return root / "life" / "timeline" / year / month / "days" / f"{date_str}.md"


def generate_monthly_summary_path(
    year: int,
    month: int,
    memory_dir: Optional[Path] = None
) -> Path:
    """
    生成月度摘要文件路径。

    Returns:
        Path 如 data/memory/life/timeline/2026/08/monthly/monthly_2026-08.md
    """
    root = memory_dir or DEFAULT_MEMORY_DIR
    return root / "life" / "timeline" / str(year) / f"{month:02d}" / "monthly" / f"monthly_{year}-{month:02d}.md"


def generate_pending_path(
    timestamp: Optional[str] = None,
    memory_dir: Optional[Path] = None
) -> Path:
    """
    生成 Pending 文件路径。

    Args:
        timestamp: 时间戳字符串，默认使用当前时间
    """
    root = memory_dir or DEFAULT_MEMORY_DIR
    if timestamp is None:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return root / "life" / "pending" / f"pending_{timestamp}.md"


# ==================== 敏感度预检 ====================

def sensitivity_precheck(text: str) -> str:
    """
    轻量规则检测文本敏感度，自动标记 private/secret。

    Returns:
        "normal" | "private" | "secret"
    """
    # secret 模式：身份证号、手机号、密码、地址
    secret_patterns = [
        r"\d{17}[\dXx]",           # 身份证号
        r"(?<!\d)1[3-9]\d{9}(?!\d)",              # 手机号
        r"(?<![a-zA-Z0-9_])密码[是为:\s]*\S{1,30}",  # 密码
        r"地址[是为:]+?\S+",          # 地址
        r"\d{4}\s?年\s?\d{1,2}\s?月\s?\d{1,2}\s?日",  # 完整生日
    ]

    # private 模式：健康、财务、家庭关系
    private_patterns = [
        r"(医院|病历|诊断|手术|复查|膝盖|腰|心脏|血压|血糖|抑郁|焦虑)",
        r"(工资|收入|存款|房贷|车贷|投资|亏损|盈利|股票|基金)",
        r"(离婚|结婚|恋爱|分手|孩子|父母|亲戚|家庭矛盾)",
    ]

    for pattern in secret_patterns:
        if re.search(pattern, text):
            return "secret"

    for pattern in private_patterns:
        if re.search(pattern, text):
            return "private"

    return "normal"


# ==================== Domain 归一化 ====================

def normalize_domain(domain: Optional[str]) -> str:
    """
    将 domain 归一化为白名单中的值。
    非法值 fallback 到 'general'。
    """
    if not domain:
        return "general"

    domain_lower = domain.lower().strip()

    # 常见别名映射
    alias_map = {
        "后端": "backend",
        "前端": "frontend",
        "运维": "devops",
        "人工智能": "ai",
        "产品": "product",
        "设计": "design",
        "基础设施": "infra",
        "安全": "security",
        "back-end": "backend",
        "front-end": "frontend",
        "back_end": "backend",
        "front_end": "frontend",
    }

    normalized = alias_map.get(domain_lower, domain_lower)

    if normalized in DOMAIN_WHITELIST:
        return normalized
    return "general"


# ==================== 文件读取辅助 ====================

async def read_markdown_file(file_path: Path) -> Tuple[Optional[MemoryFrontmatter], str]:
    """
    异步读取 Markdown 文件，解析 frontmatter 和正文。
    """
    import aiofiles

    if not file_path.exists():
        return None, ""

    async with aiofiles.open(file_path, "r", encoding=FILE_ENCODING) as f:
        raw = await f.read()

    return parse_frontmatter(raw)


def read_markdown_file_sync(file_path: Path) -> Tuple[Optional[MemoryFrontmatter], str]:
    """
    同步读取 Markdown 文件（用于非 async 场景）。
    """
    if not file_path.exists():
        return None, ""

    with open(file_path, "r", encoding=FILE_ENCODING) as f:
        raw = f.read()

    return parse_frontmatter(raw)

def estimate_tokens(text: str) -> int:
    """粗略估算 Token 数"""
    if not text:
        return 0
    chinese_chars = len(re.findall(r'[一-鿿]', text))
    english_words = len(re.findall(r'[a-zA-Z]+', text))
    return chinese_chars + int(english_words * 1.3) + 10


def parse_json_extraction(raw: str) -> List[Dict[str, Any]]:
    """统一解析 LLM 返回的 JSON 数组"""
    if not raw or not raw.strip():
        return []
    import re, json
    text = raw.strip()
    code_block = re.search(r"```(?:json)?\s*([\s\S]*?)```", text)
    if code_block:
        text = code_block.group(1).strip()
    arr_start = text.find("[")
    arr_end = text.rfind("]")
    if arr_start != -1 and arr_end != -1 and arr_end > arr_start:
        text = text[arr_start:arr_end+1]
    text = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]', '', text)
    try:
        parsed = json.loads(text)
        if isinstance(parsed, list):
            return parsed
        elif isinstance(parsed, dict):
            for key in ("memories", "facts", "skills", "results", "data"):
                if key in parsed and isinstance(parsed[key], list):
                    return parsed[key]
            return [parsed]
    except json.JSONDecodeError:
        pass
    return []