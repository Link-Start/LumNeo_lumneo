# backend/system_tools/executor.py
"""
脚本执行器 —— 安全执行技能库内的脚本

安全策略：
1. 路径越权防护：脚本必须严格位于 skill_dir 内（resolve 后用 relative_to 校验）
2. 后缀白名单：仅允许 .py / .sh
3. 参数注入防护：shlex 分割 + shell=False + 禁止空字节
4. 环境变量脱敏：剥离 SECRET / TOKEN / PASSWORD 等敏感变量
5. Python 隔离模式：-I -B 阻止 PYTHONPATH 注入与 .pyc 生成
6. 超时与输出截断：防止死循环 / 日志爆炸
7. 非阻塞：使用 asyncio.create_subprocess_exec 替代 subprocess.run
"""
import asyncio
import os
import shlex
import sys
from pathlib import Path
from typing import List, Optional, Tuple
from backend.bootstrap import logger
from config_loader import config


# ──────────────────────── 安全配置常量 ────────────────────────

ALLOWED_SCRIPT_EXTENSIONS = frozenset({".py", ".sh"})
DEFAULT_TIMEOUT = 60          # 默认超时（秒）
MAX_TIMEOUT = 300             # 最大允许超时（秒）
MAX_OUTPUT_SIZE = 64 * 1024   # 单路输出截断阈值：64 KB
MAX_ARGS_COUNT = 64           # 最大参数个数

# 环境变量名中包含以下关键词时，从子进程环境中剥离
SENSITIVE_ENV_KEYWORDS = (
    "SECRET", "TOKEN", "PASSWORD", "PASSWD", "API_KEY",
    "PRIVATE_KEY", "CREDENTIAL", "AWS_", "DATABASE_URL",
    "REDIS_URL", "MONGO", "JWT_",
)
# 额外强制移除的危险环境变量
DANGEROUS_ENV_KEYS = frozenset({
    "PYTHONPATH", "PYTHONSTARTUP", "PYTHONHOME",
    "LD_PRELOAD", "LD_LIBRARY_PATH",  # Linux 动态链接注入
    "DYLD_INSERT_LIBRARIES",          # macOS 动态链接注入
})


# ──────────────────────── 内部工具函数 ────────────────────────

def _is_sensitive_env_key(key: str) -> bool:
    """判断环境变量名是否含敏感关键词"""
    upper = key.upper()
    return any(kw in upper for kw in SENSITIVE_ENV_KEYWORDS)


def _sanitize_env(env: dict) -> dict:
    """清理环境变量，移除敏感信息和可能被注入的路径变量"""
    safe_env = {}
    for k, v in env.items():
        if k in DANGEROUS_ENV_KEYS:
            continue
        if _is_sensitive_env_key(k):
            continue
        safe_env[k] = v
    return safe_env


def _truncate(text: str, max_size: int = MAX_OUTPUT_SIZE) -> str:
    """截断过长输出，防止日志/返回体爆炸"""
    if len(text) <= max_size:
        return text
    return text[:max_size] + f"\n... [输出已截断，原始 {len(text)} 字符]"


def _validate_script_path(script_path: str) -> Tuple[Optional[Path], Optional[str]]:
    """
    严格校验脚本路径安全性。

    Returns:
        (解析后的绝对路径, 错误信息)  —— 成功时第二项为 None
    """
    # 空值校验
    if not script_path or not script_path.strip():
        return None, "错误：脚本路径不能为空"

    # 空字节注入防护（C 语言层面 path 截断）
    if "\x00" in script_path:
        return None, "错误：脚本路径包含非法字符（空字节）"

    # 解析脚本绝对路径（resolve 会展开符号链接）
    try:
        abs_path = Path(script_path).resolve(strict=False)
    except (OSError, ValueError) as e:
        return None, f"错误：无效的脚本路径格式 — {e}"

    # 解析技能库根目录
    try:
        skill_root = Path(config.skill_dir).resolve()
    except (OSError, ValueError) as e:
        return None, f"错误：技能库根目录配置异常 — {e}"

    # ★ 核心安全校验：脚本必须严格位于技能库目录内部
    try:
        abs_path.relative_to(skill_root)
    except ValueError:
        logger.warning(f"拒绝执行越权脚本: {abs_path} (skill_root={skill_root})")
        return None, "错误：只能执行技能库内的脚本，禁止操作系统文件"

    # 必须是普通文件
    if not abs_path.is_file():
        return None, f"错误：脚本不存在或不是文件 -> {abs_path}"

    # 后缀白名单
    if abs_path.suffix.lower() not in ALLOWED_SCRIPT_EXTENSIONS:
        return None, (
            f"错误：不支持的脚本类型 '{abs_path.suffix}'，"
            f"仅允许 {sorted(ALLOWED_SCRIPT_EXTENSIONS)}"
        )

    return abs_path, None


def _build_command(
    abs_path: Path, args: str
) -> Tuple[List[str], Optional[str]]:
    """
    构建子进程命令列表。

    - .py  → 使用当前解释器 + 隔离模式 (-I -B)
    - .sh  → 直接执行（依赖文件可执行权限）
    - 参数用 shlex.split 安全分割，杜绝 shell 注入
    """
    if abs_path.suffix == ".py":
        # -I: 隔离模式，忽略 PYTHON* 环境变量和用户 site-packages
        # -B: 不生成 .pyc 文件
        cmd: List[str] = [sys.executable, "-I", "-B", str(abs_path)]
    else:
        cmd = [str(abs_path)]

    # 安全分割参数
    if args and args.strip():
        try:
            extra = shlex.split(args)
        except ValueError as e:
            return [], f"错误：参数格式不合法 — {e}"

        if len(extra) > MAX_ARGS_COUNT:
            return [], f"错误：参数数量超限（最多 {MAX_ARGS_COUNT} 个）"

        cmd.extend(a for a in extra if a)  # 过滤空串

    return cmd, None


# ──────────────────────── 对外接口 ────────────────────────

async def execute_script(
    script_path: str,
    args: str = "",
    timeout: Optional[int] = None,
) -> str:
    """
    安全执行技能目录下的脚本。

    Args:
        script_path: 脚本路径，必须在 ``config.skill_dir`` 内。
        args:        传给脚本的命令行参数（空格分隔的字符串）。
        timeout:     超时秒数，默认 60，上限 300。

    Returns:
        人类可读的执行结果字符串。
    """
    # ── 1. 路径校验 ──
    abs_path, err = _validate_script_path(script_path)
    if err:
        return err

    # ── 2. 构建命令 ──
    cmd, err = _build_command(abs_path, args)
    if err:
        return err

    # ── 3. 超时钳制 ──
    exec_timeout = max(1, min(timeout or DEFAULT_TIMEOUT, MAX_TIMEOUT))

    # ── 4. 安全环境 ──
    safe_env = _sanitize_env(os.environ.copy())

    # ── 5. 日志（脱敏：不记录参数原文） ──
    logger.info(
        f"执行脚本: path={abs_path}, type={abs_path.suffix}, "
        f"args_count={len(cmd) - (2 if abs_path.suffix == '.py' else 1)}, "
        f"timeout={exec_timeout}s"
    )

    # ── 6. 执行 ──
    try:
        # asyncio 原生子进程，不阻塞事件循环
        # create_subprocess_exec 内部 shell=False，天然防止命令注入
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=str(abs_path.parent),
            env=safe_env,
            close_fds=True,  # 关闭继承的文件描述符，防泄漏
        )
    except PermissionError:
        logger.warning(f"脚本无执行权限: {abs_path}")
        return f"错误：脚本无执行权限 -> {abs_path.name}"
    except Exception as e:
        logger.exception("创建子进程失败")
        return f"错误：无法启动脚本 — {type(e).__name__}: {e}"

    # ── 7. 等待结果（带超时） ──
    try:
        stdout_bytes, stderr_bytes = await asyncio.wait_for(
            proc.communicate(),
            timeout=exec_timeout,
        )
    except asyncio.TimeoutError:
        # 超时必须杀死进程树
        try:
            proc.kill()
            await proc.wait()
        except ProcessLookupError:
            pass  # 进程已退出
        logger.warning(f"脚本执行超时被终止: {abs_path}")
        return f"错误：脚本执行超时（超过 {exec_timeout} 秒），进程已终止"

    # ── 8. 解码 & 截断 ──
    stdout = (stdout_bytes or b"").decode("utf-8", errors="replace")
    stderr = (stderr_bytes or b"").decode("utf-8", errors="replace")

    # ── 9. 组装返回 ──
    if proc.returncode == 0:
        output = _truncate(stdout.strip())
        if not output:
            return "脚本执行成功（无输出内容）"
        return f"执行成功:\n{output}"
    else:
        parts = [f"执行失败 (退出码 {proc.returncode}):"]
        err_text = _truncate(stderr.strip())
        if err_text:
            parts.append(err_text)
        out_text = _truncate(stdout.strip())
        if out_text:
            parts.append(f"--- stdout ---\n{out_text}")
        if len(parts) == 1:  # 既无 stderr 也无 stdout
            parts.append("(无输出)")
        return "\n".join(parts)
