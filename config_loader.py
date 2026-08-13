# config_loader.py
import os
import sys
from pathlib import Path
import yaml

class AppConfig:
    def __init__(self, config_file="app_config.yaml"):
        self.config_file = config_file
        self.raw_config = self._load_yaml()
        self._resolve_paths()
        self._ensure_dirs()

    def _load_yaml(self):
        # 搜索 config.yaml 的位置：当前工作目录 -> exe 所在目录 -> 代码目录
        search_paths = [
            Path.cwd() / self.config_file,
            Path(sys.executable).parent / self.config_file,
        ]
        if not getattr(sys, 'frozen', False):
            # 开发环境，尝试当前文件所在目录
            search_paths.append(Path(__file__).parent / self.config_file)
        else:
            search_paths.append(Path(sys._MEIPASS) / self.config_file)
        
        for path in search_paths:
            if path.exists():
                with open(path, 'r', encoding='utf-8') as f:
                    return yaml.safe_load(f)
        
        raise FileNotFoundError(f"配置文件 {self.config_file} 未找到，搜索路径: {search_paths}")

    def _resolve_paths(self):
        # 确定基础目录（用于相对路径解析）
        if getattr(sys, 'frozen', False):
            self.executable_dir = Path(sys.executable).parent  # exe 所在目录
            self.resource_dir = Path(sys._MEIPASS)            # 打包资源临时目录
            data_dir_raw = self.raw_config.get("data_dir", "data")
            self.data_dir = self._resolve_path(data_dir_raw, base=self.executable_dir)
        else:
            self.resource_dir = Path.cwd()
            self.data_dir = Path.cwd()
        
        # 子目录（相对于 data_dir）
        self.uploads_dir = self.data_dir / self.raw_config.get("uploads_dir", "data/uploads")
        self.cache_dir = self.data_dir / self.raw_config.get("cache_dir", "data/cache")
        self.logs_dir = self.data_dir / self.raw_config.get("logs_dir", "logs")
        self.temp_dir = self.data_dir / self.raw_config.get("temp_dir", "temp")
        self.skills_dir = self.data_dir / self.raw_config.get("skills_dir", "skills")
        self.generate_dir = self.data_dir / self.raw_config.get("generate_dir", "data/generate")
        
        # mcp_config.json 路径：可以是绝对路径或相对于 data_dir
        mcp_raw = self.raw_config.get("mcp_config_path", "mcp_config.json")
        if Path(mcp_raw).is_absolute():
            self.mcp_config_path = Path(mcp_raw)
        else:
            self.mcp_config_path = self.data_dir / mcp_raw
        
        # 静态文件目录（只读，位于 resource_dir 下）
        static_rel = self.raw_config.get("static_dir", "frontend/dist")
        self.static_dir = self.resource_dir / static_rel
        
        # 其他配置项
        self.max_upload_size = int(self.raw_config.get("max_upload_size_mb", 100)) * 1024 * 1024

        # ========== MemoryOS 路径解析 ==========
        memory_cfg = self.raw_config.get("memory", {})
        memory_data_raw = memory_cfg.get("data_dir", "data/memory")
        # 支持绝对路径或相对于 data_dir
        if Path(memory_data_raw).is_absolute():
            self.memory_data_dir = Path(memory_data_raw)
        else:
            self.memory_data_dir = self.data_dir / memory_data_raw

        # 固定子目录
        self.memory_index_dir = self.memory_data_dir / "index"
        self.memory_governance_dir = self.memory_data_dir / "governance"
        # 索引数据库路径
        index_db_name = memory_cfg.get("index_db", "fts5.db")
        self.memory_index_db = self.memory_index_dir / index_db_name

        # 检索参数（保留供后续使用）
        retrieval_cfg = memory_cfg.get("retrieval", {})
        self.memory_alpha = retrieval_cfg.get("alpha", 0.65)
        self.memory_decay_coefficient = retrieval_cfg.get("decay_coefficient", 0.05)

        # 治理参数
        governance_cfg = memory_cfg.get("governance", {})
        self.memory_review_timeout_days = governance_cfg.get("review_timeout_days", 7)

    def _resolve_path(self, path_str: str, base: Path) -> Path:
        """将路径字符串解析为 Path 对象，支持绝对路径和相对路径"""
        p = Path(path_str)
        if p.is_absolute():
            return p
        else:
            return base / p

    def _ensure_dirs(self):
        """确保所有可写目录存在（data_dir 及其子目录）"""
        dirs = [self.data_dir, self.uploads_dir, self.cache_dir, self.logs_dir, self.temp_dir, self.skills_dir, self.generate_dir]
        for d in dirs:
            try:
                d.mkdir(parents=True, exist_ok=True)
            except PermissionError:
                # 如果 ProgramData 无权限，尝试 fallback 到用户目录
                fallback_base = Path(os.environ.get('APPDATA', Path.home() / 'AppData/Roaming')) / '.LumNeo'
                # 重新设定所有路径
                self.data_dir = fallback_base
                self.uploads_dir = fallback_base / "uploads"
                self.cache_dir = fallback_base / "cache"
                self.logs_dir = fallback_base / "logs"
                self.temp_dir = fallback_base / "temp"
                self.skills_dir = fallback_base / "skills"
                self.mcp_config_path = fallback_base / "mcp_config.json"
                # 再次创建
                for d2 in [self.data_dir, self.uploads_dir, self.cache_dir, self.logs_dir, self.temp_dir, self.skills_dir]:
                    d2.mkdir(parents=True, exist_ok=True)
                break

        # ========== MemoryOS 目录创建 ==========
        # 定义 MemoryOS 所有子目录（按 ADR-009 §2）
        memory_subdirs = [
            self.memory_data_dir,
            self.memory_data_dir / "identity",
            self.memory_data_dir / "episodic",
            self.memory_data_dir / "semantic",
            self.memory_data_dir / "procedural",
            self.memory_governance_dir,
            self.memory_governance_dir / "needs_review",
            self.memory_governance_dir / "rejected",
            self.memory_governance_dir / "conflicts",
            self.memory_governance_dir / "auto_actions",
            self.memory_governance_dir / "index_rebuild_log",
            self.memory_index_dir,
        ]
        for d in memory_subdirs:
            try:
                d.mkdir(parents=True, exist_ok=True)
            except PermissionError:
                # 如果 memory_data_dir 权限不足，尝试 fallback 到应用 data_dir 下的 memory
                fallback_memory = self.data_dir / "memory"
                # 重新设定 memory_data_dir 为 fallback
                self.memory_data_dir = fallback_memory
                self.memory_index_dir = fallback_memory / "index"
                self.memory_governance_dir = fallback_memory / "governance"
                self.memory_index_db = self.memory_index_dir / "fts5.db"
                # 重新创建 fallback 子目录
                for d2 in [
                    fallback_memory,
                    fallback_memory / "identity",
                    fallback_memory / "episodic",
                    fallback_memory / "semantic",
                    fallback_memory / "procedural",
                    fallback_memory / "governance",
                    fallback_memory / "governance/needs_review",
                    fallback_memory / "governance/rejected",
                    fallback_memory / "governance/conflicts",
                    fallback_memory / "governance/auto_actions",
                    fallback_memory / "governance/index_rebuild_log",
                    fallback_memory / "index",
                ]:
                    d2.mkdir(parents=True, exist_ok=True)
                break

    @property
    def frontend_index(self) -> str:
        """返回前端入口文件的本地文件路径"""
        if getattr(sys, 'frozen', False):
            # 打包后的环境，资源文件在 sys._MEIPASS 中
            base_path = Path(sys._MEIPASS)
        else:
            base_path = self.base_dir

        index_path = base_path / "frontend/dist/index.html"

        if not index_path.exists():
            fallback_path = self.static_dir / "index.html"
            if fallback_path.exists():
                index_path = fallback_path
            else:
                raise FileNotFoundError(f"前端入口文件不存在: {index_path}")

        return str(index_path.resolve())

    def resource_path(self, relative_path: str) -> str:
        """获取打包后资源文件的绝对路径（用于图标等）"""
        if getattr(sys, 'frozen', False):
            # 打包环境，资源在 sys._MEIPASS 中
            base_path = Path(sys._MEIPASS)
        else:
            # 开发环境，相对于当前文件所在目录
            base_path = Path(__file__).parent
        return str(base_path / relative_path)

config = AppConfig()