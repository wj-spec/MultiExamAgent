"""
知识检索工具集

提供知识库检索、文档摘要、集合列表等工具。
支持 Tool Calling 模式，可被 Agent 直接调用。
"""

from typing import List, Optional, Dict, Any
from agents.tools.base import BaseTool, ToolParameter, ToolResult, register_tool
from tools.retriever import get_retriever, KnowledgeBaseRetriever


@register_tool
class SearchKnowledgeTool(BaseTool):
    """
    知识检索工具

    从业务知识库中检索相关知识内容，支持向量检索、BM25检索和混合检索。
    """

    def __init__(self):
        super().__init__()
        self._name = "search_knowledge"
        self._description = (
            "从业务知识库中检索相关知识内容。"
            "用于查找与命题相关的知识点、教材内容、考纲要求等。"
            "当需要获取特定知识点的详细信息时使用此工具。"
        )
        self._parameters = [
            ToolParameter(
                name="query",
                type="string",
                description="检索查询字符串，如知识点名称或相关描述",
                required=True
            ),
            ToolParameter(
                name="top_k",
                type="integer",
                description="返回的最大文档片段数量",
                required=False,
                default=3
            ),
            ToolParameter(
                name="method",
                type="string",
                description="检索方法：vector(向量检索)、bm25(关键词检索)、hybrid(混合检索)",
                required=False,
                default="hybrid",
                enum=["vector", "bm25", "hybrid"]
            )
        ]
        self._retriever: Optional[KnowledgeBaseRetriever] = None

    @property
    def retriever(self) -> KnowledgeBaseRetriever:
        """延迟初始化检索器"""
        if self._retriever is None:
            self._retriever = get_retriever()
        return self._retriever

    def execute(self, query: str, top_k: int = 3, method: str = "hybrid") -> ToolResult:
        """
        执行知识检索

        Args:
            query: 查询字符串
            top_k: 返回数量
            method: 检索方法

        Returns:
            检索结果
        """
        try:
            docs = self.retriever.retrieve(query, top_k, method=method)

            if not docs:
                return ToolResult(
                    success=True,
                    data={"documents": [], "count": 0,
                          "message": f"未找到与 '{query}' 相关的知识内容"},
                    metadata={"query": query, "method": method}
                )

            documents = []
            for doc in docs:
                documents.append({
                    "content": doc.page_content,
                    "source": doc.metadata.get("source", "未知"),
                    "metadata": doc.metadata
                })

            return ToolResult(
                success=True,
                data={
                    "documents": documents,
                    "count": len(documents),
                    "query": query
                },
                metadata={"method": method, "top_k": top_k}
            )

        except Exception as e:
            return ToolResult(
                success=False,
                data=None,
                error=f"知识检索失败: {str(e)}"
            )


@register_tool
class GetDocumentSummaryTool(BaseTool):
    """
    文档摘要工具

    获取知识库中特定文档的摘要信息。
    """

    def __init__(self):
        super().__init__()
        self._name = "get_document_summary"
        self._description = (
            "获取知识库中特定文档的摘要信息。"
            "用于了解某个文档的主要内容概要。"
        )
        self._parameters = [
            ToolParameter(
                name="source",
                type="string",
                description="文档来源名称（文件名）",
                required=True
            )
        ]
        self._retriever: Optional[KnowledgeBaseRetriever] = None

    @property
    def retriever(self) -> KnowledgeBaseRetriever:
        """延迟初始化检索器"""
        if self._retriever is None:
            self._retriever = get_retriever()
        return self._retriever

    def execute(self, source: str) -> ToolResult:
        """
        获取文档摘要

        Args:
            source: 文档来源名称

        Returns:
            文档摘要
        """
        try:
            # 从 BM25 索引中查找文档
            bm25_docs = self.retriever.bm25_retriever.documents
            matching_docs = [
                doc for doc in bm25_docs
                if doc.get("source") == source or source in doc.get("source", "")
            ]

            if not matching_docs:
                return ToolResult(
                    success=True,
                    data={"found": False, "message": f"未找到文档: {source}"},
                    metadata={"source": source}
                )

            # 汇总文档内容
            total_chars = sum(len(doc.get("content", ""))
                              for doc in matching_docs)
            preview = matching_docs[0].get("content", "")[
                :500] if matching_docs else ""

            return ToolResult(
                success=True,
                data={
                    "found": True,
                    "source": source,
                    "chunk_count": len(matching_docs),
                    "total_chars": total_chars,
                    "preview": preview
                },
                metadata={"source": source}
            )

        except Exception as e:
            return ToolResult(
                success=False,
                data=None,
                error=f"获取文档摘要失败: {str(e)}"
            )


@register_tool
class ListCollectionsTool(BaseTool):
    """
    知识库列表工具

    列出知识库中的所有文档和统计信息。
    """

    def __init__(self):
        super().__init__()
        self._name = "list_collections"
        self._description = (
            "列出知识库中的所有文档和统计信息。"
            "用于了解知识库中都有哪些可用的知识资源。"
        )
        self._parameters = []  # 无参数
        self._retriever: Optional[KnowledgeBaseRetriever] = None

    @property
    def retriever(self) -> KnowledgeBaseRetriever:
        """延迟初始化检索器"""
        if self._retriever is None:
            self._retriever = get_retriever()
        return self._retriever

    def execute(self) -> ToolResult:
        """
        列出知识库信息

        Returns:
            知识库统计信息
        """
        try:
            stats = self.retriever.get_stats()

            return ToolResult(
                success=True,
                data={
                    "vector_store_available": stats.get("vector_store_available", False),
                    "document_count": stats.get("document_count", 0),
                    "bm25_document_count": stats.get("bm25_document_count", 0),
                    "source_files": stats.get("source_files", []),
                    "knowledge_dir": stats.get("knowledge_dir", "")
                },
                metadata={}
            )

        except Exception as e:
            return ToolResult(
                success=False,
                data=None,
                error=f"获取知识库信息失败: {str(e)}"
            )


@register_tool
class AddKnowledgeTool(BaseTool):
    """
    添加知识工具

    将新文档添加到知识库中。
    """

    def __init__(self):
        super().__init__()
        self._name = "add_knowledge"
        self._description = (
            "将新文档添加到知识库中。"
            "支持 PDF 和 DOCX 格式的文档。"
            "当需要扩展知识库内容时使用此工具。"
        )
        self._parameters = [
            ToolParameter(
                name="file_path",
                type="string",
                description="文档文件的绝对路径",
                required=True
            )
        ]
        self._retriever: Optional[KnowledgeBaseRetriever] = None

    @property
    def retriever(self) -> KnowledgeBaseRetriever:
        """延迟初始化检索器"""
        if self._retriever is None:
            self._retriever = get_retriever()
        return self._retriever

    def execute(self, file_path: str) -> ToolResult:
        """
        添加文档到知识库

        Args:
            file_path: 文档路径

        Returns:
            添加结果
        """
        import os

        if not os.path.exists(file_path):
            return ToolResult(
                success=False,
                data=None,
                error=f"文件不存在: {file_path}"
            )

        try:
            success = self.retriever.add_documents(file_path)

            if success:
                return ToolResult(
                    success=True,
                    data={
                        "added": True,
                        "file_path": file_path,
                        "message": f"成功添加文档: {os.path.basename(file_path)}"
                    },
                    metadata={"file_path": file_path}
                )
            else:
                return ToolResult(
                    success=False,
                    data={"added": False, "file_path": file_path},
                    error="添加文档失败，请检查文件格式"
                )

        except Exception as e:
            return ToolResult(
                success=False,
                data=None,
                error=f"添加文档失败: {str(e)}"
            )


# 便捷函数：获取知识检索工具列表
def get_knowledge_tools() -> List[BaseTool]:
    """
    获取所有知识检索工具

    Returns:
        工具列表
    """
    from agents.tools.base import registry
    return registry.get_tools([
        "search_knowledge",
        "get_document_summary",
        "list_collections",
        "add_knowledge"
    ])
