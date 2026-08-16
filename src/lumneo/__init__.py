# src/lumneo/__init__.py
# LumNeo V2 —— 应用根包
#
# 根据《LumNeo V2 Architecture & Dependency Governance Specification》重构后的
# 代码组织。本包只承担极轻量的运行时状态（如当前工作区路径），不导入任何子模块，
# 以避免循环依赖。
from pathlib import Path

# 工作区根目录（可被 API 在运行时动态修改，见 api/routes/workspace.py）。
# 原 backend.workspace_path 的等价物，供文件系统工具做路径越权校验。
workspace_dir = Path.cwd() / "workspace"
workspace_path = str(workspace_dir)
