"""
多源搜索引擎 API 封装

支持 DuckDuckGo 和 Tavily 两种搜索源，统一返回标准 Document 格式。
"""

from utils.config import get_tavily_config
from langchain_core.documents import Document
import os
import sys
import logging
from typing import List, Optional, Literal
from abc import ABC, abstractmethod

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


logger = logging.getLogger(__name__)

# DuckDuckGo 可用性检查
try:
    from langchain_community.utilities.duckduckgo_search import DuckDuckGoSearchAPIWrapper
    DDG_AVAILABLE = True
except ImportError:
    DDG_AVAILABLE = False
    logger.warning("DuckDuckGo 相关依赖缺失，DuckDuckGo 搜索不可用")

# Tavily 可用性检查
try:
    from langchain_tavily import TavilySearch
    TAVILY_AVAILABLE = True
except ImportError:
    TAVILY_AVAILABLE = False
    logger.warning("langchain-tavily 未安装，Tavily 搜索不可用")


class BaseSearchAPI(ABC):
    """搜索引擎基类"""

    @abstractmethod
    def search(self, query: str, max_results: int = 5) -> List[Document]:
        """
        执行搜索并返回结果

        Args:
            query: 搜索查询
            max_results: 最大返回结果数

        Returns:
            Document 列表
        """
        pass


class DuckDuckGoSearchAPI(BaseSearchAPI):
    """DuckDuckGo 搜索 API"""

    def __init__(self):
        if not DDG_AVAILABLE:
            raise ImportError("DuckDuckGo 搜索依赖未安装")

    def search(self, query: str, max_results: int = 5) -> List[Document]:
        """
        执行 DuckDuckGo 搜索

        Args:
            query: 搜索查询
            max_results: 最大返回结果数

        Returns:
            Document 列表
        """
        try:
            logger.info(f"[DuckDuckGo] 正在搜索: {query}")
            wrapper = DuckDuckGoSearchAPIWrapper(
                max_results=max_results, region="cn-zh")
            results = wrapper.results(query, max_results=max_results)

            docs = []
            for res in results:
                title = res.get('title', 'Unknown Title')
                snippet = res.get('snippet', '')
                link = res.get('link', '')

                if not snippet:
                    continue

                content = f"【标题】: {title}\n【来源】: {link}\n【关键摘要】: {snippet}"
                metadata = {
                    "source": link,
                    "title": title,
                    "type": "api_search",
                    "search_engine": "duckduckgo"
                }
                docs.append(Document(page_content=content, metadata=metadata))

            logger.info(f"[DuckDuckGo] 搜索完成，返回 {len(docs)} 条结果")
            return docs

        except Exception as e:
            logger.error(f"[DuckDuckGo] 搜索出错: {e}")
            return []


class TavilySearchAPI(BaseSearchAPI):
    """Tavily 搜索 API"""

    def __init__(self, api_key: str = None):
        if not TAVILY_AVAILABLE:
            raise ImportError("langchain-tavily 未安装")

        config = get_tavily_config()
        self.api_key = api_key or config.get("api_key", "")

        if not self.api_key:
            logger.warning("Tavily API Key 未配置，Tavily 搜索可能不可用")

    def search(self, query: str, max_results: int = 5) -> List[Document]:
        """
        执行 Tavily 搜索

        Args:
            query: 搜索查询
            max_results: 最大返回结果数

        Returns:
            Document 列表
        """
        if not self.api_key:
            logger.warning("[Tavily] API Key 未配置，跳过搜索")
            return []

        try:
            logger.info(f"[Tavily] 正在搜索: {query}")

            # 使用 TavilySearch
            tavily_search = TavilySearch(
                max_results=max_results,
                api_key=self.api_key,
                include_raw_content=False,
                include_images=False,
            )

            results = tavily_search.invoke(query)

            docs = []
            # Tavily 返回格式: {"results": [...], "query": "..."}
            if isinstance(results, dict) and "results" in results:
                for res in results["results"]:
                    title = res.get('title', 'Unknown Title')
                    content_text = res.get(
                        'content', '') or res.get('snippet', '')
                    link = res.get('url', '') or res.get('link', '')

                    if not content_text:
                        continue

                    content = f"【标题】: {title}\n【来源】: {link}\n【关键摘要】: {content_text}"
                    metadata = {
                        "source": link,
                        "title": title,
                        "type": "api_search",
                        "search_engine": "tavily",
                        "score": res.get('score', 0)
                    }
                    docs.append(
                        Document(page_content=content, metadata=metadata))

            logger.info(f"[Tavily] 搜索完成，返回 {len(docs)} 条结果")
            return docs

        except Exception as e:
            logger.error(f"[Tavily] 搜索出错: {e}")
            return []


class UnifiedSearchAPI:
    """
    统一的搜索引擎 API 封装器

    支持多搜索引擎切换和降级策略：
    1. 优先使用 Tavily (如果配置了 API Key)
    2. 降级到 DuckDuckGo (无需 API Key)
    """

    def __init__(
        self,
        max_results: int = 5,
        search_provider: Literal["auto", "tavily", "duckduckgo"] = "auto"
    ):
        """
        初始化统一搜索 API

        Args:
            max_results: 最大返回结果数
            search_provider: 搜索引擎选择
                - "auto": 自动选择 (优先 Tavily，降级 DuckDuckGo)
                - "tavily": 仅使用 Tavily
                - "duckduckgo": 仅使用 DuckDuckGo
        """
        self.max_results = max_results
        self.search_provider = search_provider

        # 初始化各搜索引擎
        self._tavily = None
        self._duckduckgo = None

        # 根据 provider 初始化
        if search_provider in ["auto", "tavily"]:
            if TAVILY_AVAILABLE:
                try:
                    config = get_tavily_config()
                    if config.get("api_key"):
                        self._tavily = TavilySearchAPI(config["api_key"])
                        logger.info("[UnifiedSearch] Tavily 搜索已初始化")
                except Exception as e:
                    logger.warning(f"[UnifiedSearch] Tavily 初始化失败: {e}")

        if search_provider in ["auto", "duckduckgo"]:
            if DDG_AVAILABLE:
                try:
                    self._duckduckgo = DuckDuckGoSearchAPI()
                    logger.info("[UnifiedSearch] DuckDuckGo 搜索已初始化")
                except Exception as e:
                    logger.warning(f"[UnifiedSearch] DuckDuckGo 初始化失败: {e}")

    def search(self, query: str, max_results: int = None) -> List[Document]:
        """
        执行搜索

        Args:
            query: 搜索查询
            max_results: 最大返回结果数 (可选，默认使用初始化时的值)

        Returns:
            Document 列表
        """
        max_results = max_results or self.max_results

        # 根据配置选择搜索引擎
        if self.search_provider == "tavily":
            if self._tavily:
                return self._tavily.search(query, max_results)
            else:
                logger.warning("[UnifiedSearch] Tavily 不可用，无搜索结果")
                return []

        elif self.search_provider == "duckduckgo":
            if self._duckduckgo:
                return self._duckduckgo.search(query, max_results)
            else:
                logger.warning("[UnifiedSearch] DuckDuckGo 不可用，无搜索结果")
                return []

        else:  # auto
            # 优先使用 Tavily
            if self._tavily:
                results = self._tavily.search(query, max_results)
                if results:
                    return results
                logger.info("[UnifiedSearch] Tavily 无结果，尝试 DuckDuckGo")

            # 降级到 DuckDuckGo
            if self._duckduckgo:
                return self._duckduckgo.search(query, max_results)

            logger.warning("[UnifiedSearch] 无可用搜索引擎")
            return []

    def search_with_fallback(
        self,
        query: str,
        max_results: int = None
    ) -> tuple[List[Document], str]:
        """
        执行搜索并返回使用的搜索引擎名称

        Args:
            query: 搜索查询
            max_results: 最大返回结果数

        Returns:
            (Document 列表, 使用的搜索引擎名称)
        """
        max_results = max_results or self.max_results

        if self._tavily:
            results = self._tavily.search(query, max_results)
            if results:
                return results, "tavily"

        if self._duckduckgo:
            results = self._duckduckgo.search(query, max_results)
            if results:
                return results, "duckduckgo"

        return [], "none"


# 单例模式
_unified_search_instance = None


def get_unified_search(
    max_results: int = 5,
    search_provider: Literal["auto", "tavily", "duckduckgo"] = "auto"
) -> UnifiedSearchAPI:
    """
    获取统一搜索 API 实例 (单例)

    Args:
        max_results: 最大返回结果数
        search_provider: 搜索引擎选择

    Returns:
        UnifiedSearchAPI 实例
    """
    global _unified_search_instance
    if _unified_search_instance is None:
        _unified_search_instance = UnifiedSearchAPI(
            max_results, search_provider)
    return _unified_search_instance


if __name__ == "__main__":
    from dotenv import load_dotenv
    load_dotenv()
    logging.basicConfig(level=logging.INFO)

    print("=" * 50)
    print("测试统一搜索 API")
    print("=" * 50)

    # 测试自动模式
    searcher = UnifiedSearchAPI(max_results=3, search_provider="auto")
    results, engine = searcher.search_with_fallback("2024巴黎奥运会")
    print(f"\n使用的搜索引擎: {engine}")
    print(f"结果数量: {len(results)}")
    for doc in results[:2]:
        print(f"\n{doc.page_content[:200]}...")
