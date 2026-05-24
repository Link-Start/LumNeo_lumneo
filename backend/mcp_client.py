# backend/mcp_client.py
import json
import logging
from typing import Dict, List, Any
from fastmcp import Client

logger = logging.getLogger(__name__)


class MCPClientManager:
    """管理多个 MCP 服务器连接（支持 stdio 和 SSE）"""

    def __init__(self):
        self.clients: Dict[str, Client] = {}
        self.tools_cache: Dict[str, List[Dict]] = {}

    # 重写连接方法，利用 infer_transport 自动选择模式
    async def _connect_server(self, name: str, config_dict: dict):
        """支持自动选择 Streamable HTTP 或 SSE 模式的核心连接方法"""
        try:
            client = Client(config_dict)
            await client.__aenter__()
            self.clients[name] = client
            await self._fetch_tools(name, client)
            logger.info(f"MCP 服务器 '{name}' 已连接，工具: {self._tool_names(name)}")
        except Exception as e:
            logger.error(f"服务器 '{name}' 连接失败: {e}")

    async def connect_server_stdio(self, name: str, command: str, args: List[str]):
        """通过 stdio 连接到本地 MCP 服务器"""
        config_dict = {
            "mcpServers": {
                name: {
                    "command": command,
                    "args": args,
                }
            }
        }
        await self._connect_server(name, config_dict)

    async def connect_server_sse(self, name: str, url: str):
        """连接远程 MCP 服务器，支持自动识别 Streamable HTTP 或 SSE"""
        config_dict = {
            "mcpServers": {
                name: {
                    "url": url,
                }
            }
        }
        await self._connect_server(name, config_dict)

    async def _fetch_tools(self, name: str, client: Client):
        """获取并缓存工具列表"""
        tools = await client.list_tools()
        self.tools_cache[name] = [
            {
                "name": tool.name,
                "description": tool.description,
                "input_schema": tool.inputSchema,
            }
            for tool in tools
        ]

    def _tool_names(self, name: str) -> List[str]:
        return [t["name"] for t in self.tools_cache.get(name, [])]

    async def connect_from_config(self, config_path: str = "mcp_config.json"):
        """从 JSON 配置文件加载并连接所有 MCP 服务器"""
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                config = json.load(f)
        except FileNotFoundError:
            logger.warning(f"配置文件 {config_path} 不存在，将使用空配置。")
            # 自动创建默认配置文件
            default_config = {"mcpServers": {}}
            with open(config_path, "w", encoding="utf-8") as f:
                json.dump(default_config, f, indent=2)
            return  # 无需连接任何服务，直接返回

        servers = config.get("mcpServers", {})
        for server_name, server_config in servers.items():
            if "url" in server_config:
                await self.connect_server_sse(server_name, server_config["url"])
            elif "command" in server_config or "commad" in server_config:
                command = server_config.get("command") or server_config.get("commad")
                args = server_config.get("args", [])
                await self.connect_server_stdio(server_name, command, args)
            else:
                logger.warning(f"服务器 '{server_name}' 缺少有效的连接配置（command/url）")

    async def get_all_tools(self) -> List[Dict]:
        """获取所有 MCP 服务器的工具列表，转换为 OpenAI function calling 格式"""
        all_tools = []
        for server_name, tools in self.tools_cache.items():
            for tool in tools:
                all_tools.append({
                    "type": "function",
                    "function": {
                        "name": f"mcp_{server_name}__{tool['name']}",
                        "description": tool["description"],
                        "parameters": tool["input_schema"],
                    }
                })
        return all_tools

    async def call_tool(self, full_name: str, arguments: Dict) -> Any:
        """调用指定工具（全名格式：mcp_<服务名>__<工具名>）"""
        if not full_name.startswith("mcp_"):
            raise ValueError(f"无效的工具调用格式: {full_name}")
        parts = full_name[4:].split("__", 1)
        if len(parts) != 2:
            raise ValueError(f"无法解析工具名: {full_name}")
        server_name, tool_name = parts
        client = self.clients.get(server_name)
        if not client:
            raise ValueError(f"未找到 MCP 服务器 '{server_name}'")
        result = await client.call_tool(tool_name, arguments)
        # 提取文本内容
        if hasattr(result, 'content') and result.content:
            return result.content[0].text
        return str(result)

    async def close_all(self):
        for client in self.clients.values():
            await client.__aexit__(None, None, None)
        self.clients.clear()
        self.tools_cache.clear()