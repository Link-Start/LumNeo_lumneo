# src/lumneo/runtime/tools/registry.py
# 工具注册表
# 负责从 tools_config.yaml 加载工具定义并动态装载实现函数。工具实现位于
# runtime/tools/system/* 与 MCP（runtime/mcp）。本模块只做“定义 + 装载”，
# 不承载执行细节（执行见 runtime/tools/execution）。
import importlib
import json
import yaml
from typing import Dict

from lumneo.kernel.config.app_config import config
from lumneo.kernel.common.logger import logger


def load_tools_from_config(config_path: str):
    full_path = config.resource_path(config_path)
    with open(full_path, "r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f)

    tools_definition = []
    available_tools = {}

    for tool_cfg in cfg["tools"]:
        tools_definition.append({
            "type": "function",
            "function": {
                "name": tool_cfg["name"],
                "title": tool_cfg.get("title", ""),
                "description": tool_cfg["description"],
                "parameters": tool_cfg["parameters"],
                "meta": tool_cfg.get("meta", {}),
            },
        })
        module = importlib.import_module(tool_cfg["module"])
        func = getattr(module, tool_cfg["function_name"])
        available_tools[tool_cfg["name"]] = func

    return tools_definition, available_tools


def is_dangerous_tool(func_name: str) -> bool:
    for tool in TOOLS_DEFINITION:
        fn = tool.get("function", {})
        if fn.get("name") == func_name:
            return fn.get("meta", {}).get("dangerous", False)
    return False


# 模块装载时读取配置（配置缺失时退化为空，避免启动崩溃）。
try:
    TOOLS_DEFINITION, AVAILABLE_TOOLS = load_tools_from_config("tools_config.yaml")
except Exception:
    logger.error("Error: 无法加载工具配置文件，工具功能将不可用")
    TOOLS_DEFINITION, AVAILABLE_TOOLS = [], {}


def get_local_tools():
    """获取本地工具定义副本。"""
    return [dict(t) for t in TOOLS_DEFINITION]


async def get_all_tools(mcp_manager=None):
    """获取所有工具（本地 + MCP）。"""
    tools = [dict(t) for t in TOOLS_DEFINITION]
    if mcp_manager:
        mcp_tools = await mcp_manager.get_all_tools()
        tools.extend(mcp_tools)
    clean_tools = [t for t in tools if isinstance(t, dict)]
    return clean_tools


async def get_mcp_tools(mcp_manager=None):
    """获取 MCP 工具。"""
    mcp_tools = []
    if mcp_manager:
        mcp_tools = await mcp_manager.get_all_tools()
    return [t for t in mcp_tools if isinstance(t, dict)]


async def execute_tool(func_name: str, arguments: Dict, mcp_manager=None) -> str:
    """执行工具，优先本地工具，其次 MCP 工具。"""
    if func_name in AVAILABLE_TOOLS:
        result = await AVAILABLE_TOOLS[func_name](**arguments)
        if not isinstance(result, str):
            try:
                result = json.dumps(result, ensure_ascii=False)
            except Exception:
                result = str(result)
        return result
    elif mcp_manager:
        result = await mcp_manager.call_tool(func_name, arguments)
        if not isinstance(result, str):
            try:
                result = json.dumps(result, ensure_ascii=False)
            except Exception:
                result = str(result)
        return result
    else:
        return f"Error: 工具 {func_name} 未找到"
