# src/lumneo/__init__.py
from pathlib import Path

# 工作区根目录（可被 API 在运行时动态修改，见 api/routes/workspace.py）

workspace_dir = Path.cwd() / "workspace"
workspace_path = str(workspace_dir)
