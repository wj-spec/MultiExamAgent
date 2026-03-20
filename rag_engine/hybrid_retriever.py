"""
智能融合多源检索器 (Hybrid Retriever)

集成多种检索源：
- 本地知识库 (Vector/BM25)
- 网络搜索 (DuckDuckGo/Tavily)
- 深度网页爬取 (Browser Agent)

支持智能路由、多源融合和 Reranker 重排序。
"""

from langchain_core.documents import Document
from tools.retriever import get_retriever
from rag_engine.reranker import BaseReranker, get_reranker_singleton
from rag_engine.browser_agent import BrowserAgent, get_browser_agent
from rag_engine.search_api import UnifiedSearchAPI, get_unified_search
from rag_engine.router import RAGRouter, RouteDecision, get_router
import sys
import os
import logging
from typing import List, Dict, Any, Optional

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


logger = logging.getLogger(__name__)

# 尝试导入 tiktoken 用于 token 计数
try:
    import tiktoken
    TIKTOKEN_AVAILABLE = True
except ImportError:
    TIKTOKEN_AVAILABLE = False
    logger.debug("tiktoken 未安装，使用字符数估算 token")


class ContextTruncator:
    """上下文截断器"""

    def __init__(self, max_tokens: int = 4000, encoding_name: str = "cl100k_base"):
        self.max_tokens = max_tokens
        self.encoding_name = encoding_name
        self._encoding = None

    @property
    def encoding(self):
        """懒加载 tiktoken encoding"""
        if self._encoding is None and TIKTOKEN_AVAILABLE:
            try:
                self._encoding = tiktoken.get_encoding(self.encoding_name)
            except Exception:
                pass
        return self._encoding

    def count_tokens(self, text: str) -> int:
        """计算文本的 token 数量"""
        if self.encoding:
            return len(self.encoding.encode(text))
        else:
            # 降级：使用字符数估算 (中文约 1.5 字符/token，英文约 4 字符/token)
            return len(text) // 2

    def truncate_docs(
        self,
        docs: List[Document],
        max_tokens: int = None
    ) -> List[Document]:
        """
        截断文档列表以适应 token 限制

        Args:
            docs: 文档列表
            max_tokens: 最大 token 数

        Returns:
            截断后的文档列表
        """
        max_tokens = max_tokens or self.max_tokens
        if not docs:
            return []

        truncated_docs = []
        total_tokens = 0

        for doc in docs:
            doc_tokens = self.count_tokens(doc.page_content)
            if total_tokens + doc_tokens <= max_tokens:
                truncated_docs.append(doc)
                total_tokens += doc_tokens
            else:
                # 尝试截断当前文档
                remaining_tokens = max_tokens - total_tokens
                if remaining_tokens > 100:  # 至少保留 100 tokens
                    truncated_content = doc.page_content[:remaining_tokens * 2]
                    truncated_doc = Document(
                        page_content=truncated_content + "\n...[内容已截断]",
                        metadata=doc.metadata
                    )
                    truncated_docs.append(truncated_doc)
                break

        return truncated_docs


class HybridRetriever:
    """
    智能融合多源检索器

    集成意图识别 (Router)、网络快搜 (DuckDuckGo/Tavily)、
    本地 RAG (Vector/BM25)、深度搜刮 (Browser Agent)、
    以及重排序 (Reranker)。
    """

    def __init__(
        self,
        use_reranker: bool = True,
        max_context_tokens: int = 4000
    ):
        """
        初始化多源检索器

        Args:
            use_reranker: 是否使用 Reranker
            max_context_tokens: 最大上下文 token 数
        """
        self.router = get_router()
        self.api_searcher = get_unified_search()
        self.local_retriever = get_retriever()
        self.browser_agent = get_browser_agent()
        self.reranker = get_reranker_singleton() if use_reranker else None
        self.truncator = ContextTruncator(max_tokens=max_context_tokens)

    def smart_retrieve(
        self,
        query: str,
        top_k: int = 4,
        use_rerank: bool = True
    ) -> Dict[str, Any]:
        """
        基于智能路由执行多源检索

        Args:
            query: 用户查询
            top_k: 返回文档数量
            use_rerank: 是否使用 Reranker

        Returns:
            包含检索结果的字典
        """
        # 1. 路由决策
        decision = self.router.route_query(query)
        route_type = decision.route
        search_query = decision.search_query

        logger.info(
            f"[HybridRetriever] 路由决策: {route_type}, Query: {search_query}")

        docs = []
        sources_info = []

        # 2. 根据路由执行检索
        if route_type == "local":
            docs, sources_info = self._retrieve_local(search_query, top_k)

        elif route_type == "api":
            docs, sources_info = self._retrieve_api(search_query, top_k)

        elif route_type == "browser":
            docs, sources_info = self._retrieve_browser(
                search_query,
                decision.target_urls,
                top_k
            )

        elif route_type == "hybrid":
            docs, sources_info = self._retrieve_hybrid(search_query, top_k)

        # 3. Reranker 重排序
        if use_rerank and self.reranker and docs:
            logger.info(f"[HybridRetriever] 执行 Reranker 重排序...")
            docs = self.reranker.rerank(search_query, docs, top_k=top_k)

        # 4. 上下文截断保护
        docs = self.truncator.truncate_docs(docs)

        # 5. 格式化输出
        context_str = self._format_docs(docs)

        return {
            "route_decision": decision.model_dump(),
            "route": route_type,
            "search_query": search_query,
            "docs": docs,
            "context_str": context_str,
            "sources_info": sources_info,
            "doc_count": len(docs)
        }

    def _retrieve_local(
        self,
        query: str,
        top_k: int
    ) -> tuple[List[Document], List[Dict]]:
        """本地知识库检索"""
        logger.info(f"[HybridRetriever] -> 分支[Local]: {query}")
        docs = self.local_retriever.retrieve(
            query, top_k=top_k, method="hybrid")
        sources_info = [{
            "type": "local",
            "count": len(docs),
            "query": query
        }]
        return docs, sources_info

    def _retrieve_api(
        self,
        query: str,
        top_k: int
    ) -> tuple[List[Document], List[Dict]]:
        """API 搜索检索"""
        logger.info(f"[HybridRetriever] -> 分支[API]: {query}")
        docs = self.api_searcher.search(query, max_results=top_k)
        sources_info = [{
            "type": "api",
            "count": len(docs),
            "query": query
        }]
        return docs, sources_info

    def _retrieve_browser(
        self,
        query: str,
        target_urls: List[str],
        top_k: int
    ) -> tuple[List[Document], List[Dict]]:
        """Browser Agent 深度检索"""
        logger.info(f"[HybridRetriever] -> 分支[Browser]: {query}")

        docs = []
        sources_info = []

        if target_urls:
            # 访问指定的 URL
            for url in target_urls[:3]:  # 最多访问 3 个 URL
                try:
                    url_docs = self.browser_agent.browse_url(url, query)
                    docs.extend(url_docs)
                    sources_info.append({
                        "type": "browser",
                        "url": url,
                        "count": len(url_docs)
                    })
                except Exception as e:
                    logger.warning(
                        f"[HybridRetriever] Browser Agent 访问 {url} 失败: {e}")
        else:
            # 没有指定 URL，降级到 API 搜索
            logger.info("[HybridRetriever] 无目标 URL，降级到 API 搜索")
            docs = self.api_searcher.search(query, max_results=top_k)
            sources_info.append({
                "type": "api_fallback",
                "count": len(docs),
                "query": query
            })

        return docs[:top_k], sources_info

    def _retrieve_hybrid(
        self,
        query: str,
        top_k: int
    ) -> tuple[List[Document], List[Dict]]:
        """混合检索：本地 + API"""
        logger.info(f"[HybridRetriever] -> 分支[Hybrid]: {query}")

        # 并行检索 (简化版，实际可以用 asyncio)
        local_docs = self.local_retriever.retrieve(
            query, top_k=top_k, method="hybrid")
        api_docs = self.api_searcher.search(query, max_results=top_k)

        # 合并策略：本地取前 top_k//2 + 1，API 取前 top_k//2
        local_count = top_k // 2 + 1
        api_count = top_k // 2

        docs = local_docs[:local_count] + api_docs[:api_count]

        sources_info = [
            {"type": "local", "count": len(
                local_docs[:local_count]), "query": query},
            {"type": "api", "count": len(api_docs[:api_count]), "query": query}
        ]

        return docs, sources_info

    def _format_docs(self, docs: List[Document]) -> str:
        """
        格式化供 LLM 阅读的统一上下文块

        区分不同来源，添加可信度指示
        """
        if not docs:
            return "（无检索结果信息）"

        res = []
        for i, doc in enumerate(docs, 1):
            source = doc.metadata.get("source", "未知来源")
            title = doc.metadata.get("title", "")
            doc_type = doc.metadata.get("type", "local_file")
            search_engine = doc.metadata.get("search_engine", "")
            rerank_score = doc.metadata.get("rerank_score", None)

            # 根据来源类型添加标签
            if doc_type == "api_search":
                engine_tag = f"[{search_engine}]" if search_engine else ""
                tag = f"【网络搜索{engine_tag}】"
                credibility = "时效性高，需核实准确性"
            elif doc_type == "browser_agent":
                tag = "【深度网页提取】"
                credibility = "来源具体，可信度较高"
            else:
                tag = "【本地学术知识】"
                credibility = "教学大纲内容，权威可信"

            # 构建内容块
            content_lines = [f"{tag}[{i}]"]
            if title:
                content_lines.append(f"标题: {title}")
            content_lines.append(f"来源: {source}")
            content_lines.append(f"可信度: {credibility}")
            if rerank_score is not None:
                content_lines.append(f"相关性: {rerank_score:.3f}")
            content_lines.append(f"\n内容:\n{doc.page_content}")

            res.append("\n".join(content_lines))

        return "\n\n" + "=" * 40 + "\n\n".join(res)

    def retrieve_for_topic(
        self,
        topic: str,
        additional_context: str = "",
        top_k: int = 4
    ) -> str:
        """
        为特定主题检索上下文 (便捷方法)

        Args:
            topic: 知识点主题
            additional_context: 额外上下文 (如时事要求)
            top_k: 返回文档数

        Returns:
            格式化的上下文字符串
        """
        query = f"{topic} {additional_context}".strip()
        result = self.smart_retrieve(query, top_k=top_k)
        return result["context_str"]


# 单例
_hybrid_retriever_instance = None


def get_hybrid_retriever(
    use_reranker: bool = True,
    max_context_tokens: int = 4000
) -> HybridRetriever:
    """获取多源检索器实例（单例）"""
    global _hybrid_retriever_instance
    if _hybrid_retriever_instance is None:
        _hybrid_retriever_instance = HybridRetriever(
            use_reranker=use_reranker,
            max_context_tokens=max_context_tokens
        )
    return _hybrid_retriever_instance


if __name__ == "__main__":
    from dotenv import load_dotenv
    load_dotenv()
    logging.basicConfig(level=logging.INFO)

    retriever = HybridRetriever()

    print("=" * 60)
    print("场景测试1: 纯本地知识库出题")
    print("=" * 60)
    res1 = retriever.smart_retrieve("请出三道关于牛顿第二定律的初中版选择题。")
    print(f"路由: {res1['route']}")
    print(f"文档数: {res1['doc_count']}")
    print(res1["context_str"][:500])

    print("\n" + "=" * 60)
    print("场景测试2: 时事造题")
    print("=" * 60)
    res2 = retriever.smart_retrieve("以最新的诺贝尔物理学奖为题材，出一道相关的推断题。")
    print(f"路由: {res2['route']}")
    print(f"文档数: {res2['doc_count']}")
    print(res2["context_str"][:500])
