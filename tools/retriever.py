"""
业务知识库检索工具

基于 LangChain 和向量数据库实现的知识库检索功能。
支持 PDF、DOCX 等文档的向量化存储和检索。
支持向量检索、BM25检索和混合检索。
"""

from utils.config import get_embedding_config, settings
import os
import re
import json
import math
from typing import List, Optional, Type, Dict, Any, Set
from pydantic import BaseModel, Field
from langchain_core.tools import BaseTool
from langchain_core.documents import Document
from collections import defaultdict

# 导入配置
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# 延迟导入，避免未安装时报错
try:
    # 尝试使用新版 langchain-chroma
    try:
        from langchain_chroma import Chroma
    except ImportError:
        from langchain_community.vectorstores import Chroma

    from langchain_community.document_loaders import PyPDFLoader, Docx2txtLoader
    from langchain_text_splitters import RecursiveCharacterTextSplitter

    # Embeddings - 根据配置动态导入
    from langchain_openai import OpenAIEmbeddings

    # 可选导入
    try:
        from langchain_community.embeddings import DashScopeEmbeddings
        DASHSCOPE_AVAILABLE = True
    except ImportError:
        DASHSCOPE_AVAILABLE = False

    try:
        from langchain_community.embeddings import HuggingFaceEmbeddings
        HUGGINGFACE_AVAILABLE = True
    except ImportError:
        HUGGINGFACE_AVAILABLE = False

    try:
        from langchain_ollama import OllamaEmbeddings
        OLLAMA_AVAILABLE = True
    except ImportError:
        OLLAMA_AVAILABLE = False

    VECTOR_STORE_AVAILABLE = True
except ImportError:
    VECTOR_STORE_AVAILABLE = False
    RecursiveCharacterTextSplitter = None  # 依赖缺失时置为 None，避免 NameError


class BM25Retriever:
    """
    BM25 检索器

    用于基于关键词的文档检索，作为向量检索的备选方案。
    """

    # 停用词表
    STOP_WORDS: Set[str] = {
        '的', '是', '在', '了', '和', '与', '或', '有', '对', '为', '这', '那',
        '我', '你', '他', '她', '它', '们', '着', '过', '会', '能', '要', '就',
        '都', '也', '还', '又', '很', '但', '而', '不', '没', '到', '把', '被',
        '让', '给', '从', '向', '以', '如', '等', '及', 'the', 'a', 'an', 'is',
        'are', 'was', 'were', 'be', 'been', 'being', 'have', 'has', 'had', 'do',
        'does', 'did', 'will', 'would', 'could', 'should', 'may', 'might', 'must'
    }

    def __init__(self, k1: float = 1.5, b: float = 0.75):
        """
        初始化 BM25 检索器

        Args:
            k1: 词频饱和参数
            b: 文档长度归一化参数
        """
        self.k1 = k1
        self.b = b
        self.documents: List[Dict[str, Any]] = []
        self.doc_term_freqs: List[Dict[str, int]] = []
        self.doc_freqs: Dict[str, int] = defaultdict(int)
        self.doc_lens: List[int] = []
        self.avgdl: float = 0
        self.n_docs: int = 0
        self.index_file: Optional[str] = None

    def _tokenize(self, text: str) -> List[str]:
        """
        分词

        Args:
            text: 输入文本

        Returns:
            词项列表
        """
        # 移除标点符号
        text = re.sub(r'[^\w\s\u4e00-\u9fff]', ' ', text)
        # 分词
        words = text.split()
        # 过滤停用词和短词
        return [w.lower() for w in words if w.lower() not in self.STOP_WORDS and len(w) > 1]

    def add_documents(self, documents: List[Dict[str, Any]]):
        """
        添加文档

        Args:
            documents: 文档列表，每个文档包含 content 和 metadata
        """
        self.documents = documents
        self.n_docs = len(documents)

        self.doc_term_freqs = []
        self.doc_freqs = defaultdict(int)
        self.doc_lens = []

        for doc in documents:
            content = doc.get("content", "")
            tokens = self._tokenize(content)

            self.doc_lens.append(len(tokens))

            term_freqs = defaultdict(int)
            for token in tokens:
                term_freqs[token] += 1
            self.doc_term_freqs.append(dict(term_freqs))

            # 计算文档频率
            for token in set(tokens):
                self.doc_freqs[token] += 1

        self.avgdl = sum(self.doc_lens) / self.n_docs if self.n_docs > 0 else 0

    def _idf(self, term: str) -> float:
        """计算逆文档频率"""
        df = self.doc_freqs.get(term, 0)
        return math.log((self.n_docs - df + 0.5) / (df + 0.5) + 1)

    def _score(self, query_tokens: List[str], doc_idx: int) -> float:
        """
        计算 BM25 分数

        Args:
            query_tokens: 查询词项
            doc_idx: 文档索引

        Returns:
            BM25 分数
        """
        score = 0.0
        doc_len = self.doc_lens[doc_idx]
        term_freqs = self.doc_term_freqs[doc_idx]

        for token in query_tokens:
            if token not in term_freqs:
                continue

            tf = term_freqs[token]
            idf = self._idf(token)

            numerator = tf * (self.k1 + 1)
            denominator = tf + self.k1 * \
                (1 - self.b + self.b * doc_len / self.avgdl)
            score += idf * numerator / denominator

        return score

    def search(self, query: str, top_k: int = 5) -> List[tuple]:
        """
        搜索

        Args:
            query: 查询字符串
            top_k: 返回数量

        Returns:
            (文档索引, 分数) 元组列表
        """
        if self.n_docs == 0:
            return []

        query_tokens = self._tokenize(query)
        if not query_tokens:
            return []

        scores = []
        for i in range(self.n_docs):
            score = self._score(query_tokens, i)
            if score > 0:
                scores.append((i, score))

        scores.sort(key=lambda x: x[1], reverse=True)
        return scores[:top_k]

    def save_index(self, file_path: str):
        """保存索引到文件"""
        data = {
            "documents": self.documents,
            "doc_term_freqs": self.doc_term_freqs,
            "doc_freqs": dict(self.doc_freqs),
            "doc_lens": self.doc_lens,
            "avgdl": self.avgdl,
            "n_docs": self.n_docs
        }
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        self.index_file = file_path

    def load_index(self, file_path: str) -> bool:
        """从文件加载索引"""
        if not os.path.exists(file_path):
            return False

        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)

            self.documents = data.get("documents", [])
            self.doc_term_freqs = data.get("doc_term_freqs", [])
            self.doc_freqs = defaultdict(int, data.get("doc_freqs", {}))
            self.doc_lens = data.get("doc_lens", [])
            self.avgdl = data.get("avgdl", 0)
            self.n_docs = data.get("n_docs", 0)
            self.index_file = file_path
            return True
        except Exception as e:
            print(f"加载 BM25 索引失败: {e}")
            return False


class KnowledgeBaseInput(BaseModel):
    """知识库检索工具的输入参数"""
    query: str = Field(description="检索查询字符串")
    top_k: int = Field(default=3, description="返回的最大文档片段数量")


class KnowledgeBaseRetriever:
    """
    业务知识库检索器

    负责文档的加载、向量化和检索。
    支持向量检索、BM25检索和混合检索。
    """

    def __init__(
        self,
        knowledge_dir: str = None,
        persist_directory: str = None,
        embedding_model: str = "text-embedding-ada-002"
    ):
        """
        初始化检索器

        Args:
            knowledge_dir: 知识库文档目录
            persist_directory: 向量数据库持久化目录
            embedding_model: 嵌入模型名称
        """
        # 获取项目根目录
        current_dir = os.path.dirname(os.path.abspath(__file__))
        project_root = os.path.dirname(current_dir)

        self.knowledge_dir = knowledge_dir or os.path.join(
            project_root, "data", "knowledge_base")
        self.persist_directory = persist_directory or os.path.join(
            project_root, "data", "chroma_db")
        self.embedding_model = embedding_model

        self.vectorstore = None
        self.bm25_retriever = BM25Retriever()
        if RecursiveCharacterTextSplitter is not None:
            self.text_splitter = RecursiveCharacterTextSplitter(
                chunk_size=1000,
                chunk_overlap=200
            )
        else:
            self.text_splitter = None

        self._init_vectorstore()
        self._init_bm25()

    def _create_embeddings(self):
        """
        根据配置创建 Embeddings 实例

        Returns:
            Embeddings 实例
        """
        config = get_embedding_config()
        provider = config.get("provider", "openai")

        if provider == "openai":
            return OpenAIEmbeddings(
                model=config.get("model", "text-embedding-3-small"),
                openai_api_key=config.get("api_key"),
                openai_api_base=config.get("base_url")
            )
        elif provider == "dashscope":
            if not DASHSCOPE_AVAILABLE:
                raise ImportError(
                    "DashScope embeddings 未安装，请运行: pip install dashscope")
            return DashScopeEmbeddings(
                model=config.get("model", "text-embedding-v2"),
                dashscope_api_key=config.get("api_key")
            )
        elif provider == "huggingface":
            if not HUGGINGFACE_AVAILABLE:
                raise ImportError(
                    "HuggingFace embeddings 未安装，请运行: pip install sentence-transformers")
            return HuggingFaceEmbeddings(
                model_name=config.get(
                    "model_name", "sentence-transformers/all-MiniLM-L6-v2")
            )
        elif provider == "ollama":
            if not OLLAMA_AVAILABLE:
                raise ImportError(
                    "Ollama embeddings 未安装，请运行: pip install langchain-ollama")
            return OllamaEmbeddings(
                model=config.get("model", "nomic-embed-text"),
                base_url=config.get("base_url", "http://localhost:11434")
            )
        else:
            raise ValueError(f"不支持的 embedding provider: {provider}")

    def _init_vectorstore(self):
        """初始化向量数据库"""
        if not VECTOR_STORE_AVAILABLE:
            print("警告: 向量存储依赖未安装，向量检索功能将不可用")
            return

        # 创建持久化目录
        os.makedirs(self.persist_directory, exist_ok=True)

        try:
            # 根据配置创建 embeddings
            embeddings = self._create_embeddings()
            self.vectorstore = Chroma(
                persist_directory=self.persist_directory,
                embedding_function=embeddings
            )
            print(
                f"向量数据库初始化成功，使用 {get_embedding_config().get('provider')} embedding 模型: {get_embedding_config().get('model')}")
        except Exception as e:
            print(f"初始化向量数据库时出错: {e}")
            self.vectorstore = None

    def _init_bm25(self):
        """初始化 BM25 检索器"""
        bm25_index_file = os.path.join(
            self.persist_directory, "bm25_index.json")

        # 尝试加载现有索引
        if self.bm25_retriever.load_index(bm25_index_file):
            print("BM25 索引加载成功")
            return

        # 如果没有现有索引，从知识库目录构建
        self._build_bm25_index()

    def _build_bm25_index(self):
        """从知识库文档构建 BM25 索引"""
        documents = []

        if os.path.exists(self.knowledge_dir):
            for filename in os.listdir(self.knowledge_dir):
                file_path = os.path.join(self.knowledge_dir, filename)
                if os.path.isfile(file_path):
                    docs = self.load_documents(file_path)
                    for doc in docs:
                        documents.append({
                            "content": doc.page_content,
                            "metadata": doc.metadata,
                            "source": filename
                        })

        if documents:
            self.bm25_retriever.add_documents(documents)
            # 保存索引
            bm25_index_file = os.path.join(
                self.persist_directory, "bm25_index.json")
            self.bm25_retriever.save_index(bm25_index_file)
            print(f"BM25 索引构建完成，共 {len(documents)} 个文档片段")

    def load_documents(self, file_path: str) -> List[Document]:
        """
        加载文档

        Args:
            file_path: 文档路径

        Returns:
            文档列表
        """
        ext = os.path.splitext(file_path)[1].lower()

        try:
            if ext == '.pdf':
                loader = PyPDFLoader(file_path)
            elif ext in ['.docx', '.doc']:
                loader = Docx2txtLoader(file_path)
            else:
                print(f"不支持的文件格式: {ext}")
                return []

            documents = loader.load()
            return self.text_splitter.split_documents(documents)

        except Exception as e:
            print(f"加载文档时出错: {e}")
            return []

    def add_documents(self, file_path: str) -> bool:
        """
        将文档添加到向量数据库和 BM25 索引

        Args:
            file_path: 文档路径

        Returns:
            是否成功添加
        """
        success = True

        # 添加到向量数据库
        if VECTOR_STORE_AVAILABLE and self.vectorstore is not None:
            documents = self.load_documents(file_path)
            if documents:
                try:
                    self.vectorstore.add_documents(documents)
                except Exception as e:
                    print(f"添加文档到向量数据库时出错: {e}")
                    success = False
            else:
                success = False

        # 添加到 BM25 索引
        documents = self.load_documents(file_path)
        if documents:
            bm25_docs = [
                {
                    "content": doc.page_content,
                    "metadata": doc.metadata,
                    "source": os.path.basename(file_path)
                }
                for doc in documents
            ]

            # 合并到现有索引
            existing_docs = self.bm25_retriever.documents
            self.bm25_retriever.add_documents(existing_docs + bm25_docs)

            # 保存索引
            bm25_index_file = os.path.join(
                self.persist_directory, "bm25_index.json")
            self.bm25_retriever.save_index(bm25_index_file)

        return success

    def retrieve_vector(self, query: str, top_k: int = 3) -> List[Document]:
        """
        向量检索

        Args:
            query: 查询字符串
            top_k: 返回数量

        Returns:
            相关文档列表
        """
        if not VECTOR_STORE_AVAILABLE or self.vectorstore is None:
            return []

        try:
            docs = self.vectorstore.similarity_search(query, k=top_k)
            return docs
        except Exception as e:
            print(f"向量检索出错: {e}")
            return []

    def retrieve_bm25(self, query: str, top_k: int = 3) -> List[Document]:
        """
        BM25 检索

        Args:
            query: 查询字符串
            top_k: 返回数量

        Returns:
            相关文档列表
        """
        results = self.bm25_retriever.search(query, top_k)

        documents = []
        for idx, score in results:
            doc_data = self.bm25_retriever.documents[idx]
            doc = Document(
                page_content=doc_data.get("content", ""),
                metadata=doc_data.get("metadata", {})
            )
            doc.metadata["bm25_score"] = score
            documents.append(doc)

        return documents

    def retrieve_hybrid(self, query: str, top_k: int = 3, vector_weight: float = 0.6) -> List[Document]:
        """
        混合检索（向量 + BM25）

        Args:
            query: 查询字符串
            top_k: 返回数量
            vector_weight: 向量检索权重 (0-1)

        Returns:
            相关文档列表
        """
        bm25_weight = 1 - vector_weight

        # 获取更多候选结果用于融合
        candidate_k = top_k * 3

        # 向量检索
        vector_docs = []
        vector_scores = {}
        if VECTOR_STORE_AVAILABLE and self.vectorstore is not None:
            try:
                docs_with_scores = self.vectorstore.similarity_search_with_score(
                    query, k=candidate_k)
                for doc, score in docs_with_scores:
                    vector_docs.append(doc)
                    # 向量分数转换为 0-1 范围（分数越小越相似）
                    vector_scores[doc.page_content[:100]] = 1 / (1 + score)
            except Exception as e:
                print(f"向量检索出错: {e}")

        # BM25 检索
        bm25_results = self.bm25_retriever.search(query, candidate_k)
        bm25_docs = []
        bm25_scores = {}
        max_bm25_score = max((score for _, score in bm25_results), default=1)

        for idx, score in bm25_results:
            doc_data = self.bm25_retriever.documents[idx]
            doc = Document(
                page_content=doc_data.get("content", ""),
                metadata=doc_data.get("metadata", {})
            )
            bm25_docs.append(doc)
            # BM25 分数归一化
            bm25_scores[doc.page_content[:100]] = score / \
                max_bm25_score if max_bm25_score > 0 else 0

        # 融合结果
        all_docs = {}
        for doc in vector_docs + bm25_docs:
            key = doc.page_content[:100]
            if key not in all_docs:
                all_docs[key] = doc

        # 计算综合分数
        scored_docs = []
        for key, doc in all_docs.items():
            vec_score = vector_scores.get(key, 0)
            bm25_score = bm25_scores.get(key, 0)
            combined_score = vector_weight * vec_score + bm25_weight * bm25_score
            scored_docs.append((doc, combined_score))

        # 排序并返回 top_k
        scored_docs.sort(key=lambda x: x[1], reverse=True)
        return [doc for doc, _ in scored_docs[:top_k]]

    def retrieve(self, query: str, top_k: int = 3, method: str = "hybrid") -> List[Document]:
        """
        检索相关文档

        Args:
            query: 查询字符串
            top_k: 返回数量
            method: 检索方法 (vector, bm25, hybrid)

        Returns:
            相关文档列表
        """
        if method == "vector":
            docs = self.retrieve_vector(query, top_k)
            if docs:
                return docs
            # 向量检索失败，退回 BM25
            return self.retrieve_bm25(query, top_k)
        elif method == "bm25":
            return self.retrieve_bm25(query, top_k)
        else:  # hybrid
            return self.retrieve_hybrid(query, top_k)

    def retrieve_with_scores(self, query: str, top_k: int = 3) -> List[tuple]:
        """
        检索相关文档（带相似度分数）

        Args:
            query: 查询字符串
            top_k: 返回数量

        Returns:
            (文档, 分数) 元组列表
        """
        if not VECTOR_STORE_AVAILABLE or self.vectorstore is None:
            # 使用 BM25
            results = self.bm25_retriever.search(query, top_k)
            return [
                (Document(
                    page_content=self.bm25_retriever.documents[idx].get(
                        "content", ""),
                    metadata=self.bm25_retriever.documents[idx].get(
                        "metadata", {})
                ), score)
                for idx, score in results
            ]

        try:
            docs_with_scores = self.vectorstore.similarity_search_with_score(
                query, k=top_k)
            return docs_with_scores
        except Exception as e:
            print(f"检索文档时出错: {e}")
            return []

    def get_stats(self) -> dict:
        """
        获取知识库统计信息

        Returns:
            统计信息字典
        """
        stats = {
            "vector_store_available": VECTOR_STORE_AVAILABLE,
            "knowledge_dir": self.knowledge_dir,
            "persist_directory": self.persist_directory,
            "document_count": 0,
            "bm25_document_count": len(self.bm25_retriever.documents)
        }

        if VECTOR_STORE_AVAILABLE and self.vectorstore is not None:
            try:
                stats["document_count"] = self.vectorstore._collection.count()
            except Exception:
                pass

        # 统计源文件
        if os.path.exists(self.knowledge_dir):
            files = []
            for f in os.listdir(self.knowledge_dir):
                if f.lower().endswith(('.pdf', '.docx', '.doc')):
                    files.append(f)
            stats["source_files"] = files

        return stats


class KnowledgeSearchTool(BaseTool):
    """知识库检索工具"""

    name: str = "knowledge_search"
    description: str = (
        "从业务知识库中检索相关知识内容。"
        "用于查找与命题相关的知识点、教材内容、考纲要求等。"
        "当需要获取特定知识点的详细信息时使用此工具。"
    )
    args_schema: Type[BaseModel] = KnowledgeBaseInput

    retriever: Optional[KnowledgeBaseRetriever] = None

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.retriever = KnowledgeBaseRetriever()

    def _run(self, query: str, top_k: int = 3) -> str:
        """执行知识检索"""
        if self.retriever is None:
            return "知识库检索功能不可用，请确保安装了相关依赖。"

        docs = self.retriever.retrieve(query, top_k, method="hybrid")

        if not docs:
            return f"未找到与 '{query}' 相关的知识内容。"

        result = f"找到 {len(docs)} 条相关知识：\n\n"
        for i, doc in enumerate(docs, 1):
            result += f"【知识片段 {i}】\n"
            result += f"来源: {doc.metadata.get('source', '未知')}\n"
            result += f"内容: {doc.page_content[:500]}...\n\n"

        return result


class AddDocumentTool(BaseTool):
    """添加文档到知识库工具"""

    name: str = "add_document"
    description: str = (
        "将新文档添加到知识库中。"
        "支持 PDF 和 DOCX 格式的文档。"
        "当用户上传新的知识文档时使用此工具。"
    )

    retriever: Optional[KnowledgeBaseRetriever] = None

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.retriever = KnowledgeBaseRetriever()

    def _run(self, file_path: str) -> str:
        """添加文档"""
        if self.retriever is None:
            return "知识库功能不可用，请确保安装了相关依赖。"

        if not os.path.exists(file_path):
            return f"文件不存在: {file_path}"

        success = self.retriever.add_documents(file_path)

        if success:
            return f"成功添加文档: {file_path}"
        else:
            return f"添加文档失败: {file_path}"


def get_knowledge_tools() -> list:
    """
    获取所有知识库相关工具

    Returns:
        知识库工具列表
    """
    return [
        KnowledgeSearchTool(),
        AddDocumentTool()
    ]


# 全局单例
_retriever_instance = None


def get_retriever() -> KnowledgeBaseRetriever:
    """获取全局检索器实例"""
    global _retriever_instance
    if _retriever_instance is None:
        _retriever_instance = KnowledgeBaseRetriever()
    return _retriever_instance


def search_knowledge(query: str, top_k: int = 3, method: str = "hybrid") -> str:
    """
    便捷函数：检索知识

    Args:
        query: 查询字符串
        top_k: 返回数量
        method: 检索方法 (vector, bm25, hybrid)

    Returns:
        检索结果字符串
    """
    retriever = get_retriever()
    docs = retriever.retrieve(query, top_k, method=method)

    if not docs:
        return ""

    return "\n\n".join([doc.page_content for doc in docs])
