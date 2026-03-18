"""
记忆认知 Agent (Memory Cognitive Agent)

系统的核心 Agent，负责替代传统槽位填充。
利用长期记忆和上下文推理需求，智能补全用户未明确的参数。
"""

import json
import re
from typing import Dict, Any, Optional, List
from langchain_core.language_models import BaseChatModel
from langchain_core.output_parsers import StrOutputParser
from langchain_openai import ChatOpenAI

from graphs.state import AgentState, add_status_message, ExtractedParams
from utils.prompts import MEMORY_COGNITIVE_PROMPT
from tools.memory_tools import retrieve_memory, get_user_preferences
from utils.config import get_llm


class MemoryCognitiveAgent:
    """
    记忆认知 Agent

    结合长期记忆和对话上下文，智能分析用户需求。
    """

    def __init__(self, llm: Optional[BaseChatModel] = None):
        """
        初始化记忆认知 Agent

        Args:
            llm: 语言模型实例
        """
        self.llm = llm or get_llm(temperature=0)

    def _format_long_term_memory(self, memories: List[Dict]) -> str:
        """
        格式化长期记忆用于 Prompt

        Args:
            memories: 记忆列表

        Returns:
            格式化的记忆字符串
        """
        if not memories:
            return "暂无相关历史记忆。"

        result = []
        for mem in memories[:5]:  # 最多使用 5 条记忆
            mem_type = mem.get("type", "unknown")
            content = mem.get("content", "")
            result.append(f"- [{mem_type}] {content}")

        return "\n".join(result)

    def _format_chat_history(self, history: List[Dict]) -> str:
        """
        格式化对话历史

        Args:
            history: 对话历史列表

        Returns:
            格式化的对话历史字符串
        """
        if not history:
            return "这是对话的开始。"

        result = []
        for msg in history[-10:]:  # 最近 10 轮对话
            role = msg.get("role", "unknown")
            content = msg.get("content", "")
            role_name = "用户" if role == "user" else "助手"
            result.append(f"{role_name}: {content}")

        return "\n".join(result)

    def _parse_cognitive_result(self, response: str) -> Dict[str, Any]:
        """
        解析认知分析结果

        Args:
            response: LLM 返回的响应

        Returns:
            解析后的结果字典
        """
        # 尝试提取 JSON
        json_match = re.search(r'\{[\s\S]*\}', response)
        if json_match:
            try:
                result = json.loads(json_match.group())

                # 确保所有必要字段存在
                return {
                    "is_complete": result.get("is_complete", False),
                    "extracted_params": result.get("extracted_params", {
                        "topic": "",
                        "question_type": "",
                        "difficulty": "",
                        "count": 0,
                        "additional_requirements": ""
                    }),
                    "missing_info": result.get("missing_info", []),
                    "follow_up_question": result.get("follow_up_question", "")
                }
            except json.JSONDecodeError:
                pass

        # 解析失败，返回默认值
        return {
            "is_complete": False,
            "extracted_params": {
                "topic": "",
                "question_type": "",
                "difficulty": "",
                "count": 0,
                "additional_requirements": ""
            },
            "missing_info": ["无法解析需求"],
            "follow_up_question": "抱歉，我需要更多信息来帮助您。请告诉我您想要出什么类型的题目？"
        }

    def analyze(
        self,
        user_input: str,
        chat_history: List[Dict],
        long_term_memory: List[Dict] = None
    ) -> Dict[str, Any]:
        """
        分析用户需求

        Args:
            user_input: 用户输入
            chat_history: 对话历史
            long_term_memory: 长期记忆（如果未提供则自动检索）

        Returns:
            分析结果
        """
        # 如果没有提供长期记忆，自动检索
        if long_term_memory is None:
            long_term_memory = retrieve_memory(user_input, top_k=5)

        # 格式化输入
        memory_str = self._format_long_term_memory(long_term_memory)
        history_str = self._format_chat_history(chat_history)

        # 构建并执行链
        chain = MEMORY_COGNITIVE_PROMPT | self.llm | StrOutputParser()

        try:
            response = chain.invoke({
                "long_term_memory": memory_str,
                "chat_history": history_str,
                "user_input": user_input
            })
            return self._parse_cognitive_result(response)
        except Exception as e:
            print(f"需求分析出错: {e}")
            return {
                "is_complete": False,
                "extracted_params": {},
                "missing_info": ["分析出错"],
                "follow_up_question": "抱歉，我在分析您的需求时遇到了问题。请您再详细描述一下您需要的题目类型？"
            }


def memory_recall_node(state: AgentState) -> AgentState:
    """
    记忆召回节点

    从长期记忆中检索相关的用户偏好和历史经验。

    Args:
        state: 当前状态

    Returns:
        更新后的状态
    """
    new_state = add_status_message(state, "💡 正在回忆您的偏好...")

    # 检索长期记忆
    memories = retrieve_memory(state["user_input"], top_k=5)

    # 同时获取用户偏好摘要
    preferences = get_user_preferences()

    # 更新状态
    new_state = dict(new_state)
    new_state["retrieved_long_term_memory"] = memories

    if preferences:
        pref_str = ", ".join([f"{k}: {v}" for k, v in preferences.items()])
        new_state = add_status_message(new_state, f"📝 找到偏好: [{pref_str}]")

    return new_state


def cognitive_node(state: AgentState) -> AgentState:
    """
    认知分析节点

    分析用户需求，判断是否完整，并决定后续行动。

    Args:
        state: 当前状态

    Returns:
        更新后的状态
    """
    new_state = add_status_message(state, "🔍 正在分析需求完整性...")

    # 创建认知 Agent 并分析
    agent = MemoryCognitiveAgent()
    result = agent.analyze(
        user_input=state["user_input"],
        chat_history=state["chat_history"],
        long_term_memory=state["retrieved_long_term_memory"]
    )

    # 更新状态
    new_state = dict(new_state)
    new_state["is_info_complete"] = result["is_complete"]
    new_state["extracted_params"] = result["extracted_params"]
    new_state["missing_info"] = result["missing_info"]
    new_state["follow_up_question"] = result["follow_up_question"]

    # 根据需求完整性决定下一步
    if result["is_complete"]:
        new_state["next_node"] = "planner"
        params = result["extracted_params"]
        new_state = add_status_message(
            new_state,
            f"✅ 需求完整: 知识点={params.get('topic')}, "
            f"题型={params.get('question_type')}, "
            f"难度={params.get('difficulty')}, "
            f"数量={params.get('count')}"
        )
    else:
        new_state["next_node"] = "ask_user"
        missing = result["missing_info"]
        new_state = add_status_message(
            new_state,
            f"❓ 信息不完整，缺失: {', '.join(missing)}"
        )

    return new_state


def ask_user_node(state: AgentState) -> AgentState:
    """
    追问用户节点

    当需求不完整时，向用户追问缺失的信息。

    Args:
        state: 当前状态

    Returns:
        更新后的状态
    """
    new_state = dict(state)

    # 设置追问响应
    new_state["final_response"] = state["follow_up_question"]
    new_state["next_node"] = "end"
    new_state["should_continue"] = False

    new_state = add_status_message(new_state, f"🤔 向用户追问: {state['follow_up_question']}")

    return new_state
