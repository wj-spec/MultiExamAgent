"""
记忆管理子系统

管理本地 JSON 文件的读写，实现长期记忆的存储、检索和管理。
支持关键词匹配、BM25检索和简单的向量相似度检索。
"""

import json
import os
from datetime import datetime
from typing import List, Optional, Dict, Any, Set
import uuid
import re
import math
from collections import defaultdict


class BM25:
    """
    BM25 检索算法实现

    用于基于关键词的文档检索，比简单的关键词匹配更精确。
    """

    def __init__(self, k1: float = 1.5, b: float = 0.75):
        """
        初始化 BM25

        Args:
            k1: 词频饱和参数
            b: 文档长度归一化参数
        """
        self.k1 = k1
        self.b = b
        self.doc_freqs: Dict[str, int] = defaultdict(int)
        self.doc_lens: List[int] = []
        self.doc_term_freqs: List[Dict[str, int]] = []
        self.avgdl: float = 0
        self.n_docs: int = 0

    def fit(self, documents: List[List[str]]):
        """
        训练 BM25 模型

        Args:
            documents: 分词后的文档列表
        """
        self.n_docs = len(documents)
        self.doc_lens = [len(doc) for doc in documents]
        self.avgdl = sum(self.doc_lens) / self.n_docs if self.n_docs > 0 else 0

        self.doc_term_freqs = []
        self.doc_freqs = defaultdict(int)

        for doc in documents:
            term_freqs = defaultdict(int)
            for term in doc:
                term_freqs[term] += 1
            self.doc_term_freqs.append(dict(term_freqs))

            # 计算文档频率
            for term in set(doc):
                self.doc_freqs[term] += 1

    def _idf(self, term: str) -> float:
        """计算逆文档频率"""
        df = self.doc_freqs.get(term, 0)
        return math.log((self.n_docs - df + 0.5) / (df + 0.5) + 1)

    def score(self, query: List[str], doc_idx: int) -> float:
        """
        计算查询与文档的 BM25 分数

        Args:
            query: 分词后的查询
            doc_idx: 文档索引

        Returns:
            BM25 分数
        """
        score = 0.0
        doc_len = self.doc_lens[doc_idx]
        term_freqs = self.doc_term_freqs[doc_idx]

        for term in query:
            if term not in term_freqs:
                continue

            tf = term_freqs[term]
            idf = self._idf(term)

            # BM25 公式
            numerator = tf * (self.k1 + 1)
            denominator = tf + self.k1 * \
                (1 - self.b + self.b * doc_len / self.avgdl)
            score += idf * numerator / denominator

        return score

    def search(self, query: List[str], top_k: int = 5) -> List[tuple]:
        """
        搜索最相关的文档

        Args:
            query: 分词后的查询
            top_k: 返回的最大数量

        Returns:
            (文档索引, 分数) 元组列表
        """
        scores = []
        for i in range(self.n_docs):
            score = self.score(query, i)
            if score > 0:
                scores.append((i, score))

        scores.sort(key=lambda x: x[1], reverse=True)
        return scores[:top_k]


class MemoryManager:
    """
    长期记忆管理器

    负责管理存储在本地的 JSON 格式长期记忆数据，
    提供记忆的存储、检索、更新和删除功能。
    支持 BM25 检索和关键词匹配。
    """

    # 停用词表
    STOP_WORDS: Set[str] = {
        '的', '是', '在', '了', '和', '与', '或', '有', '对', '为', '这', '那',
        '我', '你', '他', '她', '它', '们', '着', '过', '会', '能', '要', '就',
        '都', '也', '还', '又', '很', '但', '而', '不', '没', '到', '把', '被',
        '让', '给', '从', '向', '以', '如', '等', '及', '或', '和', '与'
    }

    def __init__(self, memory_file: str = None):
        """
        初始化记忆管理器

        Args:
            memory_file: 记忆文件路径，默认为 data/memory/long_term_memory.json
        """
        if memory_file is None:
            # 获取项目根目录
            current_dir = os.path.dirname(os.path.abspath(__file__))
            project_root = os.path.dirname(current_dir)
            memory_file = os.path.join(
                project_root, "data", "memory", "long_term_memory.json")

        self.memory_file = memory_file
        self._bm25: Optional[BM25] = None
        self._bm25_docs: List[List[str]] = []
        self._ensure_memory_file()

    def _ensure_memory_file(self):
        """确保记忆文件存在"""
        os.makedirs(os.path.dirname(self.memory_file), exist_ok=True)
        if not os.path.exists(self.memory_file):
            with open(self.memory_file, 'w', encoding='utf-8') as f:
                json.dump([], f, ensure_ascii=False, indent=2)

    def _load_memories(self) -> List[Dict[str, Any]]:
        """加载所有记忆"""
        try:
            with open(self.memory_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        except (json.JSONDecodeError, FileNotFoundError):
            return []

    def _save_memories(self, memories: List[Dict[str, Any]]):
        """保存所有记忆"""
        with open(self.memory_file, 'w', encoding='utf-8') as f:
            json.dump(memories, f, ensure_ascii=False, indent=2)

    def _extract_keywords(self, text: str) -> List[str]:
        """
        提取关键词

        支持中英文混合文本的关键词提取

        Args:
            text: 输入文本

        Returns:
            关键词列表
        """
        if not text:
            return []

        # 移除标点符号，保留中英文和数字
        text = re.sub(r'[^\w\s\u4e00-\u9fff]', ' ', text)

        # 分词（简单按空格分割）
        words = text.split()

        # 过滤停用词和短词
        keywords = []
        for w in words:
            w_lower = w.lower()
            if w_lower not in self.STOP_WORDS and len(w) > 1:
                keywords.append(w_lower)

        # 对于中文文本，进行简单的字符级分词（可选）
        # 这里保持词级分词，因为大多数情况下输入已经是分词后的

        return keywords

    def _init_bm25(self, memories: List[Dict[str, Any]]):
        """
        初始化 BM25 模型

        Args:
            memories: 记忆列表
        """
        self._bm25_docs = []
        for mem in memories:
            content = mem.get("content", "")
            # 合并内容和关键词
            keywords = mem.get("keywords", [])
            all_terms = self._extract_keywords(content) + keywords
            self._bm25_docs.append(all_terms)

        self._bm25 = BM25()
        self._bm25.fit(self._bm25_docs)

    def save_memory(
        self,
        content: str,
        memory_type: str = "task_experience",
        metadata: Dict[str, Any] = None,
        keywords: List[str] = None
    ) -> Dict[str, Any]:
        """
        保存新记忆

        Args:
            content: 记忆内容
            memory_type: 记忆类型 (user_preference, task_experience, feedback)
            metadata: 元数据
            keywords: 关键词列表（如果不提供，则自动提取）

        Returns:
            保存的记忆项
        """
        memories = self._load_memories()

        # 自动提取关键词
        if keywords is None:
            keywords = self._extract_keywords(content)

        memory_item = {
            "id": f"mem_{uuid.uuid4().hex[:8]}",
            "timestamp": datetime.now().isoformat(),
            "type": memory_type,
            "content": content,
            "keywords": keywords[:20],  # 最多保存20个关键词
            "metadata": metadata or {}
        }

        memories.append(memory_item)
        self._save_memories(memories)

        # 重置 BM25 模型（下次检索时会重新初始化）
        self._bm25 = None

        return memory_item

    def retrieve_memory(
        self,
        query: str,
        top_k: int = 5,
        memory_type: Optional[str] = None,
        use_bm25: bool = True
    ) -> List[Dict[str, Any]]:
        """
        检索相关记忆

        优先使用 BM25 检索，返回最相关的记忆项。

        Args:
            query: 查询字符串
            top_k: 返回的最大数量
            memory_type: 可选的记忆类型过滤
            use_bm25: 是否使用 BM25 检索

        Returns:
            相关记忆列表
        """
        memories = self._load_memories()

        # 类型过滤
        if memory_type:
            memories = [m for m in memories if m.get("type") == memory_type]

        if not memories:
            return []

        if use_bm25 and len(memories) > 0:
            return self._retrieve_bm25(query, memories, top_k)
        else:
            return self._retrieve_keyword(query, memories, top_k)

    def _retrieve_bm25(
        self,
        query: str,
        memories: List[Dict[str, Any]],
        top_k: int
    ) -> List[Dict[str, Any]]:
        """
        使用 BM25 检索

        Args:
            query: 查询字符串
            memories: 记忆列表
            top_k: 返回数量

        Returns:
            相关记忆列表
        """
        # 初始化 BM25（懒加载）
        if self._bm25 is None:
            self._init_bm25(memories)

        # 提取查询关键词
        query_terms = self._extract_keywords(query)

        if not query_terms:
            return memories[:top_k]

        # BM25 检索
        results = self._bm25.search(query_terms, top_k)

        # 返回结果
        return [memories[idx] for idx, _ in results]

    def _retrieve_keyword(
        self,
        query: str,
        memories: List[Dict[str, Any]],
        top_k: int
    ) -> List[Dict[str, Any]]:
        """
        使用关键词匹配检索（备选方案）

        Args:
            query: 查询字符串
            memories: 记忆列表
            top_k: 返回数量

        Returns:
            相关记忆列表
        """
        query_keywords = self._extract_keywords(query)

        if not query_keywords:
            return memories[:top_k]

        # 计算相关性分数
        scored_memories = []
        for memory in memories:
            content = memory.get("content", "")
            memory_keywords = memory.get(
                "keywords", self._extract_keywords(content))

            # 计算关键词重叠率
            common_keywords = set(query_keywords) & set(memory_keywords)
            if common_keywords:
                score = len(common_keywords) / max(len(query_keywords), 1)
                # 考虑时间因素
                time_factor = self._get_time_factor(
                    memory.get("timestamp", ""))
                final_score = score * time_factor
                scored_memories.append((final_score, memory))

        # 按分数排序并返回 top_k
        scored_memories.sort(key=lambda x: x[0], reverse=True)
        return [m for _, m in scored_memories[:top_k]]

    def _get_time_factor(self, timestamp: str) -> float:
        """
        计算时间因子

        较新的记忆获得稍高的权重

        Args:
            timestamp: ISO 格式的时间戳

        Returns:
            时间因子 (0.8 - 1.0)
        """
        try:
            memory_time = datetime.fromisoformat(timestamp)
            now = datetime.now()
            days_diff = (now - memory_time).days

            # 30 天内权重递减
            if days_diff < 30:
                return 1.0 - (days_diff / 150)  # 0.8 - 1.0
            return 0.8
        except (ValueError, TypeError):
            return 0.9

    def get_all_memories(
        self,
        memory_type: Optional[str] = None,
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """
        获取所有记忆（用于后台管理查看）

        Args:
            memory_type: 可选的类型过滤
            limit: 返回数量限制

        Returns:
            记忆列表
        """
        memories = self._load_memories()

        if memory_type:
            memories = [m for m in memories if m.get("type") == memory_type]

        # 按时间倒序排列
        memories.sort(key=lambda x: x.get("timestamp", ""), reverse=True)

        return memories[:limit]

    def get_memory_by_id(self, memory_id: str) -> Optional[Dict[str, Any]]:
        """
        根据 ID 获取记忆

        Args:
            memory_id: 记忆 ID

        Returns:
            记忆项或 None
        """
        memories = self._load_memories()
        for memory in memories:
            if memory.get("id") == memory_id:
                return memory
        return None

    def update_memory(
        self,
        memory_id: str,
        content: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
        keywords: Optional[List[str]] = None
    ) -> Optional[Dict[str, Any]]:
        """
        更新记忆

        Args:
            memory_id: 记忆 ID
            content: 新内容
            metadata: 新元数据（会合并到现有元数据）
            keywords: 新关键词列表

        Returns:
            更新后的记忆项或 None
        """
        memories = self._load_memories()

        for i, memory in enumerate(memories):
            if memory.get("id") == memory_id:
                if content is not None:
                    memories[i]["content"] = content
                    # 更新关键词
                    if keywords is None:
                        keywords = self._extract_keywords(content)
                    memories[i]["keywords"] = keywords[:20]
                elif keywords is not None:
                    memories[i]["keywords"] = keywords[:20]

                if metadata is not None:
                    memories[i]["metadata"].update(metadata)
                memories[i]["updated_at"] = datetime.now().isoformat()

                self._save_memories(memories)
                # 重置 BM25 模型
                self._bm25 = None
                return memories[i]

        return None

    def delete_memory(self, memory_id: str) -> bool:
        """
        删除记忆

        Args:
            memory_id: 记忆 ID

        Returns:
            是否成功删除
        """
        memories = self._load_memories()
        initial_len = len(memories)

        memories = [m for m in memories if m.get("id") != memory_id]

        if len(memories) < initial_len:
            self._save_memories(memories)
            self._bm25 = None
            return True

        return False

    def clear_all_memories(self) -> int:
        """
        清除所有记忆（谨慎使用）

        Returns:
            删除的记忆数量
        """
        memories = self._load_memories()
        count = len(memories)

        self._save_memories([])
        self._bm25 = None

        return count

    def get_user_preferences(self) -> Dict[str, Any]:
        """
        获取用户偏好摘要

        Returns:
            用户偏好字典
        """
        preference_memories = self.get_all_memories(
            memory_type="user_preference")

        preferences = {}
        for memory in preference_memories:
            content = memory.get("content", "")
            # 简单解析偏好（可以扩展为更复杂的解析逻辑）
            if "难度" in content:
                if "困难" in content or "高" in content:
                    preferences["difficulty"] = "hard"
                elif "中等" in content:
                    preferences["difficulty"] = "medium"
                elif "简单" in content or "低" in content:
                    preferences["difficulty"] = "easy"
            if "题型" in content:
                if "选择题" in content:
                    preferences["question_type"] = "choice"
                elif "填空题" in content:
                    preferences["question_type"] = "fill_blank"
                elif "解答题" in content:
                    preferences["question_type"] = "essay"

        return preferences

    def get_statistics(self) -> Dict[str, Any]:
        """
        获取记忆统计信息

        Returns:
            统计信息字典
        """
        memories = self._load_memories()

        type_counts = {}
        keyword_count = 0
        for memory in memories:
            mem_type = memory.get("type", "unknown")
            type_counts[mem_type] = type_counts.get(mem_type, 0) + 1
            keyword_count += len(memory.get("keywords", []))

        return {
            "total_count": len(memories),
            "type_counts": type_counts,
            "total_keywords": keyword_count,
            "file_path": self.memory_file
        }


# 全局单例
_memory_manager_instance = None


def get_memory_manager() -> MemoryManager:
    """获取全局记忆管理器实例"""
    global _memory_manager_instance
    if _memory_manager_instance is None:
        _memory_manager_instance = MemoryManager()
    return _memory_manager_instance
