"""
MCP 客户端管理器

负责启动 MCP Server 子进程，并通过 langchain-mcp-adapters
将 MCP Tools 转为 LangChain Tools 供 Agent 使用。
"""

import os
import sys
import asyncio
import logging
from typing import List, Optional, Dict, Any

logger = logging.getLogger(__name__)

# MCP Server 配置
MCP_SERVERS = {
    "memory": {
        "module": "mcp_servers.memory_server",
        "name": "IntelliExam-Memory",
        "description": "记忆库 MCP 服务"
    },
    "knowledge": {
        "module": "mcp_servers.knowledge_server",
        "name": "IntelliExam-Knowledge",
        "description": "知识库 MCP 服务"
    }
}


class MCPClientManager:
    """
    MCP 客户端管理器

    管理 MCP Server 的生命周期，提供将 MCP Tools
    转换为 LangChain Tools 的接口。
    """

    def __init__(self):
        self._sessions: Dict[str, Any] = {}
        self._tools_cache: Dict[str, list] = {}
        self._initialized = False

    async def initialize(self):
        """初始化所有 MCP Server 连接"""
        if self._initialized:
            return

        try:
            from langchain_mcp_adapters.client import MultiServerMCPClient

            project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            python_exe = sys.executable

            # 构建 MCP 服务器配置
            server_configs = {}
            for server_id, config in MCP_SERVERS.items():
                server_configs[config["name"]] = {
                    "command": python_exe,
                    "args": ["-m", config["module"]],
                    "cwd": project_root,
                    "transport": "stdio"
                }

            self._client = MultiServerMCPClient(server_configs)
            self._initialized = True
            logger.info("MCP 客户端管理器初始化完成")

        except ImportError:
            logger.warning("langchain-mcp-adapters 未安装，MCP 功能不可用")
            self._initialized = False
        except Exception as e:
            logger.error(f"MCP 客户端初始化失败: {e}")
            self._initialized = False

    async def get_tools(self, server_name: str = None) -> list:
        """
        获取 MCP Tools（已转为 LangChain Tool 格式）

        Args:
            server_name: 可选，指定服务器名称，为 None 则返回所有

        Returns:
            LangChain Tool 列表
        """
        if not self._initialized:
            await self.initialize()

        if not self._initialized:
            return []

        try:
            async with self._client as client:
                tools = client.get_tools()
                if server_name:
                    # 按服务器过滤（通过工具名称前缀）
                    tools = [t for t in tools if server_name.lower() in t.name.lower()]
                return tools
        except Exception as e:
            logger.error(f"获取 MCP Tools 失败: {e}")
            return []

    def get_status(self) -> Dict[str, Any]:
        """获取 MCP 服务状态"""
        server_statuses = {}
        for server_id, config in MCP_SERVERS.items():
            server_statuses[server_id] = {
                "name": config["name"],
                "description": config["description"],
                "module": config["module"],
                "initialized": self._initialized
            }

        return {
            "initialized": self._initialized,
            "servers": server_statuses
        }

    async def shutdown(self):
        """关闭所有 MCP 连接"""
        self._initialized = False
        self._tools_cache.clear()
        logger.info("MCP 客户端管理器已关闭")


# 全局单例
_mcp_client: Optional[MCPClientManager] = None


def get_mcp_client() -> MCPClientManager:
    """获取全局 MCP 客户端实例"""
    global _mcp_client
    if _mcp_client is None:
        _mcp_client = MCPClientManager()
    return _mcp_client
