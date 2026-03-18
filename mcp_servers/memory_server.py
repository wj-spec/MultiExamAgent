"""
MCP Memory Server - IntelliExam 记忆服务

将 long_term_memory.json 封装为标准 MCP Server，
提供资源读取和工具调用两种访问方式。

通过 stdio 传输协议运行，可被 MCP 客户端连接。
"""

import sys
import os
import json

# 确保项目根目录在 Python 路径中
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from mcp.server.fastmcp import FastMCP

# 初始化 MCP Server
mcp = FastMCP("IntelliExam-Memory")

# ==================== 工具函数 ====================

def _get_memory_manager():
    """延迟导入，避免循环依赖"""
    from utils.memory_manager import get_memory_manager
    return get_memory_manager()


# ==================== MCP Resources ====================

@mcp.resource("memory://preferences")
def get_user_preferences() -> str:
    """获取用户的长期记忆偏好 (MCP Resource)

    返回 JSON 格式的用户偏好记忆列表。
    """
    manager = _get_memory_manager()
    preferences = manager.get_all_memories(memory_type="user_preference", limit=20)
    return json.dumps(preferences, ensure_ascii=False, indent=2)


@mcp.resource("memory://all")
def get_all_memories() -> str:
    """获取全部长期记忆 (MCP Resource)

    返回 JSON 格式的完整记忆列表（最多100条）。
    """
    manager = _get_memory_manager()
    memories = manager.get_all_memories(limit=100)
    return json.dumps(memories, ensure_ascii=False, indent=2)


@mcp.resource("memory://stats")
def get_memory_stats() -> str:
    """获取记忆库统计信息 (MCP Resource)

    返回记忆总数、类型分布等统计数据。
    """
    manager = _get_memory_manager()
    stats = manager.get_statistics()
    return json.dumps(stats, ensure_ascii=False, indent=2)


# ==================== MCP Tools ====================

@mcp.tool()
def search_memory(query: str, top_k: int = 5) -> str:
    """检索与查询相关的历史记忆。

    使用 BM25 算法在记忆库中搜索最相关的记忆项。

    Args:
        query: 检索查询字符串，可以是关键词或描述性语句
        top_k: 返回的最大记忆数量，默认5条

    Returns:
        JSON 格式的相关记忆列表
    """
    manager = _get_memory_manager()
    memories = manager.retrieve_memory(query, top_k=top_k)

    if not memories:
        return json.dumps({"message": "未找到相关记忆", "results": []}, ensure_ascii=False)

    return json.dumps({
        "message": f"检索到 {len(memories)} 条相关记忆",
        "results": memories
    }, ensure_ascii=False, indent=2)


@mcp.tool()
def save_preference(content: str) -> str:
    """保存新的用户偏好到长期记忆中。

    当用户明确表达喜欢或不喜欢某种题型、难度或知识点时调用此工具。

    Args:
        content: 用户偏好的描述内容

    Returns:
        保存结果确认
    """
    manager = _get_memory_manager()
    memory = manager.save_memory(
        content=content,
        memory_type="user_preference",
        metadata={"source": "mcp_tool"}
    )
    return json.dumps({
        "message": "偏好已保存",
        "memory_id": memory["id"]
    }, ensure_ascii=False)


@mcp.tool()
def save_experience(content: str, metadata: dict = None) -> str:
    """保存任务经验到长期记忆中。

    在完成试题生成任务后，记录成功的经验或需要改进的地方。

    Args:
        content: 经验内容描述
        metadata: 可选的元数据（如评分、知识点等）

    Returns:
        保存结果确认
    """
    manager = _get_memory_manager()
    memory = manager.save_memory(
        content=content,
        memory_type="task_experience",
        metadata=metadata or {"source": "mcp_tool"}
    )
    return json.dumps({
        "message": "经验已保存",
        "memory_id": memory["id"]
    }, ensure_ascii=False)


# ==================== 入口 ====================

if __name__ == "__main__":
    mcp.run()
