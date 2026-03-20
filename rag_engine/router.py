"""
多源检索意图路由器 (Query Formulation & Routing)

基于 LLM 分析用户输入，决定使用哪种检索策略：
- local: 纯本地知识库检索
- api: 公共搜索引擎
- browser: 深度网页爬取
- hybrid: 多源混合检索
"""

from pydantic import BaseModel, Field
from langchain_core.prompts import ChatPromptTemplate
from utils.config import get_llm
import sys
import os
import logging
import hashlib
import re
from typing import Literal, List, Optional, Dict
from functools import lru_cache
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


logger = logging.getLogger(__name__)


class RouteDecision(BaseModel):
    """RAG 路由决策结构"""
    route: Literal["local", "api", "browser", "hybrid"] = Field(
        description="选择检索的路由方向: local(纯本地教学大纲), api(需要公共新闻/时事/常识), browser(需要深度防爬网页查证), hybrid(本地大纲与API结合)"
    )
    reasoning: str = Field(description="做出此路由决定的原因说明")
    search_query: str = Field(
        description="基于用户输入改写后的、最适合搜索引擎或向量检索的独立且精准的 Query")
    confidence: float = Field(
        default=0.8,
        ge=0.0,
        le=1.0,
        description="路由决策的置信度 (0.0-1.0)"
    )
    target_urls: List[str] = Field(
        default_factory=list,
        description="如果选择 browser 路由，指定需要访问的目标 URL 列表"
    )
    suggested_sources: List[str] = Field(
        default_factory=list,
        description="建议的检索来源类型列表"
    )


class RouteCache:
    """路由决策缓存"""

    def __init__(self, max_size: int = 100, ttl_seconds: int = 3600):
        self.max_size = max_size
        self.ttl_seconds = ttl_seconds
        self._cache: Dict[str, tuple] = {}

    def _hash_query(self, query: str) -> str:
        normalized = " ".join(query.lower().strip().split())
        return hashlib.md5(normalized.encode()).hexdigest()

    def get(self, query: str) -> Optional[RouteDecision]:
        key = self._hash_query(query)
        if key in self._cache:
            decision, timestamp = self._cache[key]
            if datetime.now() - timestamp < timedelta(seconds=self.ttl_seconds):
                logger.debug(f"[RouteCache] 命中缓存: {query[:50]}...")
                return decision
            else:
                del self._cache[key]
        return None

    def set(self, query: str, decision: RouteDecision):
        if len(self._cache) >= self.max_size:
            oldest_key = min(self._cache.keys(),
                             key=lambda k: self._cache[k][1])
            del self._cache[oldest_key]
        key = self._hash_query(query)
        self._cache[key] = (decision, datetime.now())

    def clear(self):
        self._cache.clear()
        logger.info("[RouteCache] 缓存已清空")


ROUTER_SYSTEM_PROMPT = """你是一个专业的教育系统智能检索意图识别专家。
你的任务是分析用户的输入，决定应该使用哪种检索策略。

可用的检索源：
1. "local"：本地教育知识库（包含教学大纲、高频课本知识点等）。
   - 当用户的问题纯粹是学术理论、普通出题，不涉及最新时事时选择。

2. "api"：公共搜索引擎接口（DuckDuckGo / Tavily）。
   - 当用户问题中明确包含"结合最新的XXX事件"、"结合XXX新闻背景"，或者需要查询公开的时效性知识时选择。

3. "browser"：深度网页爬取专家（Playwright / browser-use）。
   - 当用户明确要求核对某道题是否抄袭自特定网站、查重、或者需要进行深网页面截图查证时选择。
   - 如果用户提供了具体的 URL，请在 target_urls 中列出。

4. "hybrid"：上述源的混合。
   - 当既要学术大纲的知识支撑（local），又要最新的事实素材（api）时选择。

请分析用户的意图，并给出检索策略、决策理由、优化后的检索核心词、置信度以及目标URL（如果有）。"""


class RAGRouter:
    """多源检索意图路由器"""

    def __init__(self, use_cache: bool = True):
        self.llm = get_llm(temperature=0).with_structured_output(RouteDecision)

        self.prompt = ChatPromptTemplate.from_messages([
            ("system", ROUTER_SYSTEM_PROMPT),
            ("human", "用户输入: {user_input}")
        ])

        self.chain = self.prompt | self.llm
        self.use_cache = use_cache
        self.cache = RouteCache() if use_cache else None

    def _extract_urls(self, text: str) -> List[str]:
        """从文本中提取 URL"""
        url_pattern = r'https?://[^\s<>"{}|\\^`\[\]]+'
        return re.findall(url_pattern, text)

    def route_query(self, user_input: str) -> RouteDecision:
        """对用户输入进行意图识别并给出路由结果"""
        if self.use_cache and self.cache:
            cached = self.cache.get(user_input)
            if cached:
                logger.info(f"[Router] 使用缓存结果 => [{cached.route}]")
                return cached

        try:
            logger.info(f"[Router] 正在进行意图路由分析: {user_input[:100]}...")
            decision = self.chain.invoke({"user_input": user_input})

            # 后处理：提取 URL
            extracted_urls = self._extract_urls(user_input)
            if extracted_urls and not decision.target_urls:
                decision.target_urls = extracted_urls

            # 如果有目标 URL 但路由不是 browser，考虑调整
            if decision.target_urls and decision.route != "browser":
                decision.suggested_sources.append("browser")

            logger.info(
                f"[Router] 路由完成 => [{decision.route}] (置信度: {decision.confidence:.2f})")
            logger.info(f"[Router] 改写 Query: {decision.search_query}")

            # 缓存结果
            if self.use_cache and self.cache:
                self.cache.set(user_input, decision)

            return decision

        except Exception as e:
            logger.error(f"[Router] 分析异常: {e}，默认降级为 local 路由")
            return RouteDecision(
                route="local",
                reasoning="由于路由分析失败，默认执行安全性最高的本地知识检索",
                search_query=user_input,
                confidence=0.5
            )

    def clear_cache(self):
        """清空路由缓存"""
        if self.cache:
            self.cache.clear()


# 单例模式
_router_instance = None


def get_router() -> RAGRouter:
    """获取路由器实例（单例）"""
    global _router_instance
    if _router_instance is None:
        _router_instance = RAGRouter()
    return _router_instance


if __name__ == "__main__":
    from dotenv import load_dotenv
    load_dotenv()
    logging.basicConfig(level=logging.INFO)

    router = RAGRouter()
    print("=" * 50)
    print("路由测试")
    print("=" * 50)

    test_cases = [
        "结合2024年巴黎奥运会全红婵跳水，出一道高一物理自由落体计算题。",
        "请根据牛顿第二定律出三道选择题。",
        "帮我查一下这道题是不是抄袭的：https://example.com/question/123",
        "根据最新的诺贝尔物理学奖，出一道相关的推断题。",
    ]

    for query in test_cases:
        print(f"\n查询: {query}")
        result = router.route_query(query)
        print(f"路由: {result.route}")
        print(f"置信度: {result.confidence}")
        print(f"改写Query: {result.search_query}")
        if result.target_urls:
            print(f"目标URL: {result.target_urls}")
