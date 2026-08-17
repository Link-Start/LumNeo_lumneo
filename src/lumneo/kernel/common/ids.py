# src/lumneo/kernel/common/ids.py
# Kernel / Common —— ID 与时钟原语（系统级共享能力）。
import uuid
import datetime


def new_id() -> str:
    """生成全局唯一 ID。"""
    return str(uuid.uuid4())


def new_short_id(length: int = 12) -> str:
    """生成短 ID（用于 plan_id 等非保密标识）。"""
    return uuid.uuid4().hex[:length]


def now_iso() -> str:
    """当前本地时间的 ISO 字符串。"""
    return datetime.datetime.now().isoformat()


def utcnow_iso() -> str:
    """当前 UTC 时间的 ISO 字符串。"""
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def clock() -> datetime.datetime:
    """当前时间（业务可注入的时钟原语入口）。"""
    return datetime.datetime.now()
