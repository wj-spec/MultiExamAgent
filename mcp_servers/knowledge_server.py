"""
MCP Knowledge Server - IntelliExam 知识库服务

将知识库检索功能封装为标准 MCP Server，
提供知识文件列表和向量检索工具。
"""

import sys
import os
import json

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from mcp.server.fastmcp import FastMCP

mcp = FastMCP("IntelliExam-Knowledge")


# ==================== MCP Resources ====================

@mcp.resource("knowledge://list")
def list_knowledge_files() -> str:
    """列出知识库中所有已导入的文件。

    返回 JSON 格式的文件列表，包含文件名和大小。
    """
    kb_dir = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "data", "knowledge_base"
    )

    files = []
    if os.path.exists(kb_dir):
        for fname in os.listdir(kb_dir):
            fpath = os.path.join(kb_dir, fname)
            if os.path.isfile(fpath):
                files.append({
                    "name": fname,
                    "size_bytes": os.path.getsize(fpath),
                    "ext": os.path.splitext(fname)[1]
                })

    return json.dumps({
        "count": len(files),
        "files": files
    }, ensure_ascii=False, indent=2)


# ==================== MCP Tools ====================

@mcp.tool()
def search_knowledge(query: str, top_k: int = 3) -> str:
    """在知识库中检索与查询相关的知识内容。

    使用向量检索从已导入的文档中查找最相关的知识片段。

    Args:
        query: 检索查询字符串，如知识点名称或问题描述
        top_k: 返回的最大结果数量，默认3条

    Returns:
        检索到的知识内容文本
    """
    from tools.retriever import search_knowledge as _search

    result = _search(query, top_k=top_k)

    if not result or result.strip() == "":
        return json.dumps({
            "message": "未检索到相关知识",
            "content": ""
        }, ensure_ascii=False)

    return json.dumps({
        "message": f"检索到相关知识内容",
        "content": result
    }, ensure_ascii=False)


if __name__ == "__main__":
    mcp.run()
