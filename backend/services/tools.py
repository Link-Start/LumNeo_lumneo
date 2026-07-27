# backend/services/tools.py
import json
import importlib
import yaml
from typing import Dict
from backend.utils.base import resource_path


def load_tools_from_config(config_path: str):
    full_path = resource_path(config_path)
    with open(full_path, 'r', encoding="utf-8") as f:
        config = yaml.safe_load(f)

    tools_definition = []
    available_tools = {}

    for tool_cfg in config['tools']:
        # 构建工具定义
        tools_definition.append({
            "type": "function",
            "function": {
                "name": tool_cfg['name'],
                "title": tool_cfg['title'],
                "description": tool_cfg['description'],
                "parameters": tool_cfg['parameters'],
                "meta": tool_cfg.get('meta', {})
            }
        })
        # 动态导入函数
        module = importlib.import_module(tool_cfg['module'])
        func = getattr(module, tool_cfg['function_name'])
        available_tools[tool_cfg['name']] = func

    return tools_definition, available_tools

def is_dangerous_tool(func_name: str) -> bool:
    for tool in TOOLS_DEFINITION:
        fn = tool.get("function", {})
        if fn.get("name") == func_name:
            return fn.get("meta", {}).get("dangerous", False)
    return False


TOOLS_DEFINITION, AVAILABLE_TOOLS = load_tools_from_config("tools_config.yaml")

def get_local_tools():
    """获取本地工具"""
    return TOOLS_DEFINITION.copy()

async def get_all_tools(mcp_manager=None):
    """获取所有工具（本地 + MCP）"""
    tools = TOOLS_DEFINITION.copy()
    if mcp_manager:
        mcp_tools = await mcp_manager.get_all_tools()
        tools.extend(mcp_tools)
     # 过滤掉非字典项（防止意外混入对象）
    clean_tools = [t for t in tools if isinstance(t, dict)]

    return clean_tools

async def get_mcp_tools(mcp_manager=None):
    """获取MCP工具"""
    mcp_tools = []
    if mcp_manager:
        mcp_tools = await mcp_manager.get_all_tools()
    # 过滤掉非字典项（防止意外混入对象）
    clean_tools = [t for t in mcp_tools if isinstance(t, dict)]

    return clean_tools

async def execute_tool(func_name: str, arguments: Dict, mcp_manager=None) -> str:
    """执行工具，优先本地工具，其次 MCP 工具"""
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