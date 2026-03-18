"""
入口路由 Agent (ReAct Router Agent)

负责意图识别与分发，是系统的第一层入口。
分析用户输入，判断意图类型，并将请求路由到相应的处理流程。
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
        json_match = re.search(r'\{[^}]+\}', response, re.DOTALL)
        if json_match:
            try:
                result = json.loads(json_match.group())
                return {
                    "intent": result.get("intent", "chat"),
                    "reason": result.get("reason", "")
                }
            except json.JSONDecodeError:
                pass

        # 如果无法解析，使用关键词匹配作为后备
        response_lower = response.lower()
        if any(kw in response_lower for kw in ["出题", "命题", "生成试题", "考题"]):
            return {"intent": "proposition", "reason": "关键词匹配：命题相关"}
        elif any(kw in response_lower for kw in ["阅卷", "评分", "批改"]):
            return {"intent": "grading", "reason": "关键词匹配：阅卷相关"}
        else:
            return {"intent": "chat", "reason": "默认：普通对话"}

    def route(self, user_input: str) -> Dict[str, Any]:
        """
        执行路由判断

        Args:
            user_input: 用户输入

        Returns:
            路由结果，包含 intent 和 reason
        """
        try:
            response = self.chain.invoke({"user_input": user_input})
            return self._parse_routing_result(response)
        except Exception as e:
            print(f"路由判断出错: {e}")
            # 出错时默认为聊天
            return {"intent": "chat", "reason": f"路由出错，默认为聊天: {str(e)}"}


def router_node(state: AgentState) -> AgentState:
    """
    路由节点函数

    LangGraph 工作流中使用的节点函数。
    分析用户意图并更新状态。

    Args:
        state: 当前状态

    Returns:
        更新后的状态
    """
    # 添加状态消息
    new_state = add_status_message(state, "🧠 正在分析用户意图...")

    # 创建路由 Agent 并执行
    agent = RouterAgent()
    result = agent.route(state["user_input"])

    # 更新状态
    new_state = dict(new_state)
    new_state["intent"] = result["intent"]
    new_state["routing_reason"] = result["reason"]

    # 根据意图设置下一个节点
    intent = result["intent"]
    if intent == "proposition":
        new_state["next_node"] = "memory_recall"
        new_state = add_status_message(new_state, f"📋 意图识别：命题需求")
    elif intent == "grading":
        new_state["next_node"] = "grading"
        new_state = add_status_message(new_state, f"📋 意图识别：阅卷需求")
    else:
        new_state["next_node"] = "chat_reply"
        new_state = add_status_message(new_state, f"📋 意图识别：普通对话")

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
                            "出一套", "帮我出", "生成几道", "生成一道"]
    keywords_grading = ["阅卷", "评分", "批改", "打分", "判断对错", "这题对不对"]

    user_input_lower = user_input.lower()

    if any(kw in user_input_lower for kw in keywords_proposition):
        return "proposition"
    elif any(kw in user_input_lower for kw in keywords_grading):
        return "grading"
    else:
        return "chat"
