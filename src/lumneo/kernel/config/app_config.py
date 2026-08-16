# src/lumneo/kernel/config/app_config.py
# Kernel / Config —— 配置基础能力（不拥有具体业务配置逻辑）。
#
# 对应原 config_loader.py。仅负责加载 app_config.yaml、解析并校验路径、
# 确保可写目录存在。任何业务策略（Memory Ranking / Hardware Execution 等）
# 不得放入此处。
import os
import sys
from pathlib import Path

import yaml


def find_project_root(start: Path | None = None) -> Path:
    """向上回溯，定位包含 app_config.yaml 的项目根目录。

    同时兼容开发环境（cwd 即项目根）与打包环境（_MEIPASS 内）。
    """
    search = start or Path(__file__).resolve()
    # 也从当前工作目录开始找，覆盖 `python main.py` 直接运行的场景
    candidates = [search, Path.cwd()]
    if getattr(sys, "frozen", False):
        candidates.append(Path(getattr(sys, "_MEIPASS", ".")))

    seen = set()
    for base in candidates:
        base = base.resolve()
        for _ in range(8):  # 最多向上 8 层
            if (base / "app_config.yaml").exists():
                return base
            if str(base) in seen:
                break
            seen.add(str(base))
            parent = base.parent
            if parent == base:
                break
            base = parent
    # 兜底：返回当前工作目录
    return Path.cwd().resolve()


class AppConfig:
    """全局应用配置。"""

    def __init__(self, config_file: str = "app_config.yaml"):
        self.config_file = config_file
        self.project_root = find_project_root()
        self.raw_config = self._load_yaml()
        self._resolve_paths()
        self._ensure_dirs()

    def _load_yaml(self):
        search_paths = [
            self.project_root / self.config_file,
            Path.cwd() / self.config_file,
        ]
        if getattr(sys, "frozen", False):
            search_paths.append(Path(getattr(sys, "_MEIPASS", ".")) / self.config_file)

        for path in search_paths:
            if path.exists():
                with open(path, "r", encoding="utf-8") as f:
                    return yaml.safe_load(f) or {}

        # 未找到时使用内置默认，保证系统可启动
        return {}

    def _resolve_paths(self):
        if getattr(sys, "frozen", False):
            self.executable_dir = Path(sys.executable).parent
            self.resource_dir = Path(getattr(sys, "_MEIPASS", str(self.project_root)))
            data_dir_raw = self.raw_config.get("data_dir", "data")
            self.data_dir = self._resolve_path(data_dir_raw, base=self.executable_dir)
        else:
            self.resource_dir = self.project_root
            self.data_dir = self.project_root

        self.uploads_dir = self.data_dir / self.raw_config.get("uploads_dir", "data/uploads")
        self.cache_dir = self.data_dir / self.raw_config.get("cache_dir", "data/cache")
        self.logs_dir = self.data_dir / self.raw_config.get("logs_dir", "logs")
        self.temp_dir = self.data_dir / self.raw_config.get("temp_dir", "temp")
        self.skills_dir = self.data_dir / self.raw_config.get("skills_dir", "skills")
        self.generate_dir = self.data_dir / self.raw_config.get("generate_dir", "data/generate")

        mcp_raw = self.raw_config.get("mcp_config_path", "mcp_config.json")
        if Path(mcp_raw).is_absolute():
            self.mcp_config_path = Path(mcp_raw)
        else:
            self.mcp_config_path = self.data_dir / mcp_raw

        static_rel = self.raw_config.get("static_dir", "html")
        self.static_dir = self.resource_dir / static_rel

        self.max_upload_size = int(self.raw_config.get("max_upload_size_mb", 100)) * 1024 * 1024

    def _resolve_path(self, path_str: str, base: Path) -> Path:
        p = Path(path_str)
        if p.is_absolute():
            return p
        return base / p

    def _ensure_dirs(self):
        dirs = [
            self.data_dir,
            self.uploads_dir,
            self.cache_dir,
            self.logs_dir,
            self.temp_dir,
            self.skills_dir,
            self.generate_dir,
        ]
        for d in dirs:
            try:
                d.mkdir(parents=True, exist_ok=True)
            except PermissionError:
                fallback_base = Path(
                    os.environ.get("APPDATA", Path.home() / "AppData/Roaming")
                ) / ".LumNeo"
                self.data_dir = fallback_base
                self.uploads_dir = fallback_base / "uploads"
                self.cache_dir = fallback_base / "cache"
                self.logs_dir = fallback_base / "logs"
                self.temp_dir = fallback_base / "temp"
                self.skills_dir = fallback_base / "skills"
                self.mcp_config_path = fallback_base / "mcp_config.json"
                for d2 in [
                    self.data_dir,
                    self.uploads_dir,
                    self.cache_dir,
                    self.logs_dir,
                    self.temp_dir,
                    self.skills_dir,
                ]:
                    d2.mkdir(parents=True, exist_ok=True)
                break

    @property
    def frontend_index(self) -> str:
        if getattr(sys, "frozen", False):
            base_path = Path(getattr(sys, "_MEIPASS", str(self.project_root)))
        else:
            base_path = self.project_root

        index_path = base_path / "frontend/dist/index.html"
        if not index_path.exists():
            fallback_path = self.static_dir / "index.html"
            if fallback_path.exists():
                index_path = fallback_path
            else:
                raise FileNotFoundError(f"前端入口文件不存在: {index_path}")
        return str(index_path.resolve())

    def resource_path(self, relative_path: str) -> str:
        """获取打包/开发环境下的资源绝对路径（图标等）。"""
        if getattr(sys, "frozen", False):
            base_path = Path(getattr(sys, "_MEIPASS", str(self.project_root)))
        else:
            base_path = self.project_root
        return str(base_path / relative_path)

    @property
    def db_path(self) -> Path:
        """数据库文件路径。

        与 uploads / cache / generate 同处 data 子目录（data_dir/data），
        开发态下即 项目根/data/lumneo.db，避免散落到项目根目录。
        """
        return self.data_dir / "data" / "lumneo.db"


config = AppConfig()
