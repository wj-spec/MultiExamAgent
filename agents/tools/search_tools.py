"""
搜索工具集 - 支持互联网检索和浏览器访问

共享工具，基础模式和专业模式均可调用。
"""

from typing import List, Optional, Dict, Any
from agents.tools.base import BaseTool, ToolParameter, ToolResult, register_tool
import logging

logger = logging.getLogger(__name__)


@register_tool
class SearchInternetTool(BaseTool):
    """
    互联网搜索工具

    使用 DuckDuckGo 或 Tavily 搜索互联网获取最新信息。
    """

    def __init__(self):
        super().__init__()
        self._name = "search_internet"
        self._description = (
            "搜索互联网获取最新信息。"
            "当用户询问实时新闻、最新数据、当前事件等需要最新信息的问题时使用。"
            "也可以用于查找教材资料、考试资讯等。"
        )
        self._parameters = [
            ToolParameter(
                name="query",
                type="string",
                description="搜索查询关键词",
                required=True
            ),
            ToolParameter(
                name="max_results",
                type="integer",
                description="最大返回结果数",
                required=False,
                default=5
            )
        ]
        self._searcher = None

    @property
    def searcher(self):
        """延迟初始化搜索器"""
        if self._searcher is None:
            from rag_engine.search_api import get_unified_search
            self._searcher = get_unified_search()
        return self._searcher

    def execute(self, query: str, max_results: int = 5) -> ToolResult:
        """
        执行互联网搜索

        Args:
            query: 搜索关键词
            max_results: 最大结果数

        Returns:
            搜索结果
        """
        try:
            logger.info(f"[SearchInternet] 正在搜索: {query}")
            docs = self.searcher.search(query, max_results)

            if not docs:
                return ToolResult(
                    success=True,
                    data={
                        "results": [],
                        "count": 0,
                        "message": f"未找到与 '{query}' 相关的信息"
                    }
                )

            results = []
            for doc in docs:
                results.append({
                    "title": doc.metadata.get("title", "未知标题"),
                    "source": doc.metadata.get("source", ""),
                    "snippet": doc.page_content[:500],
                    "search_engine": doc.metadata.get("search_engine", "unknown")
                })

            logger.info(f"[SearchInternet] 搜索完成，返回 {len(results)} 条结果")

            return ToolResult(
                success=True,
                data={
                    "results": results,
                    "count": len(results),
                    "query": query
                }
            )

        except Exception as e:
            logger.error(f"[SearchInternet] 搜索失败: {e}")
            return ToolResult(
                success=False,
                error=f"搜索失败: {str(e)}"
            )


@register_tool
class BrowseWebTool(BaseTool):
    """
    网页浏览工具

    访问指定URL获取详细内容，支持智能内容提取。
    """

    def __init__(self):
        super().__init__()
        self._name = "browse_web"
        self._description = (
            "访问指定网页URL获取详细内容。"
            "当搜索结果不够详细，或者用户提供了具体网址时使用。"
            "支持智能提取页面主要内容，过滤广告和无关信息。"
        )
        self._parameters = [
            ToolParameter(
                name="url",
                type="string",
                description="目标网页URL",
                required=True
            ),
            ToolParameter(
                name="task",
                type="string",
                description="要提取的内容描述，如'提取试题内容'、'获取教材信息'",
                required=False,
                default="提取页面主要内容"
            )
        ]
        self._browser_agent = None

    @property
    def browser_agent(self):
        """延迟初始化浏览器代理"""
        if self._browser_agent is None:
            from rag_engine.browser_agent import get_browser_agent
            self._browser_agent = get_browser_agent()
        return self._browser_agent

    def execute(self, url: str, task: str = "提取页面主要内容") -> ToolResult:
        """
        执行网页浏览

        Args:
            url: 目标URL
            task: 提取任务描述

        Returns:
            页面内容
        """
        try:
            logger.info(f"[BrowseWeb] 正在访问: {url}")
            docs = self.browser_agent.browse_url(url, task)

            if not docs:
                return ToolResult(
                    success=True,
                    data={
                        "url": url,
                        "content": "",
                        "message": "页面内容提取失败，可能是网站限制了访问"
                    }
                )

            doc = docs[0]
            content = doc.page_content

            logger.info(f"[BrowseWeb] 内容提取完成，长度: {len(content)}")

            return ToolResult(
                success=True,
                data={
                    "url": url,
                    "title": doc.metadata.get("title", ""),
                    "content": content[:5000],  # 限制长度
                    "extraction_method": doc.metadata.get("extraction_method", "unknown"),
                    "timestamp": doc.metadata.get("timestamp", "")
                }
            )

        except Exception as e:
            logger.error(f"[BrowseWeb] 访问失败: {e}")
            return ToolResult(
                success=False,
                error=f"网页访问失败: {str(e)}"
            )


@register_tool
class MultiSearchTool(BaseTool):
    """
    多源搜索工具

    同时使用互联网搜索和知识库检索，综合返回结果。
    """

    def __init__(self):
        super().__init__()
        self._name = "multi_search"
        self._description = (
            "同时搜索互联网和本地知识库，综合返回最相关的结果。"
            "适用于需要全面信息的查询，如命题时需要参考资料。"
        )
        self._parameters = [
            ToolParameter(
                name="query",
                type="string",
                description="搜索查询",
                required=True
            ),
            ToolParameter(
                name="include_internet",
                type="boolean",
                description="是否包含互联网搜索",
                required=False,
                default=True
            ),
            ToolParameter(
                name="include_knowledge_base",
                type="boolean",
                description="是否包含知识库检索",
                required=False,
                default=True
            )
        ]

    def execute(
        self,
        query: str,
        include_internet: bool = True,
        include_knowledge_base: bool = True
    ) -> ToolResult:
        """
        执行多源搜索

        Args:
            query: 搜索查询
            include_internet: 是否包含互联网
            include_knowledge_base: 是否包含知识库

        Returns:
            综合搜索结果
        """
        results = {
            "query": query,
            "internet_results": [],
            "knowledge_base_results": [],
            "total_count": 0
        }

        try:
            # 互联网搜索
            if include_internet:
                internet_tool = SearchInternetTool()
                internet_result = internet_tool.execute(query, max_results=3)
                if internet_result.success:
                    results["internet_results"] = internet_result.data.get(
                        "results", [])

            # 知识库检索
            if include_knowledge_base:
                try:
                    from agents.tools.knowledge_tools import SearchKnowledgeTool
                    kb_tool = SearchKnowledgeTool()
                    kb_result = kb_tool.execute(query, top_k=3)
                    if kb_result.success:
                        results["knowledge_base_results"] = kb_result.data.get(
                            "documents", [])
                except Exception as e:
                    logger.warning(f"[MultiSearch] 知识库检索失败: {e}")

            results["total_count"] = len(
                results["internet_results"]) + len(results["knowledge_base_results"])

            return ToolResult(
                success=True,
                data=results
            )

        except Exception as e:
            logger.error(f"[MultiSearch] 搜索失败: {e}")
            return ToolResult(
                success=False,
                error=f"多源搜索失败: {str(e)}"
            )


def get_search_tools() -> List[BaseTool]:
    """
    获取所有搜索工具

    Returns:
        搜索工具列表
    """
    from agents.tools.base import registry
    return registry.get_tools([
        "search_internet",
        "browse_web",
        "multi_search"
    ])
