# backend/system_tools/creator.py
"""
从目录结构文本创建项目目录
"""
import os
import re
import asyncio
from pathlib import Path
from collections import Counter
from config_loader import config
import backend
from backend.utils.validators import validate_path
from backend.bootstrap import logger


class TreeParser:
    """解析目录树文本，生成创建指令"""
    def __init__(self, text):
        self.text = text.strip()
        self.instructions = []  # [(type, path), ...]  type: "dir" | "file"
    def parse(self):
        """解析文本，识别目录和文件"""
        lines = self.text.split("\n")
        # 检测 Markdown 代码块并去除标记 (使用显式切片更安全)
        if self._is_markdown_codeblock(lines):
            if lines and lines[0].strip().startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].strip().startswith("```"):
                lines = lines[:-1]
        # 根据格式选择解析方式
        if self._is_tree_format(lines):
            self._parse_tree_format(lines)
        else:
            self._parse_simple_format(lines)
        return self.instructions
    def _is_tree_format(self, lines):
        """检测是否是 tree 格式（包含 ├── └── │ 等符号）"""
        for line in lines[:10]:
            if any(c in line for c in ["├──", "└──", "│"]):
                return True
        return False
    def _is_markdown_codeblock(self, lines):
        """检测是否被 Markdown 代码块包裹（首行和末行都是 ```）"""
        if len(lines) < 2:
            return False
        first = lines[0].strip()
        last = lines[-1].strip()
        return first.startswith("```") and last.startswith("```")
    def _clean_name(self, name):
        """清理名称，去除行尾注释（两个以上空格或制表符后跟 # 的内容）"""
        name = re.sub(r'[ \t]{2,}#.*$', '', name)
        name = name.strip()
        return name
    def _detect_indent_width(self, lines):
        """检测简单缩进格式的缩进宽度，通过统计众数提高准确率"""
        indents = []
        for line in lines:
            stripped = line.lstrip()
            if not stripped or stripped.startswith('#'):
                continue
            indent = len(line) - len(stripped)
            if indent > 0:
                indents.append(indent)
        if not indents:
            return 4  # 默认
        # 取出现次数最多的缩进值
        return Counter(indents).most_common(1)[0][0]
    def _add_instruction(self, name, indent, path_stack, root_name):
        """统一的栈维护和指令添加逻辑"""
        while path_stack and path_stack[-1][1] >= indent:
            path_stack.pop()
        parent_path = path_stack[-1][0] if path_stack else ""
        if not parent_path and root_name:
            parent_path = root_name
        is_dir = name.endswith("/")
        name_clean = name.rstrip("/")
        full_path = os.path.join(parent_path, name_clean) if parent_path else name_clean
        if is_dir:
            self.instructions.append(("dir", full_path))
            path_stack.append((full_path, indent))
        else:
            self.instructions.append(("file", full_path))
    def _parse_tree_format(self, lines):
        """解析 tree 格式"""
        path_stack = [("", -1)]
        root_name = None
        root_detected = False
        for line in lines:
            if not line.strip():
                continue
            stripped = line.strip()
            if not stripped.replace("│", "").replace(" ", ""):
                continue
            if not root_detected:
                root_detected = True
                if not any(c in line for c in ["├──", "└──", "│"]):
                    if stripped.endswith("/"):
                        root_name = self._clean_name(stripped).rstrip("/")
                        path_stack = [(root_name, -1)]
                        continue
            if not any(c in line for c in ["├──", "└──", "│"]):
                continue
            processed = line.replace("├── ", "    ").replace("└── ", "    ")
            processed = processed.replace("│   ", "    ")
            processed = processed.replace("│", " ")
            indent = 0
            temp = processed
            while temp.startswith("    "):
                indent += 1
                temp = temp[4:]
            name = self._clean_name(temp)
            if not name:
                continue
            self._add_instruction(name, indent, path_stack, root_name)
    def _parse_simple_format(self, lines):
        """解析简单缩进格式（自动检测缩进宽度）"""
        indent_width = self._detect_indent_width(lines)
        path_stack = [("", -1)]
        for line in lines:
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue
            processed = line.expandtabs(indent_width)
            indent = 0
            temp = processed
            while temp.startswith(" " * indent_width):
                indent += 1
                temp = temp[indent_width:]
            name = self._clean_name(temp)
            if not name:
                continue
            self._add_instruction(name, indent, path_stack, None)
class ProjectCreator:
    """根据解析结果创建目录和文件"""
    def __init__(self, instructions, base_path=".", dry_run=False, verbose=False):
        self.instructions = instructions
        self.base_path = os.path.abspath(base_path)
        self.dry_run = dry_run
        self.verbose = verbose
        self.created_dirs = 0
        self.created_files = 0
        self.errors = []
        self.log_messages = []
    def create(self):
        """执行创建"""
        base_path = self.base_path
        for inst_type, rel_path in self.instructions:
            full_path = os.path.abspath(os.path.join(base_path, rel_path))
            try:
                if os.path.commonpath([base_path, full_path]) != base_path:
                    err_msg = f"❌ 非法路径被拒绝: {rel_path}"
                    self.errors.append(err_msg)
                    self._log(err_msg)
                    continue
            except ValueError:
                err_msg = f"❌ 非法路径被拒绝: {rel_path}"
                self.errors.append(err_msg)
                self._log(err_msg)
                continue
            try:
                if inst_type == "dir":
                    if not os.path.exists(full_path):
                        if self.dry_run:
                            self._log(f"[DRY RUN] 创建目录: {rel_path}")
                        else:
                            os.makedirs(full_path, exist_ok=True)
                            self._log(f"📁 创建目录: {rel_path}")
                        self.created_dirs += 1
                    else:
                        self._log(f"⏭  已存在: {rel_path}")
                elif inst_type == "file":
                    if not os.path.exists(full_path):
                        if self.dry_run:
                            self._log(f"[DRY RUN] 创建文件: {rel_path}")
                        else:
                            os.makedirs(os.path.dirname(full_path), exist_ok=True)
                            with open(full_path, "w", encoding="utf-8") as f:
                                pass 
                            self._log(f"📄 创建文件: {rel_path}")
                        self.created_files += 1
                    else:
                        self._log(f"⏭  已存在: {rel_path}")
            except Exception as e:
                error_msg = f"❌ 创建失败 {rel_path}: {e}"
                self.errors.append(error_msg)
                self._log(error_msg)
    def _log(self, msg):
        self.log_messages.append(msg)
        if self.verbose:
            logger.info(msg)
    def summary(self):
        """收集总结信息"""
        lines = [
            f"\n{'='*60}",
            "📊 创建完成！",
            f"   目录: {self.created_dirs} 个",
            f"   文件: {self.created_files} 个",
            f"   错误: {len(self.errors)} 个",
            f"   路径: {self.base_path}",
        ]
        if self.dry_run:
            lines.append("   ⚠️  这是试运行，没有实际创建任何文件")
        lines.append(f"{'='*60}")
        summary_text = "\n".join(lines)
        self.log_messages.append(summary_text)
        if self.verbose:
            logger.info(summary_text)
        return summary_text
# ============================================================
# 主入口（给大模型/异步框架调用）
# ============================================================
def _sync_create_project_tree(tree: str, path: str, dry_run: bool = False, verbose: bool = False) -> dict:
    """同步执行创建逻辑，供异步函数包装调用"""
    workspace = getattr(backend, "workspace_path", None)
    paths = [config.uploads_dir] + ([workspace] if workspace else [])
    allowed_dirs = [Path(p).resolve() for p in paths if p]
    def make_response(success, message, created_dirs=0, created_files=0, errors=None, logs=None):
        return {
            "success": success,
            "message": message,
            "created_dirs": created_dirs,
            "created_files": created_files,
            "errors": errors or [],
            "logs": logs or []
        }
    try:
        safe_path = validate_path(path, allowed_dirs)
    except ValueError as e:
        return make_response(False, f"路径校验失败：{e}", errors=[str(e)])
    parser_obj = TreeParser(tree)
    instructions = parser_obj.parse()
    if not instructions:
        return make_response(False, "未能解析出任何目录或文件，请检查输入格式", errors=["解析结果为空"])
    creator = ProjectCreator(
        instructions=instructions,
        base_path=safe_path,
        dry_run=dry_run,
        verbose=verbose
    )
    try:
        creator.create()
        creator.summary()
    except Exception as e:
        return make_response(
            False, 
            f"项目创建过程中发生异常：{e}", 
            created_dirs=creator.created_dirs,
            created_files=creator.created_files,
            errors=creator.errors + [str(e)],
            logs=creator.log_messages
        )
    if creator.errors:
        return make_response(
            False, 
            "部分项目创建失败，详见 errors 字段", 
            created_dirs=creator.created_dirs,
            created_files=creator.created_files,
            errors=creator.errors,
            logs=creator.log_messages
        )
    return make_response(
        True, 
        f"项目创建成功，路径：{safe_path}", 
        created_dirs=creator.created_dirs,
        created_files=creator.created_files,
        logs=creator.log_messages
    )
async def create_project_tree(tree: str, path: str, dry_run: bool = False, verbose: bool = False) -> dict:
    """
    项目创建，解析目录结构文本，自动创建对应的目录和文件
    支持的格式:
        - tree 命令输出（含 ├── └── │ 符号）
        - Markdown 代码块中的目录树
        - 简单缩进格式（自动检测缩进宽度，支持 2/4 空格或制表符）
    Args:
        tree: 目录树文本
        path: 目标文件路径（相对或绝对路径）
        dry_run: 试运行模式，不实际创建文件
        verbose: 打印详细日志
    Returns:
        dict: 统一返回结构，包含 success, message, created_dirs, created_files, errors, logs
    """
    # 将耗时的同步文件IO操作放入线程池执行，防止阻塞异步事件循环
    return await asyncio.to_thread(
        _sync_create_project_tree, 
        tree, 
        path, 
        dry_run, 
        verbose
    )