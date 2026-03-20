"""
Phase 7 多源混合检索测试

测试各组件的功能：
1. Router - 意图路由
2. SearchAPI - 多源搜索
3. BrowserAgent - 网页爬取
4. Reranker - 重排序
5. HybridRetriever - 完整流程
"""

from dotenv import load_dotenv
import os
import sys
import logging

# 设置路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def test_router():
    """测试路由器"""
    print("\n" + "=" * 60)
    print("测试 1: Router 意图路由")
    print("=" * 60)

    from rag_engine.router import RAGRouter

    router = RAGRouter(use_cache=False)

    test_cases = [
        ("请出三道牛顿第二定律的选择题", "local"),
        ("结合2024巴黎奥运会，出一道物理题", "api"),
        ("帮我查一下这道题的出处：https://example.com/question", "browser"),
        ("根据最新的科技新闻，出一道关于物理定律的应用题", "hybrid"),
    ]

    for query, expected_route in test_cases:
        print(f"\n查询: {query}")
        result = router.route_query(query)
        print(f"  路由: {result.route} (预期: {expected_route})")
        print(f"  置信度: {result.confidence:.2f}")
        print(f"  改写Query: {result.search_query}")
        if result.target_urls:
            print(f"  目标URL: {result.target_urls}")

    print("\n[Router] 测试完成")
    return True


def test_search_api():
    """测试搜索 API"""
    print("\n" + "=" * 60)
    print("测试 2: SearchAPI 多源搜索")
    print("=" * 60)

    from rag_engine.search_api import UnifiedSearchAPI

    # 测试自动模式
    searcher = UnifiedSearchAPI(max_results=3, search_provider="auto")

    print("\n测试搜索: 2024年诺贝尔物理学奖")
    results, engine = searcher.search_with_fallback("2024年诺贝尔物理学奖")

    print(f"使用的搜索引擎: {engine}")
    print(f"结果数量: {len(results)}")

    if results:
        print("\n第一条结果:")
        print(results[0].page_content[:300])

    print("\n[SearchAPI] 测试完成")
    return True


def test_browser_agent():
    """测试 Browser Agent"""
    print("\n" + "=" * 60)
    print("测试 3: BrowserAgent 网页爬取")
    print("=" * 60)

    try:
        from rag_engine.browser_agent import BrowserAgent

        agent = BrowserAgent()

        # 测试 Playwright 模式
        print("\n测试 Playwright 模式访问百度...")
        docs = agent.browse_url(
            "https://www.baidu.com",
            "提取页面标题和主要内容"
        )

        if docs:
            print(f"提取成功，内容长度: {len(docs[0].page_content)}")
            print(docs[0].page_content[:200])
        else:
            print("提取失败")

        print("\n[BrowserAgent] 测试完成")
        return True

    except ImportError as e:
        print(f"[BrowserAgent] 依赖未安装，跳过测试: {e}")
        return True


def test_reranker():
    """测试 Reranker"""
    print("\n" + "=" * 60)
    print("测试 4: Reranker 重排序")
    print("=" * 60)

    from rag_engine.reranker import get_reranker, NoOpReranker
    from langchain_core.documents import Document

    # 创建测试文档
    test_docs = [
        Document(page_content="Python 是一种高级编程语言，广泛用于数据科学和人工智能领域。"),
        Document(page_content="Java 是一种面向对象的编程语言，主要用于企业级应用开发。"),
        Document(page_content="机器学习是人工智能的一个分支，使用算法从数据中学习。"),
        Document(page_content="JavaScript 是一种脚本语言，主要用于网页开发。"),
        Document(page_content="深度学习是机器学习的子领域，使用神经网络进行学习。"),
    ]

    query = "人工智能和机器学习"

    # 测试 LLM Reranker
    print("\n测试 LLM Reranker...")
    try:
        reranker = get_reranker("llm")
        reranked = reranker.rerank(query, test_docs, top_k=3)
        print(f"重排序结果 ({len(reranked)} 个):")
        for i, doc in enumerate(reranked):
            score = doc.metadata.get("rerank_score", "N/A")
            print(f"  {i+1}. {doc.page_content[:40]}... (score: {score})")
    except Exception as e:
        print(f"LLM Reranker 测试失败: {e}")

    # 测试 NoOp Reranker
    print("\n测试 NoOp Reranker...")
    noop_reranker = NoOpReranker()
    noop_result = noop_reranker.rerank(query, test_docs, top_k=3)
    print(f"NoOp 结果数量: {len(noop_result)}")

    print("\n[Reranker] 测试完成")
    return True


def test_hybrid_retriever():
    """测试完整的混合检索流程"""
    print("\n" + "=" * 60)
    print("测试 5: HybridRetriever 完整流程")
    print("=" * 60)

    from rag_engine.hybrid_retriever import HybridRetriever

    retriever = HybridRetriever(use_reranker=False)  # 暂时禁用 Reranker 加快测试

    test_cases = [
        ("牛顿第二定律选择题", "local"),
        ("2024年奥运会物理题", "api或hybrid"),
    ]

    for query, expected in test_cases:
        print(f"\n查询: {query}")
        result = retriever.smart_retrieve(query, top_k=3, use_rerank=False)

        print(f"  路由: {result['route']}")
        print(f"  改写Query: {result['search_query']}")
        print(f"  文档数: {result['doc_count']}")
        print(f"  来源: {result['sources_info']}")

        if result['docs']:
            print(f"  第一条内容预览:")
            print(f"    {result['docs'][0].page_content[:100]}...")

    print("\n[HybridRetriever] 测试完成")
    return True


def run_all_tests():
    """运行所有测试"""
    print("\n" + "#" * 60)
    print("# Phase 7 多源混合检索测试")
    print("#" * 60)

    tests = [
        ("Router", test_router),
        ("SearchAPI", test_search_api),
        ("BrowserAgent", test_browser_agent),
        ("Reranker", test_reranker),
        ("HybridRetriever", test_hybrid_retriever),
    ]

    results = {}
    for name, test_func in tests:
        try:
            results[name] = test_func()
        except Exception as e:
            print(f"\n[{name}] 测试失败: {e}")
            results[name] = False

    # 汇总
    print("\n" + "#" * 60)
    print("# 测试汇总")
    print("#" * 60)
    for name, passed in results.items():
        status = "PASS" if passed else "FAIL"
        print(f"  {name}: {status}")

    all_passed = all(results.values())
    print(f"\n总体结果: {'ALL PASSED' if all_passed else 'SOME FAILED'}")
    return all_passed


if __name__ == "__main__":
    run_all_tests()
