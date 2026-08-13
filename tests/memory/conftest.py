# tests/memory/conftest.py
"""MemoryOS 测试共用配置"""
import sys
from pathlib import Path

# 将项目根目录添加到 Python 路径，确保 backend 可导入
project_root = Path(__file__).parent.parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

# 确保 backend.memory 可被导入
backend_path = project_root / "backend"
if str(backend_path) not in sys.path:
    sys.path.insert(0, str(backend_path))