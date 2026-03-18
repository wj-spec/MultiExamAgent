"""
ReAct Router Agent

使用 ReAct 模式进行意图识别与实体提取。
支持多轮推理、追问澄清、复杂需求分析。
"""

import json
from typing import Dict, Any, Optional, List

from langchain_core.language_models import BaseChatModel

from agents.base.react_agent import ReActAgent, ReActTrace
from agents.tools.base import BaseTool, ToolParameter, ToolResult, register_tool
from graphs.state import AgentState, add_status_message
from utils.config import get_llm


# ==================== Router 专用工具 ====================

@register_tool
class ClassifyIntentTool(BaseTool):
    """意图分类工具"""

    def __init__(self):
        super().__init__()
        self._name = "classify_intent"
        self._description = "将用户输入分类为特定意图类型。返回意图类型和置信度。"
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
        return ToolResult(
            success=True,
            data={"intent": intent, "confidence": confidence, "reason": reason}
        )


@register_tool
class ExtractEntitiesTool(BaseTool):
    """实体提取工具"""

    def __init__(self):
        super().__init__()
        self._name = "extract_entities"
        self._description = "从用户输入中提取命题相关的实体信息，包括知识点、题型、难度、数量等。"
        self._parameters = [
            ToolParameter(name="topic", type="string",
                          description="知识点名称", required=False, default=""),
            ToolParameter(name="question_type", type="string",
                          description="题型：choice/fill_blank/essay", required=False, default=""),
            ToolParameter(name="difficulty", type="string",
                          description="难度：easy/medium/hard", required=False, default=""),
            ToolParameter(name="count", type="integer",
                          description="试题数量", required=False, default=1),
            ToolParameter(name="additional_requirements", type="string",
                          description="额外要求", required=False, default="")
        ]

    def execute(self, topic: str = "", question_type: str = "", difficulty: str = "",
                count: int = 1, additional_requirements: str = "") -> ToolResult:
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


@register_tool
class CheckCompletenessTool(BaseTool):
    """需求完整性检查工具"""

    def __init__(self):
        super().__init__()
        self._name = "check_completeness"
        self._description = "检查命题需求是否完整，判断是否需要追问用户。"
        self._parameters = [
            ToolParameter(name="is_complete", type="boolean",
                          description="需求是否完整", required=True),
            ToolParameter(name="missing_fields", type="string",
                          description="缺失的字段，JSON数组格式", required=False, default="[]"),
            ToolParameter(name="suggested_question", type="string",
                          description="建议追问的问题", required=False, default="")
        ]

    def execute(self, is_complete: bool, missing_fields: str = "[]", suggested_question: str = "") -> ToolResult:
        try:
            missing = json.loads(missing_fields) if isinstance(
                missing_fields, str) else missing_fields
        except json.JSONDecodeError:
            missing = []

        return ToolResult(
            success=True,
            data={
                "is_complete": is_complete,
                "missing_fields": missing,
                "suggested_question": suggested_question
            }
        )


@register_tool
class GenerateFollowUpTool(BaseTool):
    """追问生成工具"""

    def __init__(self):
        super().__init__()
        self._name = "generate_follow_up"
        self._description = "生成追问问题，用于澄清用户需求。"
        self._parameters = [
            ToolParameter(name="question", type="string",
                          description="追问的问题", required=True),
            ToolParameter(name="options", type="string",
                          description="可选答案，JSON数组格式", required=False, default="[]"),
            ToolParameter(name="purpose", type="string",
                          description="追问目的", required=True)
        ]

    def execute(self, question: str, options: str = "[]", purpose: str = "") -> ToolResult:
        try:
            options_list = json.loads(options) if isinstance(
                options, str) else options
        except json.JSONDecodeError:
            options_list = []

        return ToolResult(
            success=True,
            data={
                "question": question,
                "options": options_list,
                "purpose": purpose
            }
        )


# ==================== ReAct Router Agent ====================

REACT_ROUTER_SYSTEM_PROMPT = """你是一个智能路由 Agent，使用 ReAct 模式分析用户输入并决定如何处理。

## 核心职责
1. 识别用户意图（命题、阅卷、闲聊）
2. 提取命题相关实体（知识点、题型、难度、数量）
3. 判断需求完整性，必要时生成追问

## 可用工具
- classify_intent: 意图分类
- extract_entities: 实体提取
- check_completeness: 完整性检查
- generate_follow_up: 生成追问

## 工作流程
1. 首先使用 classify_intent 判断用户意图
2. 如果是命题意图，使用 extract_entities 提取实体
3. 使用 check_completeness 检查需求完整性
4. 如果不完整，使用 generate_follow_up 生成追问
5. 完整后给出最终结果

## 意图判断标准
- proposition: 用户想要生成试题、出题、命题
- grading: 用户想要阅卷、评分、批改
- chat: 普通对话、问答、咨询

## 示例
用户输入: "帮我出5道代数选择题"
Thought: 用户明确要求出题，这是命题意图
Action: classify_intent
Action Input: {"intent": "proposition", "confidence": 0.95, "reason": "用户明确要求出题"}

Thought: 意图确认为命题，需要提取实体
Action: extract_entities
Action Input: {"topic": "代数", "question_type": "choice", "count": 5}

Thought: 检查需求完整性
Action: check_completeness
Action Input: {"is_complete": false, "missing_fields": ["difficulty"], "suggested_question": "请问难度要求是什么？"}

Thought: 需要追问难度
Action: generate_follow_up
Action Input: {"question": "请问您希望试题难度如何？", "options": ["简单", "中等", "困难"], "purpose": "确定难度"}

Final Answer: 意图=命题，实体={知识点:代数, 题型:选择题, 数量:5}，需要追问难度
"""


class ReActRouterAgent(ReActAgent):
    """
    使用 ReAct 模式的 Router Agent

    特点：
    - 多轮推理能力
    - 自动判断需求完整性
    - 智能追问生成
    - 推理过程可追溯
    """

    def __init__(self, llm: Optional[BaseChatModel] = None, verbose: bool = False):
        super().__init__(
            llm=llm or get_llm(temperature=0),
            tools=[
                ClassifyIntentTool(),
                ExtractEntitiesTool(),
                CheckCompletenessTool(),
                GenerateFollowUpTool()
            ],
            max_iterations=6,
            verbose=verbose
        )

    @property
    def name(self) -> str:
        return "react_router"

    @property
    def system_prompt(self) -> str:
        return REACT_ROUTER_SYSTEM_PROMPT

    def route(self, user_input: str, context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        执行路由判断

        Args:
            user_input: 用户输入
            context: 额外上下文（如历史对话）

        Returns:
            路由结果
        """
        # 构建 task
        task = f"分析以下用户输入，确定意图并提取相关信息：\n\n用户输入: {user_input}"

        if context:
            task += f"\n\n上下文信息: {json.dumps(context, ensure_ascii=False)}"

        # 运行 ReAct 循环
        trace = self.run(task, context)

        # 解析结果
        result = {
            "intent": "chat",
            "reason": "",
            "confidence": 0.0,
            "entities": {},
            "needs_follow_up": False,
            "follow_up_question": "",
            "is_complete": True,
            "trace": trace.to_dict()
        }

        # 从步骤中提取信息
        for step in trace.steps:
            if step.action == "classify_intent":
                result["intent"] = step.action_input.get("intent", "chat")
                result["reason"] = step.action_input.get("reason", "")
                result["confidence"] = step.action_input.get("confidence", 0.0)

            elif step.action == "extract_entities":
                result["entities"] = step.action_input

            elif step.action == "check_completeness":
                result["is_complete"] = step.action_input.get(
                    "is_complete", True)
                if not result["is_complete"]:
                    result["needs_follow_up"] = True

            elif step.action == "generate_follow_up":
                result["follow_up_question"] = step.action_input.get(
                    "question", "")
                result["needs_follow_up"] = True

        # 如果有最终答案，尝试解析
        if trace.final_answer:
            result["final_answer"] = trace.final_answer

        return result


# ==================== LangGraph 节点函数 ====================

def react_router_node(state: AgentState) -> AgentState:
    """
    ReAct Router 节点函数

    用于集成到 LangGraph 工作流中。
    """
    new_state = add_status_message(state, "🧠 正在使用 ReAct 模式分析用户意图...")

    # 创建 Agent
    agent = ReActRouterAgent(verbose=False)

    # 获取上下文
    context = {}
    if state.get("chat_history"):
        context["chat_history"] = state["chat_history"][-3:]  # 最近3轮对话

    # 执行路由
    result = agent.route(state["user_input"], context)

    # 更新状态
    new_state = dict(new_state)
    new_state["intent"] = result["intent"]
    new_state["routing_reason"] = result["reason"]
    new_state["routing_confidence"] = result["confidence"]

    # 如果有提取的实体，合并到状态
    if result.get("entities"):
        existing_params = new_state.get("extracted_params", {})
        new_state["extracted_params"] = {
            **existing_params, **result["entities"]}

    # 如果需要追问
    if result.get("needs_follow_up"):
        new_state["needs_follow_up"] = True
        new_state["follow_up_question"] = result.get("follow_up_question", "")
        new_state["is_info_complete"] = False
        new_state["next_node"] = "ask_user"
        new_state = add_status_message(
            new_state,
            f"❓ 需要追问: {result.get('follow_up_question', '')}"
        )
    else:
        # 根据意图设置下一个节点
        intent = result["intent"]
        if intent == "proposition":
            new_state["next_node"] = "memory_recall"
            new_state["is_info_complete"] = True
            new_state = add_status_message(
                new_state,
                f"📋 意图识别：命题需求 (置信度: {result['confidence']:.0%})"
            )
        elif intent == "grading":
            new_state["next_node"] = "grading"
            new_state = add_status_message(
                new_state,
                f"📋 意图识别：阅卷需求 (置信度: {result['confidence']:.0%})"
            )
        else:
            new_state["next_node"] = "chat_reply"
            new_state = add_status_message(
                new_state,
                f"📋 意图识别：普通对话 (置信度: {result['confidence']:.0%})"
            )

    # 保存追踪信息
    new_state["agent_trace"] = result.get("trace", {})

    return new_state


# ==================== 便捷函数 ====================

def create_react_router(llm: Optional[BaseChatModel] = None, verbose: bool = False) -> ReActRouterAgent:
    """创建 ReAct Router Agent 实例"""
    return ReActRouterAgent(llm=llm, verbose=verbose)
