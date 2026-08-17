# LumNeo V2 仓库根入口（薄启动器）。
#
# 真实的程序代码位于 src/lumneo 包内；本文件仅把 src 目录加入 Python
# 模块搜索路径，再调用 lumneo.main:main()，使你可以像原项目一样在仓库根目录
# 直接执行：`python main.py`。
#
# 备选运行方式（无需本文件）：
#   cd src && python -m lumneo.main
#   PYTHONPATH=src python src/lumneo/main.py
import os
import sys

_SRC_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "src")
if _SRC_DIR not in sys.path:
    sys.path.insert(0, _SRC_DIR)

from lumneo.main import main

if __name__ == "__main__":
    main()
