"""
入口路由 Agent (ReAct Router Agent)

负责意图识别与分发，是系统的第一层入口。
分析用户输入，判断意图类型，并将请求路由到相应的处理流程。

核心功能：双层意图判断
1. primary_intent：当前输入的主要意图
2. proposition_needed：是否需要调用命题 Agent
"""

import json
import re
from typing import Dict, Any, Optional
from langchain_core.language_models import BaseChatModel
from langchain_core.output_parsers import StrOutputParser
from langchain_openai import ChatOpenAI

from graphs.state import AgentState, add_status_message
from utils.prompts import ROUTER_PROMPT
from utils.config import get_llm


class RouterAgent:
    """
    入口路由 Agent

    使用 ReAct 模式分析用户意图，决定路由方向。
    """

    def __init__(self, llm: Optional[BaseChatModel] = None):
        """
        初始化路由 Agent

        Args:
            llm: 语言模型实例，如果不提供则使用默认配置
        """
        self.llm = llm or get_llm(temperature=0)
        self.chain = ROUTER_PROMPT | self.llm | StrOutputParser()

    def _parse_routing_result(self, response: str) -> Dict[str, Any]:
        """
        解析路由结果

        Args:
            response: LLM 返回的响应

        Returns:
            解析后的路由结果字典
        """
        # 尝试提取 JSON
        json_match = re.search(r'\{[\s\S]*\}', response)
        if json_match:
            try:
                result = json.loads(json_match.group())
                return {
                    "primary_intent": result.get("primary_intent", "chat"),
                    "proposition_needed": result.get("proposition_needed", False),
                    "proposition_context": result.get("proposition_context", ""),
                    "mode_transition": result.get("mode_transition", "none"),
                    "reason": result.get("reason", "")
                }
            except json.JSONDecodeError:
                pass

        # 如果无法解析，使用关键词匹配作为后备
        response_lower = response.lower()
        return self._keyword_fallback(response_lower)

    def _keyword_fallback(self, text_lower: str) -> Dict[str, Any]:
        """
        基于关键词的备用路由判断

        Args:
            text_lower: 小写化的用户输入

        Returns:
            路由结果字典
        """
        # 命题关键词
        proposition_keywords = ["出题", "命题", "生成试题", "考题", "练习题",
                                "出一道", "帮我出", "生成几道", "生成一道",
                                "再来", "继续"]
        # 阅卷关键词
        grading_keywords = ["阅卷", "评分", "批改", "打分", "判断对错"]
        # 退出关键词
        exit_keywords = ["好了", "可以了", "就这些", "完成", "结束"]

        if any(kw in text_lower for kw in proposition_keywords):
            return {
                "primary_intent": "proposition",
                "proposition_needed": True,
                "proposition_context": "",
                "mode_transition": "enter",
                "reason": "关键词匹配：命题相关"
            }
        elif any(kw in text_lower for kw in grading_keywords):
            return {
                "primary_intent": "grading",
                "proposition_needed": False,
                "proposition_context": "",
                "mode_transition": "none",
                "reason": "关键词匹配：阅卷相关"
            }
        elif any(kw in text_lower for kw in exit_keywords):
            return {
                "primary_intent": "chat",
                "proposition_needed": False,
                "proposition_context": "",
                "mode_transition": "exit",
                "reason": "关键词匹配：退出命题模式"
            }
        else:
            return {
                "primary_intent": "chat",
                "proposition_needed": False,
                "proposition_context": "",
                "mode_transition": "none",
                "reason": "默认：普通对话"
            }

    def route(self, user_input: str, chat_history: list = None, current_mode: str = "chat") -> Dict[str, Any]:
        """
        执行路由判断

        Args:
            user_input: 用户输入
            chat_history: 对话历史（可选）
            current_mode: 当前会话模式（可选）

        Returns:
            路由结果，包含分层意图信息
        """
        try:
            # 格式化对话历史
            history_str = self._format_chat_history(
                chat_history) if chat_history else "无"

            response = self.chain.invoke({
                "user_input": user_input,
                "chat_history": history_str,
                "current_mode": current_mode
            })
            return self._parse_routing_result(response)
        except Exception as e:
            print(f"路由判断出错: {e}")
            # 出错时默认为聊天
            return {
                "primary_intent": "chat",
                "proposition_needed": False,
                "proposition_context": "",
                "mode_transition": "none",
                "reason": f"路由出错，默认为聊天: {str(e)}"
            }

    def _format_chat_history(self, chat_history: list) -> str:
        """格式化对话历史用于 Prompt"""
        if not chat_history:
            return "无"

        lines = []
        for msg in chat_history[-6:]:  # 最近 6 条
            role = msg.get("role", "unknown")
            content = msg.get("content", "")[:100]  # 截断
            role_name = "用户" if role == "user" else "助手"
            lines.append(f"{role_name}: {content}")

        return "\n".join(lines)


def router_node(state: AgentState) -> AgentState:
    """
    路由节点函数

    LangGraph 工作流中使用的节点函数。
    分析用户意图并更新状态，支持双层意图判断。

    Args:
        state: 当前状态

    Returns:
        更新后的状态
    """
    new_state = add_status_message(state, "正在分析用户意图...")

    # 创建路由 Agent 并执行
    agent = RouterAgent()

    # 获取对话历史和当前模式
    chat_history = state.get("chat_history", [])
    current_mode = state.get("current_mode", "chat")

    result = agent.route(
        state["user_input"],
        chat_history=chat_history,
        current_mode=current_mode
    )

    # 更新状态
    new_state = dict(new_state)
    new_state["primary_intent"] = result["primary_intent"]
    new_state["proposition_needed"] = result["proposition_needed"]
    new_state["proposition_context"] = result["proposition_context"]
    new_state["mode_transition"] = result["mode_transition"]
    new_state["routing_reason"] = result["reason"]

    # 更新当前模式
    if result["mode_transition"] == "enter":
        new_state["current_mode"] = "proposition"
    elif result["mode_transition"] == "exit":
        new_state["current_mode"] = "chat"

    # 兼容旧版 intent 字段
    new_state["intent"] = result["primary_intent"]

    # 根据 proposition_needed 设置下一个节点
    if result["proposition_needed"]:
        new_state["next_node"] = "memory_recall"
        new_state = add_status_message(
            new_state, f"意图识别：命题需求 (模式: {result['mode_transition']})")
    else:
        new_state["next_node"] = "chat_reply"
        new_state = add_status_message(new_state, f"意图识别：闲聊模式")

    return new_state


# 简单的意图判断函数（用于快速判断，不调用 LLM）
def quick_intent_check(user_input: str) -> str:
    """
    快速意图检查

    使用关键词匹配进行快速的意图判断，
    适用于简单场景或作为 LLM 判断的前置过滤。

    Args:
        user_input: 用户输入

    Returns:
        意图类型
    """
    keywords_proposition = ["出题", "命题", "生成试题", "考题", "练习题", "测试题",
                            "出一套", "帮我出", "生成几道", "生成一道", "继续", "再来"]
    keywords_grading = ["阅卷", "评分", "批改", "打分", "判断对错", "这题对不对"]

    user_input_lower = user_input.lower()

    if any(kw in user_input_lower for kw in keywords_proposition):
        return "proposition"
    elif any(kw in user_input_lower for kw in keywords_grading):
        return "grading"
    else:
        return "chat"
