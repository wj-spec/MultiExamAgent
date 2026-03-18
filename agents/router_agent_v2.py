"""
入口路由 Agent (Tool Calling 版本)

使用 Tool Calling 模式进行意图识别与实体提取。
支持更精准的意图分类和参数提取。
"""

import json
import re
from typing import Dict, Any, Optional, List
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import SystemMessage, HumanMessage

from agents.base import ToolCallingAgent, AgentTrace
from agents.tools.base import BaseTool, ToolParameter, ToolResult, register_tool
from graphs.state import AgentState, add_status_message
from utils.config import get_llm


# ==================== Router 专用工具 ====================

@register_tool
class ClassifyIntentTool(BaseTool):
    """
    意图分类工具

    将用户输入分类为特定意图类型。
    """

    def __init__(self):
        super().__init__()
        self._name = "classify_intent"
        self._description = (
            "将用户输入分类为特定意图类型。"
            "返回意图类型和置信度。"
        )
        self._parameters = [
            ToolParameter(
                name="intent",
                type="string",
                description="意图类型：proposition(命题)、grading(阅卷)、chat(闲聊)",
                required=True,
                enum=["proposition", "grading", "chat"]
            ),
            ToolParameter(
                name="confidence",
                type="number",
                description="置信度 (0-1)",
                required=True
            ),
            ToolParameter(
                name="reason",
                type="string",
                description="分类理由",
                required=True
            )
        ]

    def execute(self, intent: str, confidence: float, reason: str) -> ToolResult:
        """执行意图分类"""
        return ToolResult(
            success=True,
            data={
                "intent": intent,
                "confidence": confidence,
                "reason": reason
            }
        )


@register_tool
class ExtractEntitiesTool(BaseTool):
    """
    实体提取工具

    从用户输入中提取命题相关的实体信息。
    """

    def __init__(self):
        super().__init__()
        self._name = "extract_entities"
        self._description = (
            "从用户输入中提取命题相关的实体信息。"
            "包括知识点、题型、难度、数量等。"
        )
        self._parameters = [
            ToolParameter(
                name="topic",
                type="string",
                description="知识点名称",
                required=False,
                default=""
            ),
            ToolParameter(
                name="question_type",
                type="string",
                description="题型：choice/fill_blank/essay",
                required=False,
                default=""
            ),
            ToolParameter(
                name="difficulty",
                type="string",
                description="难度：easy/medium/hard",
                required=False,
                default=""
            ),
            ToolParameter(
                name="count",
                type="integer",
                description="试题数量",
                required=False,
                default=1
            ),
            ToolParameter(
                name="additional_requirements",
                type="string",
                description="额外要求",
                required=False,
                default=""
            )
        ]

    def execute(
        self,
        topic: str = "",
        question_type: str = "",
        difficulty: str = "",
        count: int = 1,
        additional_requirements: str = ""
    ) -> ToolResult:
        """执行实体提取"""
        return ToolResult(
            success=True,
            data={
                "topic": topic,
                "question_type": question_type,
                "difficulty": difficulty,
                "count": count,
                "additional_requirements": additional_requirements
            }
        )


# ==================== Router Agent ====================

ROUTER_SYSTEM_PROMPT = """你是一个智能路由 Agent，负责分析用户输入并决定如何处理。

## 可用工具
1. classify_intent: 将用户输入分类为特定意图类型
2. extract_entities: 从用户输入中提取命题相关的实体信息

## 意图类型说明
- proposition: 用户想要生成试题、出题、命题
- grading: 用户想要阅卷、评分、批改
- chat: 普通对话、问答、咨询

## 工作流程
1. 首先使用 classify_intent 工具判断用户意图
2. 如果意图是 proposition，使用 extract_entities 工具提取实体信息
3. 返回结构化的路由结果

## 示例
用户输入: "帮我出5道代数选择题"
1. 调用 classify_intent(intent="proposition", confidence=0.95, reason="用户明确要求出题")
2. 调用 extract_entities(topic="代数", question_type="choice", count=5)

用户输入: "这道题对不对？"
1. 调用 classify_intent(intent="grading", confidence=0.9, reason="用户想要判断题目对错")

用户输入: "你好"
1. 调用 classify_intent(intent="chat", confidence=0.99, reason="普通问候")
"""


class RouterAgentV2(ToolCallingAgent):
    """
    入口路由 Agent V2

    使用 Tool Calling 模式进行意图识别与实体提取。
    """

    def __init__(self, llm: Optional[BaseChatModel] = None):
        super().__init__(
            llm=llm or get_llm(temperature=0),
            tools=[ClassifyIntentTool(), ExtractEntitiesTool()],
            max_iterations=3,
            verbose=False
        )

    @property
    def name(self) -> str:
        return "router"

    @property
    def system_prompt(self) -> str:
        return ROUTER_SYSTEM_PROMPT

    def route(self, user_input: str) -> Dict[str, Any]:
        """
        执行路由判断

        Args:
            user_input: 用户输入

        Returns:
            路由结果
        """
        # 运行 Agent
        trace = self.run_with_tools(user_input)

        # 解析结果
        result = {
            "intent": "chat",
            "reason": "",
            "confidence": 0.0,
            "entities": {},
            "trace": trace.to_dict()
        }

        # 从决策中提取信息
        for decision in trace.decisions:
            if decision.action == "classify_intent":
                result["intent"] = decision.action_input.get("intent", "chat")
                result["reason"] = decision.action_input.get("reason", "")
                result["confidence"] = decision.action_input.get(
                    "confidence", 0.0)

            elif decision.action == "extract_entities":
                result["entities"] = decision.action_input

        # 如果没有工具调用，使用后备方案
        if not trace.decisions and trace.final_result:
            result = self._fallback_parse(trace.final_result, user_input)

        return result

    def _fallback_parse(self, response: str, user_input: str) -> Dict[str, Any]:
        """
        后备解析方案

        当 Tool Calling 失败时使用规则匹配。
        """
        result = {
            "intent": "chat",
            "reason": "后备规则匹配",
            "confidence": 0.6,
            "entities": {}
        }

        # 关键词匹配
        response_lower = response.lower()
        user_lower = user_input.lower()

        if any(kw in user_lower for kw in ["出题", "命题", "生成试题", "考题", "出一套"]):
            result["intent"] = "proposition"
            result["reason"] = "关键词匹配：命题相关"
            result["confidence"] = 0.8
        elif any(kw in user_lower for kw in ["阅卷", "评分", "批改", "打分"]):
            result["intent"] = "grading"
            result["reason"] = "关键词匹配：阅卷相关"
            result["confidence"] = 0.8

        # 提取实体
        if result["intent"] == "proposition":
            # 数量
            count_match = re.search(r'(\d+)\s*[道个条]', user_input)
            if count_match:
                result["entities"]["count"] = int(count_match.group(1))

            # 题型
            if "选择" in user_lower:
                result["entities"]["question_type"] = "choice"
            elif "填空" in user_lower:
                result["entities"]["question_type"] = "fill_blank"
            elif "解答" in user_lower or "简答" in user_lower:
                result["entities"]["question_type"] = "essay"

            # 难度
            if "简单" in user_lower or "基础" in user_lower:
                result["entities"]["difficulty"] = "easy"
            elif "困难" in user_lower or "难" in user_lower:
                result["entities"]["difficulty"] = "hard"
            elif "中等" in user_lower:
                result["entities"]["difficulty"] = "medium"

        return result


# ==================== 兼容旧版本的节点函数 ====================

def router_node_v2(state: AgentState) -> AgentState:
    """
    路由节点函数 V2

    使用 Tool Calling 版本的 Router Agent。
    与旧版本保持兼容的接口。
    """
    # 添加状态消息
    new_state = add_status_message(state, "🧠 正在分析用户意图...")

    # 创建路由 Agent 并执行
    agent = RouterAgentV2()
    result = agent.route(state["user_input"])

    # 更新状态
    new_state = dict(new_state)
    new_state["intent"] = result["intent"]
    new_state["routing_reason"] = result["reason"]

    # 如果有提取的实体，合并到状态
    if result.get("entities"):
        existing_params = new_state.get("extracted_params", {})
        new_state["extracted_params"] = {
            **existing_params, **result["entities"]}

    # 根据意图设置下一个节点
    intent = result["intent"]
    if intent == "proposition":
        new_state["next_node"] = "memory_recall"
        new_state = add_status_message(
            new_state, f"📋 意图识别：命题需求 (置信度: {result['confidence']:.0%})")
    elif intent == "grading":
        new_state["next_node"] = "grading"
        new_state = add_status_message(
            new_state, f"📋 意图识别：阅卷需求 (置信度: {result['confidence']:.0%})")
    else:
        new_state["next_node"] = "chat_reply"
        new_state = add_status_message(
            new_state, f"📋 意图识别：普通对话 (置信度: {result['confidence']:.0%})")

    # 保存追踪信息（用于可观测性）
    new_state["agent_trace"] = result.get("trace", {})

    return new_state
