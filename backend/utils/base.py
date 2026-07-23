# backend/utils/base.py
import os
import sys
import json
import socket
from pathlib import Path
from datetime import datetime, timezone as tz
from config_loader import config
from typing import Optional, Tuple
from backend.bootstrap import logger
from backend.utils.validators import validate_path
import backend


def is_absolute(path: str) -> bool:
    return Path(path).is_absolute()

def resource_path(relative_path):
    """获取资源的绝对路径，兼容 PyInstaller 打包"""
    if getattr(sys, 'frozen', False):
        base_path = sys._MEIPASS
    else:
        current_dir = os.path.dirname(os.path.abspath(__file__))
        base_path = os.path.dirname(os.path.dirname(current_dir))
    return os.path.join(base_path, relative_path)

def get_current_time(timezone: str = "local") -> str:
    """
    获取当前真实的日期和时间。

    在没有明确时区的情况下直接使用默认值"local"。
    
    Args:
        timezone: 时区设置，可选值：
            - "local": 本地时间（默认）
            - "utc": UTC 时间
            - "iso": ISO 8601 格式的 UTC 时间
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
        
        return f"{now.strftime("%Y-%m-%d %H:%M:%S")} {weekday_cn} "
    except Exception as e:
        return f"获取时间失败：{str(e)}"

def get_local_ip():
    """获取本机IP地址"""
    try:
        # 创建一个UDP套接字，连接到一个外部地址（不发送数据）
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"
    
def delete_uploaded_files(file_ref_json: str):
    """根据 file_ref JSON 字符串，删除对应的物理上传文件"""
    if not file_ref_json:
        return
    try:
        ref_data = json.loads(file_ref_json)
        # 如果只是单个对象，转成数组统一处理
        if isinstance(ref_data, dict):
            ref_data = [ref_data]

        for item in ref_data:
            url = item.get('url')
            if not url:
                continue
            
            # 提取文件名，拼接物理路径
            # 通常 url 类似 /files/uploads/xxx.jpg 或 /uploads/xxx.jpg
            if '/uploads/' in url:
                # 截取 uploads 后的部分作为文件名
                filename = url.split('/uploads/')[-1]
                phys_path = os.path.join(config.uploads_dir, filename)
                
                if os.path.exists(phys_path):
                    try:
                        os.remove(phys_path)
                    except Exception as e:
                        logger.error(f"删除上传文件失败 {phys_path}: {e}")
    except Exception as e:
        # 避免解析错误导致主流程中断
        logger.warning(f"解析 file_ref 失败: {e}")


def _get_allowed_dirs() -> list[Path]:
    """获取允许操作的目录列表。"""
    raw = backend.workspace_path
    if not raw:
        raise RuntimeError("backend.workspace_path 未配置")
    if isinstance(raw, (list, tuple)):
        return [Path(p).resolve() for p in raw if p]
    return [Path(raw).resolve()]


def _validate(path: str) -> Tuple[Optional[Path], Optional[str]]:
    """统一路径校验，返回 (safe_path, error_message)。"""
    if not is_absolute(path):
        path = f"{os.getcwd()}/{path}"
    try:
        safe_path = validate_path(path, _get_allowed_dirs())
        return safe_path, None
    except (ValueError, RuntimeError) as e:
        return None, str(e)