"""
记忆沉淀 Agent (Consolidator Agent)

在任务成功完成后，总结本次对话中的用户新偏好或成功的命题经验，
并将其写入长期记忆，实现 Agent 的自我进化。
"""

import json
import re
from typing import Dict, Any, Optional, List
from langchain_core.language_models import BaseChatModel
from langchain_core.output_parsers import StrOutputParser
from langchain_openai import ChatOpenAI

from graphs.state import AgentState, add_status_message
from utils.prompts import CONSOLIDATOR_PROMPT
from tools.memory_tools import save_memory
from utils.config import get_llm


class ConsolidatorAgent:
    """
    记忆沉淀 Agent

    从任务执行过程中提炼有价值的记忆并保存。
    """

    def __init__(self, llm: Optional[BaseChatModel] = None):
        """
        初始化记忆沉淀 Agent

        Args:
            llm: 语言模型实例
        """
        self.llm = llm or get_llm(temperature=0)

    def _parse_memories(self, response: str) -> List[Dict[str, Any]]:
        """
        解析记忆提炼结果

        Args:
            response: LLM 返回的响应

        Returns:
            记忆列表
        """
        # 尝试提取 JSON
        json_match = re.search(r'\{[\s\S]*\}', response)
        if json_match:
            try:
                result = json.loads(json_match.group())
                return result.get("memories", [])
            except json.JSONDecodeError:
                pass

        return []

    def consolidate(
        self,
        user_input: str,
        extracted_params: Dict[str, Any],
        questions: List[Dict[str, Any]],
        audit_feedback: str = ""
    ) -> List[Dict[str, Any]]:
        """
        提炼记忆

        Args:
            user_input: 用户原始输入
            extracted_params: 提取的命题参数
            questions: 生成的试题
            audit_feedback: 审核反馈

        Returns:
            需要保存的记忆列表
        """
        # 构建执行摘要
        execution_summary = f"成功生成 {len(questions)} 道试题"
        if audit_feedback:
            execution_summary += f"，审核反馈: {audit_feedback}"

        # 构建并执行链
        chain = CONSOLIDATOR_PROMPT | self.llm | StrOutputParser()

        try:
            response = chain.invoke({
                "user_input": user_input,
                "extracted_params": json.dumps(extracted_params, ensure_ascii=False),
                "execution_summary": execution_summary
            })
            return self._parse_memories(response)
        except Exception as e:
            print(f"记忆提炼出错: {e}")
            return []

    def save_memories(self, memories: List[Dict[str, Any]]) -> int:
        """
        保存记忆到存储

        Args:
            memories: 记忆列表

        Returns:
            成功保存的记忆数量
        """
        saved_count = 0
        for mem in memories:
            try:
                save_memory(
                    content=mem.get("content", ""),
                    memory_type=mem.get("type", "task_experience"),
                    metadata=mem.get("metadata", {})
                )
                saved_count += 1
            except Exception as e:
                print(f"保存记忆出错: {e}")

        return saved_count


def consolidator_node(state: AgentState) -> AgentState:
    """
    记忆沉淀节点

    在任务完成后总结经验并保存到长期记忆。

    Args:
        state: 当前状态

    Returns:
        更新后的状态
    """
    new_state = add_status_message(state, "💾 正在保存本次经验...")

    # 创建记忆沉淀 Agent
    agent = ConsolidatorAgent()

    # 提炼记忆
    memories = agent.consolidate(
        user_input=state["user_input"],
        extracted_params=state["extracted_params"],
        questions=state["draft_questions"],
        audit_feedback=state.get("audit_feedback", "")
    )

    # 保存记忆
    saved_count = 0
    if memories:
        saved_count = agent.save_memories(memories)

    # 生成最终响应
    from agents.executor_agent import format_questions_response
    final_response = format_questions_response(state["draft_questions"])

    # 更新状态
    new_state = dict(new_state)
    new_state["final_response"] = final_response
    new_state["next_node"] = "end"
    new_state["should_continue"] = False
    new_state["current_step_index"] = 4
    new_state["current_step"] = "完成"

    if saved_count > 0:
        new_state = add_status_message(new_state, f"📝 已保存 {saved_count} 条经验到记忆库")
    else:
        new_state = add_status_message(new_state, "📝 本次无需保存新记忆")

    new_state = add_status_message(new_state, "🎉 命题任务完成!")

    return new_state


def chat_reply_node(state: AgentState) -> AgentState:
    """
    闲聊回复节点

    处理非命题意图的用户输入。

    Args:
        state: 当前状态

    Returns:
        更新后的状态
    """
    from utils.prompts import CHAT_PROMPT
    from utils.config import get_llm

    llm = get_llm(temperature=0.7)

    # 构建对话历史
    chat_history = []
    for msg in state["chat_history"][-5:]:  # 最近 5 轮
        role = "human" if msg["role"] in ("user", "human") else "ai"
        chat_history.append((role, msg["content"]))

    chain = CHAT_PROMPT | llm

    try:
        response = chain.invoke({
            "chat_history": chat_history,
            "user_input": state["user_input"]
        })
        final_response = response.content
    except Exception as e:
        import traceback
        print(f"[ERROR] chat_reply_node in consolidator 异常: {e}")
        traceback.print_exc()
        final_response = "您好！我是 IntelliExam 命题助手，可以帮助您生成各类试题。请告诉我您需要什么类型的题目？"

    # 更新状态
    new_state = dict(state)
    new_state["final_response"] = final_response
    new_state["next_node"] = "end"
    new_state["should_continue"] = False

    new_state = add_status_message(new_state, "💬 生成回复")

    return new_state
