"""
记忆沉淀 Agent (Tool Calling 版本)

使用 Tool Calling 模式进行经验总结和记忆沉淀。
支持用户偏好学习、经验提取、记忆存储等工具调用。
"""

import json
from typing import Dict, Any, Optional, List
from datetime import datetime
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import SystemMessage, HumanMessage

from agents.base import ToolCallingAgent, AgentTrace
from agents.tools.base import BaseTool, ToolParameter, ToolResult, register_tool
from graphs.state import AgentState, add_status_message
from tools.memory_tools import save_memory, get_user_preferences
from utils.config import get_llm


# ==================== Consolidator 专用工具 ====================

@register_tool
class SummarizeExperienceTool(BaseTool):
    """
    经验总结工具

    总结本次对话中的成功经验。
    """

    def __init__(self):
        super().__init__()
        self._name = "summarize_experience"
        self._description = (
            "总结本次对话中的成功经验。"
            "提取可复用的命题经验、用户偏好等。"
        )
        self._parameters = [
            ToolParameter(
                name="experience_type",
                type="string",
                description="经验类型：user_preference/ task_experience/feedback",
                required=True,
                enum=["user_preference", "task_experience", "feedback"]
            ),
            ToolParameter(
                name="content",
                type="string",
                description="经验内容描述",
                required=True
            ),
            ToolParameter(
                name="keywords",
                type="string",
                description="关键词列表，逗号分隔",
                required=False,
                default=""
            ),
            ToolParameter(
                name="importance",
                type="string",
                description="重要程度：high/medium/low",
                required=False,
                default="medium",
                enum=["high", "medium", "low"]
            )
        ]

    def execute(
        self,
        experience_type: str,
        content: str,
        keywords: str = "",
        importance: str = "medium"
    ) -> ToolResult:
        """执行经验总结"""
        return ToolResult(
            success=True,
            data={
                "type": experience_type,
                "content": content,
                "keywords": [k.strip() for k in keywords.split(",") if k.strip()],
                "importance": importance,
                "timestamp": datetime.now().isoformat()
            }
        )


@register_tool
class SavePreferenceTool(BaseTool):
    """
    偏好保存工具

    保存用户的命题偏好到长期记忆。
    """

    def __init__(self):
        super().__init__()
        self._name = "save_preference"
        self._description = (
            "保存用户的命题偏好到长期记忆。"
            "用于记录用户常用的题型、难度等偏好。"
        )
        self._parameters = [
            ToolParameter(
                name="preference_key",
                type="string",
                description="偏好键名，如 preferred_difficulty、preferred_question_type",
                required=True
            ),
            ToolParameter(
                name="preference_value",
                type="string",
                description="偏好值",
                required=True
            ),
            ToolParameter(
                name="confidence",
                type="number",
                description="置信度 (0-1)",
                required=False,
                default=0.8
            )
        ]

    def execute(
        self,
        preference_key: str,
        preference_value: str,
        confidence: float = 0.8
    ) -> ToolResult:
        """执行偏好保存"""
        # 调用实际的记忆存储
        try:
            save_memory(
                memory_type="user_preference",
                content=f"{preference_key}: {preference_value}",
                metadata={
                    "key": preference_key,
                    "value": preference_value,
                    "confidence": confidence
                }
            )

            return ToolResult(
                success=True,
                data={
                    "saved": True,
                    "key": preference_key,
                    "value": preference_value,
                    "confidence": confidence
                }
            )
        except Exception as e:
            return ToolResult(
                success=False,
                data={"saved": False},
                error=f"保存偏好失败: {str(e)}"
            )


@register_tool
class SaveExperienceTool(BaseTool):
    """
    经验保存工具

    保存成功的命题经验到长期记忆。
    """

    def __init__(self):
        super().__init__()
        self._name = "save_experience"
        self._description = (
            "保存成功的命题经验到长期记忆。"
            "用于积累命题技巧和最佳实践。"
        )
        self._parameters = [
            ToolParameter(
                name="topic",
                type="string",
                description="相关知识点",
                required=True
            ),
            ToolParameter(
                name="experience",
                type="string",
                description="经验描述",
                required=True
            ),
            ToolParameter(
                name="success_indicators",
                type="string",
                description="成功指标，JSON数组格式",
                required=False,
                default="[]"
            )
        ]

    def execute(
        self,
        topic: str,
        experience: str,
        success_indicators: str = "[]"
    ) -> ToolResult:
        """执行经验保存"""
        try:
            indicators = json.loads(success_indicators) if isinstance(
                success_indicators, str) else success_indicators

            # 调用实际的记忆存储
            save_memory(
                memory_type="task_experience",
                content=experience,
                metadata={
                    "topic": topic,
                    "success_indicators": indicators
                }
            )

            return ToolResult(
                success=True,
                data={
                    "saved": True,
                    "topic": topic,
                    "experience": experience,
                    "indicators": indicators
                }
            )
        except Exception as e:
            return ToolResult(
                success=False,
                data={"saved": False},
                error=f"保存经验失败: {str(e)}"
            )


@register_tool
class AnalyzePatternsTool(BaseTool):
    """
    模式分析工具

    分析用户行为模式和历史偏好。
    """

    def __init__(self):
        super().__init__()
        self._name = "analyze_patterns"
        self._description = (
            "分析用户行为模式和历史偏好。"
            "识别常见的命题需求和偏好趋势。"
        )
        self._parameters = [
            ToolParameter(
                name="pattern_type",
                type="string",
                description="分析模式类型：topic_frequency/difficulty_preference/type_preference",
                required=True,
                enum=["topic_frequency",
                      "difficulty_preference", "type_preference"]
            ),
            ToolParameter(
                name="findings",
                type="string",
                description="分析发现，JSON格式",
                required=True
            ),
            ToolParameter(
                name="recommendations",
                type="string",
                description="基于分析的推荐，JSON数组格式",
                required=False,
                default="[]"
            )
        ]

    def execute(
        self,
        pattern_type: str,
        findings: str,
        recommendations: str = "[]"
    ) -> ToolResult:
        """执行模式分析"""
        try:
            findings_data = json.loads(findings) if isinstance(
                findings, str) else findings
            recs = json.loads(recommendations) if isinstance(
                recommendations, str) else recommendations

            return ToolResult(
                success=True,
                data={
                    "pattern_type": pattern_type,
                    "findings": findings_data,
                    "recommendations": recs
                }
            )
        except json.JSONDecodeError as e:
            return ToolResult(
                success=False,
                data=None,
                error=f"JSON 解析失败: {str(e)}"
            )


# ==================== Consolidator Agent ====================

CONSOLIDATOR_SYSTEM_PROMPT = """你是一个记忆沉淀 Agent，负责总结对话经验并保存到长期记忆。

## 可用工具
1. summarize_experience: 总结本次对话中的成功经验
2. save_preference: 保存用户的命题偏好
3. save_experience: 保存成功的命题经验
4. analyze_patterns: 分析用户行为模式

## 工作流程
1. 分析本次对话的成功要素
2. 提取用户偏好（如常用题型、难度偏好）
3. 总结可复用的命题经验
4. 保存到长期记忆

## 经验类型
- user_preference: 用户偏好（题型、难度、风格等）
- task_experience: 任务经验（成功的命题技巧）
- feedback: 反馈记录（用户的评价和建议）

## 示例
对话: 用户要求"出5道代数选择题，难度中等"，生成的试题通过了审核
1. 调用 summarize_experience(
    experience_type="task_experience",
    content="代数选择题生成：使用具体数值例子，选项设计避免计算错误",
    keywords="代数,选择题,数值计算"
)
2. 调用 save_preference(
    preference_key="preferred_question_type",
    preference_value="choice",
    confidence=0.7
)
"""


class ConsolidatorAgentV2(ToolCallingAgent):
    """
    记忆沉淀 Agent V2

    使用 Tool Calling 模式进行经验总结和记忆沉淀。
    """

    def __init__(self, llm: Optional[BaseChatModel] = None):
        super().__init__(
            llm=llm or get_llm(temperature=0.3),
            tools=[
                SummarizeExperienceTool(),
                SavePreferenceTool(),
                SaveExperienceTool(),
                AnalyzePatternsTool()
            ],
            max_iterations=3,
            verbose=False
        )

    @property
    def name(self) -> str:
        return "consolidator"

    @property
    def system_prompt(self) -> str:
        return CONSOLIDATOR_SYSTEM_PROMPT

    def consolidate(
        self,
        topic: str,
        question_type: str,
        difficulty: str,
        count: int,
        audit_passed: bool,
        user_feedback: str = "",
        chat_history: List[Dict] = None
    ) -> Dict[str, Any]:
        """
        执行记忆沉淀

        Args:
            topic: 知识点
            question_type: 题型
            difficulty: 难度
            count: 数量
            audit_passed: 是否通过审核
            user_feedback: 用户反馈
            chat_history: 对话历史

        Returns:
            沉淀结果
        """
        # 构建输入
        user_input = f"请总结本次命题对话的经验：\n"
        user_input += f"- 知识点: {topic}\n"
        user_input += f"- 题型: {question_type}\n"
        user_input += f"- 难度: {difficulty}\n"
        user_input += f"- 数量: {count}\n"
        user_input += f"- 审核结果: {'通过' if audit_passed else '未通过'}\n"
        if user_feedback:
            user_input += f"- 用户反馈: {user_feedback}\n"

        # 运行 Agent
        trace = self.run_with_tools(user_input)

        # 收集沉淀结果
        result = {
            "experiences_saved": [],
            "preferences_saved": [],
            "patterns_analyzed": [],
            "trace": trace.to_dict()
        }

        for decision in trace.decisions:
            if decision.action == "summarize_experience":
                if decision.observation:
                    try:
                        data = json.loads(decision.observation)
                        if data.get("success"):
                            result["experiences_saved"].append(
                                data.get("data", {}))
                    except json.JSONDecodeError:
                        pass

            elif decision.action == "save_preference":
                if decision.observation:
                    try:
                        data = json.loads(decision.observation)
                        if data.get("success") and data.get("data", {}).get("saved"):
                            result["preferences_saved"].append(
                                data.get("data", {}))
                    except json.JSONDecodeError:
                        pass

            elif decision.action == "save_experience":
                if decision.observation:
                    try:
                        data = json.loads(decision.observation)
                        if data.get("success") and data.get("data", {}).get("saved"):
                            result["experiences_saved"].append(
                                data.get("data", {}))
                    except json.JSONDecodeError:
                        pass

            elif decision.action == "analyze_patterns":
                if decision.observation:
                    try:
                        data = json.loads(decision.observation)
                        if data.get("success"):
                            result["patterns_analyzed"].append(
                                data.get("data", {}))
                    except json.JSONDecodeError:
                        pass

        return result


# ==================== 兼容旧版本的节点函数 ====================

def consolidator_node_v2(state: AgentState) -> AgentState:
    """
    记忆沉淀节点函数 V2

    使用 Tool Calling 版本的 Consolidator Agent。
    与旧版本保持兼容的接口。
    """
    new_state = add_status_message(state, "💾 正在沉淀经验...")

    # 获取参数
    params = state.get("extracted_params", {})
    questions = state.get("draft_questions", [])

    # 检查审核是否通过
    audit_passed = all(q.get("audit_passed", False)
                       for q in questions) if questions else False

    # 创建沉淀 Agent
    agent = ConsolidatorAgentV2()

    # 执行记忆沉淀
    result = agent.consolidate(
        topic=params.get("topic", ""),
        question_type=params.get("question_type", ""),
        difficulty=params.get("difficulty", ""),
        count=params.get("count", 1),
        audit_passed=audit_passed,
        user_feedback="",
        chat_history=state.get("chat_history", [])
    )

    # 更新状态
    new_state = dict(new_state)
    new_state["consolidation_result"] = result
    new_state["should_continue"] = False

    # 添加状态消息
    exp_count = len(result.get("experiences_saved", []))
    pref_count = len(result.get("preferences_saved", []))

    if exp_count > 0 or pref_count > 0:
        new_state = add_status_message(
            new_state,
            f"✅ 经验沉淀完成：{exp_count} 条经验，{pref_count} 个偏好"
        )
    else:
        new_state = add_status_message(new_state, "✅ 记忆沉淀完成")

    # 保存追踪信息
    new_state["agent_trace"] = result.get("trace", {})

    return new_state
