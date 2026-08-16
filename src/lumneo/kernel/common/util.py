# kernel/common/util.py
# 通用工具函数（原 backend/utils/base.py 中的轻量纯函数）。
#
# 仅保留与具体业务无强耦合的辅助函数；路径校验已迁至 infrastructure.filesystem.path_guard，
# file_ref 删除已迁至 infrastructure.filesystem.local_storage。
import socket
from datetime import datetime, timezone as tz


def get_typeName(type: str) -> str:
    """模型类型中文名。"""
    if type == "local":
        return "本地"
    return "云端"


def get_current_time(timezone: str = "local") -> str:
    """获取当前真实的日期和时间。

    Args:
        timezone: "local" 本地时间（默认） | "utc" UTC 时间 | "iso" ISO8601 UTC
    """
    try:
        if timezone == "utc":
            now = datetime.now(tz.utc)
            tz_info = "UTC"
        elif timezone == "iso":
            now = datetime.now(tz.utc)
            return {
                "success": True,
                "iso": now.isoformat().replace("+00:00", "Z"),
                "timestamp": int(now.timestamp()),
                "timezone": "UTC",
            }
        else:  # local
            now = datetime.now()
            tz_info = "本地时间"

        weekdays = ["星期一", "星期二", "星期三", "星期四", "星期五", "星期六", "星期日"]
        weekday_cn = weekdays[now.weekday()]

        return f"{now.strftime('%Y-%m-%d %H:%M:%S')} {weekday_cn} "
    except Exception as e:
        return f"获取时间失败：{str(e)}"


def get_local_ip() -> str:
    """获取本机 IP 地址（用于前端连接本地服务）。"""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"
