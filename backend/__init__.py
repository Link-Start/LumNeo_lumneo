# backend/__init__.py
from pathlib import Path


workspace_dir = Path.cwd() / 'workspace'
workspace_dir.mkdir(parents=True, exist_ok=True)

workspace_path = str(workspace_dir)