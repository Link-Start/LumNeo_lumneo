# infrastructure/filesystem/local_storage.py
# Local File Storage Adapter（§37 / §38 / §39）。
#
# StoragePort 的本地磁盘实现。集中了所有“物理文件落盘 / 删除”操作，
# 领域与工具只通过 StoragePort 抽象访问，不直接 open()/os.remove()。
import json
import os
import tempfile
from pathlib import Path
from typing import List, Optional

from lumneo.kernel.config.app_config import config
from lumneo.kernel.common.logger import logger
from lumneo.infrastructure.filesystem.storage_port import StoragePort


class LocalFileStorage(StoragePort):
    """基于本地磁盘的 StoragePort 实现。"""

    def __init__(self, base_dir: Optional[Path] = None):
        # base_dir 用于 write_under / read_under 的默认根（默认 cache_dir）。
        self.base_dir = Path(base_dir) if base_dir else Path(config.cache_dir)

    # ───────────────────────── 基础读写 ─────────────────────────
    def read_text(self, path: str, encoding: str = "utf-8") -> str:
        return Path(path).read_text(encoding=encoding)

    def write_text(self, path: str, content: str, encoding: str = "utf-8") -> int:
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding=encoding)
        return len(content.encode(encoding))

    def read_bytes(self, path: str) -> bytes:
        return Path(path).read_bytes()

    def write_bytes(self, path: str, data: bytes) -> int:
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(data)
        return len(data)

    def delete(self, path: str) -> bool:
        p = Path(path)
        if p.exists():
            try:
                p.unlink()
                return True
            except Exception as e:  # pragma: no cover - 防御性
                logger.error(f"删除文件失败 {p}: {e}")
                return False
        return False

    def delete_many(self, paths: List[str]) -> List[str]:
        """批量删除，返回实际删除失败的路径列表（空表示全部成功）。"""
        failed: List[str] = []
        for p in paths:
            if not self.delete(p):
                failed.append(p)
        return failed

    def exists(self, path: str) -> bool:
        return Path(path).exists()

    def list_files(self, directory: str, recursive: bool = True,
                   pattern: Optional[str] = None) -> List[str]:
        d = Path(directory)
        if not d.exists():
            return []
        if recursive:
            iterator = d.rglob(pattern) if pattern else d.rglob("*")
        else:
            iterator = d.glob(pattern) if pattern else d.glob("*")
        return [str(p) for p in iterator if p.is_file()]

    # ───────────────────────── 相对根读写 ─────────────────────────
    def write_under(self, root: str, relative_path: str, content: str,
                    encoding: str = "utf-8") -> str:
        root_path = Path(root)
        target = (root_path / relative_path).resolve()
        # 防越权：确保目标仍位于 root 之内
        if root_path.resolve() not in target.parents and target != root_path.resolve():
            raise ValueError(f"相对路径越权：{relative_path} 超出根目录 {root}")
        self.write_text(str(target), content, encoding=encoding)
        return str(target)

    def read_under(self, root: str, relative_path: str, encoding: str = "utf-8") -> str:
        target = (Path(root) / relative_path).resolve()
        return self.read_text(str(target), encoding=encoding)

    # ───────────────────────── 大结果存储 ─────────────────────────
    def store_large_text(self, relative_key: str, text: str, encoding: str = "utf-8") -> str:
        """将大文本结果写入 cache_dir 下的相对路径，返回该相对路径（供 DB 记录）。"""
        rel = relative_key.replace("\\", "/").lstrip("/")
        self.write_under(str(config.cache_dir), rel, text, encoding=encoding)
        return rel

    def read_large_text(self, relative_key: str, encoding: str = "utf-8") -> str:
        """读取 store_large_text 写入的内容。"""
        return self.read_under(str(config.cache_dir), relative_key, encoding=encoding)

    # ───────────────────────── 上传文件清理 ─────────────────────────
    @staticmethod
    def delete_uploaded_files(file_ref_json: str) -> None:
        """根据 file_ref JSON 字符串，删除对应的物理上传文件。

        由 Repository 在删除会话 / 消息时返回磁盘路径，最终由基础设施执行实际删除，
        避免 Repository 直接做文件 I/O（§39 / §60）。
        """
        if not file_ref_json:
            return
        try:
            ref_data = json.loads(file_ref_json)
        except Exception as e:
            logger.warning(f"解析 file_ref 失败: {e}")
            return
        if isinstance(ref_data, dict):
            ref_data = [ref_data]
        if not isinstance(ref_data, list):
            return
        for item in ref_data:
            url = item.get("url") if isinstance(item, dict) else None
            if not url or "/uploads/" not in url:
                continue
            filename = url.split("/uploads/")[-1]
            phys_path = os.path.join(str(config.uploads_dir), filename)
            try:
                if os.path.exists(phys_path):
                    os.remove(phys_path)
            except Exception as e:
                logger.error(f"删除上传文件失败 {phys_path}: {e}")
