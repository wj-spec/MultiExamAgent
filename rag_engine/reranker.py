"""
Reranker 重排序模块

支持多种 Reranker 提供者：
1. Cohere 云 API
2. HuggingFace 本地模型 (Cross-Encoder)
3. LLM 重排序
"""

from utils.config import get_reranker_config, get_llm_config, settings
from langchain_core.documents import Document
import os
import sys
import logging
from typing import List, Optional, Literal
from abc import ABC, abstractmethod

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


logger = logging.getLogger(__name__)

# Cohere 可用性检查
try:
    import cohere
    COHERE_AVAILABLE = True
except ImportError:
    COHERE_AVAILABLE = False
    logger.debug("cohere 未安装，Cohere Reranker 不可用")

# HuggingFace 可用性检查
try:
    from sentence_transformers import CrossEncoder
    HUGGINGFACE_AVAILABLE = True
except ImportError:
    HUGGINGFACE_AVAILABLE = False
    logger.debug("sentence-transformers 未安装，HuggingFace Reranker 不可用")


class BaseReranker(ABC):
    """Reranker 基类"""

    @abstractmethod
    def rerank(
        self,
        query: str,
        documents: List[Document],
        top_k: int = 5
    ) -> List[Document]:
        """
        对文档进行重排序

        Args:
            query: 查询字符串
            documents: 待排序的文档列表
            top_k: 返回的文档数量

        Returns:
            重排序后的文档列表
        """
        pass


class NoOpReranker(BaseReranker):
    """无操作 Reranker (直接返回原始列表)"""

    def rerank(
        self,
        query: str,
        documents: List[Document],
        top_k: int = 5
    ) -> List[Document]:
        return documents[:top_k]


class CohereReranker(BaseReranker):
    """Cohere 云 API Reranker"""

    def __init__(self, api_key: str = None, model: str = "rerank-multilingual-v3.0"):
        """
        初始化 Cohere Reranker

        Args:
            api_key: Cohere API Key
            model: Reranker 模型名称
        """
        if not COHERE_AVAILABLE:
            raise ImportError("cohere 未安装，请运行: pip install cohere")

        config = get_reranker_config()
        self.api_key = api_key or config.get("cohere_api_key", "")
        self.model = model

        if not self.api_key:
            raise ValueError("Cohere API Key 未配置")

        self._client = None

    @property
    def client(self):
        """懒加载 Cohere 客户端"""
        if self._client is None:
            self._client = cohere.Client(self.api_key)
        return self._client

    def rerank(
        self,
        query: str,
        documents: List[Document],
        top_k: int = 5
    ) -> List[Document]:
        """
        使用 Cohere API 进行重排序

        Args:
            query: 查询字符串
            documents: 待排序的文档列表
            top_k: 返回的文档数量

        Returns:
            重排序后的文档列表
        """
        if not documents:
            return []

        try:
            logger.info(f"[Cohere Reranker] 正在重排序 {len(documents)} 个文档...")

            # 提取文档内容
            docs_text = [doc.page_content for doc in documents]

            # 调用 Cohere Rerank API
            response = self.client.rerank(
                query=query,
                documents=docs_text,
                top_n=min(top_k, len(documents)),
                model=self.model
            )

            # 根据重排序结果重新排列文档
            reranked_docs = []
            for result in response.results:
                idx = result.index
                doc = documents[idx]
                # 添加重排序分数到元数据
                doc.metadata["rerank_score"] = result.relevance_score
                doc.metadata["reranker"] = "cohere"
                reranked_docs.append(doc)

            logger.info(f"[Cohere Reranker] 重排序完成，返回 {len(reranked_docs)} 个文档")
            return reranked_docs

        except Exception as e:
            logger.error(f"[Cohere Reranker] 重排序失败: {e}")
            # 降级返回原始列表
            return documents[:top_k]


class HuggingFaceReranker(BaseReranker):
    """HuggingFace Cross-Encoder Reranker"""

    def __init__(self, model_name: str = "cross-encoder/ms-marco-MiniLM-L-6-v2"):
        """
        初始化 HuggingFace Reranker

        Args:
            model_name: Cross-Encoder 模型名称
        """
        if not HUGGINGFACE_AVAILABLE:
            raise ImportError(
                "sentence-transformers 未安装，请运行: pip install sentence-transformers")

        config = get_reranker_config()
        self.model_name = model_name or config.get(
            "model", "cross-encoder/ms-marco-MiniLM-L-6-v2")
        self._model = None

    @property
    def model(self):
        """懒加载模型"""
        if self._model is None:
            logger.info(f"[HF Reranker] 正在加载模型: {self.model_name}")
            self._model = CrossEncoder(self.model_name)
        return self._model

    def rerank(
        self,
        query: str,
        documents: List[Document],
        top_k: int = 5
    ) -> List[Document]:
        """
        使用 Cross-Encoder 进行重排序

        Args:
            query: 查询字符串
            documents: 待排序的文档列表
            top_k: 返回的文档数量

        Returns:
            重排序后的文档列表
        """
        if not documents:
            return []

        try:
            logger.info(f"[HF Reranker] 正在重排序 {len(documents)} 个文档...")

            # 构建查询-文档对
            pairs = [(query, doc.page_content) for doc in documents]

            # 计算相关性分数
            scores = self.model.predict(pairs)

            # 按分数排序
            scored_docs = list(zip(documents, scores))
            scored_docs.sort(key=lambda x: x[1], reverse=True)

            # 返回 top_k 文档
            reranked_docs = []
            for doc, score in scored_docs[:top_k]:
                doc.metadata["rerank_score"] = float(score)
                doc.metadata["reranker"] = "huggingface"
                reranked_docs.append(doc)

            logger.info(f"[HF Reranker] 重排序完成，返回 {len(reranked_docs)} 个文档")
            return reranked_docs

        except Exception as e:
            logger.error(f"[HF Reranker] 重排序失败: {e}")
            return documents[:top_k]


class LLMReranker(BaseReranker):
    """使用 LLM 进行重排序"""

    def __init__(self, llm_model: str = None):
        """
        初始化 LLM Reranker

        Args:
            llm_model: 使用的 LLM 模型
        """
        llm_config = get_llm_config()
        self.llm_model = llm_model or llm_config.get(
            "default_model", "gpt-4o-mini")
        self._llm = None

    @property
    def llm(self):
        """懒加载 LLM"""
        if self._llm is None:
            from utils.config import get_llm
            self._llm = get_llm(model=self.llm_model, temperature=0)
        return self._llm

    def rerank(
        self,
        query: str,
        documents: List[Document],
        top_k: int = 5
    ) -> List[Document]:
        """
        使用 LLM 进行重排序

        Args:
            query: 查询字符串
            documents: 待排序的文档列表
            top_k: 返回的文档数量

        Returns:
            重排序后的文档列表
        """
        if not documents:
            return []

        # 如果文档数量较少，直接返回
        if len(documents) <= top_k:
            return documents

        try:
            logger.info(f"[LLM Reranker] 正在重排序 {len(documents)} 个文档...")

            # 构建文档摘要
            doc_summaries = []
            for i, doc in enumerate(documents):
                content = doc.page_content[:500]  # 截断以控制 token
                doc_summaries.append(f"[{i}] {content}")

            # 构建 prompt
            prompt = f"""你是一个专业的信息检索专家。请根据查询对以下文档片段进行相关性排序。

查询: {query}

文档片段:
{chr(10).join(doc_summaries)}

请返回最相关的 {top_k} 个文档的编号，按相关性从高到低排列。
只返回编号列表，用逗号分隔，例如: 2, 5, 1, 3"""

            # 调用 LLM
            response = self.llm.invoke(prompt)
            result_text = response.content if hasattr(
                response, 'content') else str(response)

            # 解析结果
            import re
            numbers = re.findall(r'\d+', result_text)
            indices = [int(n) for n in numbers if 0 <=
                       int(n) < len(documents)][:top_k]

            # 如果解析失败，返回原始顺序
            if not indices:
                logger.warning("[LLM Reranker] 无法解析 LLM 输出，返回原始顺序")
                return documents[:top_k]

            # 构建重排序后的文档列表
            reranked_docs = []
            for idx in indices:
                doc = documents[idx]
                doc.metadata["reranker"] = "llm"
                reranked_docs.append(doc)

            logger.info(f"[LLM Reranker] 重排序完成，返回 {len(reranked_docs)} 个文档")
            return reranked_docs

        except Exception as e:
            logger.error(f"[LLM Reranker] 重排序失败: {e}")
            return documents[:top_k]


def get_reranker(
    provider: Literal["none", "cohere", "huggingface", "llm"] = None
) -> BaseReranker:
    """
    获取 Reranker 实例

    Args:
        provider: Reranker 提供者
            - "none": 禁用 Reranker
            - "cohere": 使用 Cohere 云 API
            - "huggingface": 使用本地 HuggingFace 模型
            - "llm": 使用 LLM 进行重排序

    Returns:
        Reranker 实例
    """
    config = get_reranker_config()
    provider = provider or config.get("provider", "none")

    if provider == "none":
        logger.info("[Reranker] 使用 NoOp Reranker (禁用重排序)")
        return NoOpReranker()

    elif provider == "cohere":
        if not COHERE_AVAILABLE:
            logger.warning("[Reranker] Cohere 不可用，降级到 NoOp")
            return NoOpReranker()

        api_key = config.get("cohere_api_key", "")
        if not api_key:
            logger.warning("[Reranker] Cohere API Key 未配置，降级到 NoOp")
            return NoOpReranker()

        try:
            logger.info("[Reranker] 使用 Cohere Reranker")
            return CohereReranker(api_key=api_key)
        except Exception as e:
            logger.warning(f"[Reranker] Cohere 初始化失败: {e}，降级到 NoOp")
            return NoOpReranker()

    elif provider == "huggingface":
        if not HUGGINGFACE_AVAILABLE:
            logger.warning("[Reranker] HuggingFace 不可用，降级到 NoOp")
            return NoOpReranker()

        try:
            model = config.get("model", "cross-encoder/ms-marco-MiniLM-L-6-v2")
            logger.info(f"[Reranker] 使用 HuggingFace Reranker: {model}")
            return HuggingFaceReranker(model_name=model)
        except Exception as e:
            logger.warning(f"[Reranker] HuggingFace 初始化失败: {e}，降级到 NoOp")
            return NoOpReranker()

    elif provider == "llm":
        try:
            logger.info("[Reranker] 使用 LLM Reranker")
            return LLMReranker()
        except Exception as e:
            logger.warning(f"[Reranker] LLM Reranker 初始化失败: {e}，降级到 NoOp")
            return NoOpReranker()

    else:
        logger.warning(f"[Reranker] 未知的 provider: {provider}，使用 NoOp")
        return NoOpReranker()


# 单例模式
_reranker_instance = None


def get_reranker_singleton() -> BaseReranker:
    """获取 Reranker 单例实例"""
    global _reranker_instance
    if _reranker_instance is None:
        _reranker_instance = get_reranker()
    return _reranker_instance


if __name__ == "__main__":
    from dotenv import load_dotenv
    load_dotenv()
    logging.basicConfig(level=logging.INFO)

    print("=" * 50)
    print("测试 Reranker")
    print("=" * 50)

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
    print("\n[测试] LLM Reranker...")
    reranker = get_reranker("llm")
    reranked = reranker.rerank(query, test_docs, top_k=3)
    print(f"重排序结果 ({len(reranked)} 个):")
    for i, doc in enumerate(reranked):
        print(
            f"  {i+1}. {doc.page_content[:50]}... (score: {doc.metadata.get('rerank_score', 'N/A')})")
