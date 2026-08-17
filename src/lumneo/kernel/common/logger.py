# kernel/common/logger.py
# Kernel / Common —— 全局日志原语（系统级共享能力）。
#
# 对应原 backend.bootstrap.py 的 _ensure_stdio() / setup_logging()。
# 该模块在任意第三方库加载前完成 stdio 防护与日志配置，并导出全局 logger。
# 其它模块统一通过 `from lumneo.kernel.common.logger import logger` 获取 logger，
# 避免散落的 logging.getLogger 调用。
import os
import sys
import logging
import datetime


def _ensure_stdio() -> None:
    """确保 stdio 不为 None，防止 GUI / 无控制台模式下第三方库写入崩溃。"""
    if sys.stdout is None:
        sys.stdout = open(os.devnull, "w", encoding="utf-8")
    if sys.stderr is None:
        sys.stderr = open(os.devnull, "w", encoding="utf-8")
    if sys.stdin is None:
        sys.stdin = open(os.devnull, "r", encoding="utf-8")


def setup_logging() -> logging.Logger:
    """配置全局日志，返回根 Logger 实例。"""
    logger = logging.getLogger("LumNeo")
    logger.setLevel(logging.INFO)
    logger.propagate = False  # 防止重复输出日志

    if logger.handlers:
        return logger

    formatter = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    original_stderr = getattr(sys, "__stderr__", sys.stderr)
    console_handler = logging.StreamHandler(original_stderr)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    is_frozen = getattr(sys, "frozen", False)
    is_gui_mode = sys.stdout is not sys.__stdout__

    # 延迟导入 config，避免早期循环；日志目录在 config 可用时再挂文件 handler。
    try:
        from lumneo.kernel.config.app_config import config
        logs_dir = config.logs_dir
    except Exception:
        logs_dir = None

    if (is_frozen or is_gui_mode) and logs_dir is not None:
        try:
            os.makedirs(str(logs_dir), exist_ok=True)
            now = datetime.datetime.now()
            log_filename = f"lumneo_{now.strftime('%Y-%m')}.log"  # 按月份分日志文件
            file_handler = logging.FileHandler(
                os.path.join(str(logs_dir), log_filename), encoding="utf-8"
            )
            file_handler.setFormatter(formatter)
            logger.addHandler(file_handler)
        except Exception:
            # 日志初始化失败不应阻断启动
            pass

    return logger


# ⚡ 模块级自动执行：只要被 import，stdio 防护立即生效
_ensure_stdio()

# 导出全局 logger，其他模块直接 `from lumneo.kernel.common.logger import logger`
logger = setup_logging()
