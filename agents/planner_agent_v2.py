"""
规划 Agent (Tool Calling 版本)

使用 Tool Calling 模式进行任务规划和分解。
支持复杂任务的自动分解和执行计划生成。
"""

import json
from typing import Dict, Any, Optional, List
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import SystemMessage, HumanMessage

from agents.base import ToolCallingAgent, AgentTrace
from agents.tools.base import BaseTool, ToolParameter, ToolResult, register_tool
from graphs.state import AgentState, add_status_message
from utils.config import get_llm


# ==================== Planner 专用工具 ====================

@register_tool
class DecomposeTaskTool(BaseTool):
    """
    任务分解工具

    将复杂任务分解为多个子任务。
    """

    def __init__(self):
        super().__init__()
        self._name = "decompose_task"
        self._description = (
            "将复杂任务分解为多个子任务。"
            "返回子任务列表及其执行顺序。"
        )
        self._parameters = [
            ToolParameter(
                name="subtasks",
                type="string",
                description="JSON 数组格式的子任务列表，每个子任务包含 name、description、dependencies",
                required=True
            ),
            ToolParameter(
                name="execution_order",
                type="string",
                description="执行顺序，JSON 数组格式的子任务名称列表",
                required=True
            )
        ]

    def execute(self, subtasks: str, execution_order: str) -> ToolResult:
        """执行任务分解"""
        try:
            subtasks_list = json.loads(subtasks) if isinstance(
                subtasks, str) else subtasks
            order_list = json.loads(execution_order) if isinstance(
                execution_order, str) else execution_order

            return ToolResult(
                success=True,
                data={
                    "subtasks": subtasks_list,
                    "execution_order": order_list,
                    "total_subtasks": len(subtasks_list)
                }
            )
        except json.JSONDecodeError as e:
            return ToolResult(
                success=False,
                data=None,
                error=f"JSON 解析失败: {str(e)}"
            )


@register_tool
class EstimateComplexityTool(BaseTool):
    """
    复杂度评估工具

    评估任务的复杂度和预计执行时间。
    """

    def __init__(self):
        super().__init__()
        self._name = "estimate_complexity"
        self._description = (
            "评估任务的复杂度和预计执行时间。"
            "返回复杂度级别和预估步骤数。"
        )
        self._parameters = [
            ToolParameter(
                name="complexity_level",
                type="string",
                description="复杂度级别：simple/medium/complex",
                required=True,
                enum=["simple", "medium", "complex"]
            ),
            ToolParameter(
                name="estimated_steps",
                type="integer",
                description="预计执行步骤数",
                required=True
            ),
            ToolParameter(
                name="requires_parallel",
                type="boolean",
                description="是否需要并行执行",
                required=False,
                default=False
            ),
            ToolParameter(
                name="reason",
                type="string",
                description="评估理由",
                required=True
            )
        ]

    def execute(
        self,
        complexity_level: str,
        estimated_steps: int,
        reason: str,
        requires_parallel: bool = False
    ) -> ToolResult:
        """执行复杂度评估"""
        return ToolResult(
            success=True,
            data={
                "complexity_level": complexity_level,
                "estimated_steps": estimated_steps,
                "requires_parallel": requires_parallel,
                "reason": reason
            }
        )


@register_tool
class GeneratePlanTool(BaseTool):
    """
    计划生成工具

    生成详细的执行计划。
    """

    def __init__(self):
        super().__init__()
        self._name = "generate_plan"
        self._description = (
            "生成详细的执行计划。"
            "包含步骤列表、资源需求、预期输出。"
        )
        self._parameters = [
            ToolParameter(
                name="steps",
                type="string",
                description="JSON 数组格式的步骤列表，每个步骤包含 name、action、expected_output",
                required=True
            ),
            ToolParameter(
                name="resources_needed",
                type="string",
                description="需要的资源列表，JSON 数组格式",
                required=False,
                default="[]"
            ),
            ToolParameter(
                name="estimated_time",
                type="string",
                description="预计完成时间描述",
                required=False,
                default="1-2分钟"
            )
        ]

    def execute(
        self,
        steps: str,
        resources_needed: str = "[]",
        estimated_time: str = "1-2分钟"
    ) -> ToolResult:
        """执行计划生成"""
        try:
            steps_list = json.loads(steps) if isinstance(steps, str) else steps
            resources_list = json.loads(resources_needed) if isinstance(
                resources_needed, str) else resources_needed

            return ToolResult(
                success=True,
                data={
                    "steps": steps_list,
                    "resources_needed": resources_list,
                    "estimated_time": estimated_time,
                    "total_steps": len(steps_list)
                }
            )
        except json.JSONDecodeError as e:
            return ToolResult(
                success=False,
                data=None,
                error=f"JSON 解析失败: {str(e)}"
            )


# ==================== Planner Agent ====================

PLANNER_SYSTEM_PROMPT = """你是一个任务规划 Agent，负责将命题需求分解为可执行的步骤。

## 可用工具
1. decompose_task: 将复杂任务分解为多个子任务
2. estimate_complexity: 评估任务复杂度
3. generate_plan: 生成详细执行计划

## 工作流程
1. 首先使用 estimate_complexity 评估任务复杂度
2. 如果任务复杂，使用 decompose_task 分解子任务
3. 最后使用 generate_plan 生成详细计划

## 命题任务的标准步骤
- 知识检索：从知识库检索相关知识点
- 试题生成：根据需求生成试题
- 质量审核：审核试题的科学性和规范性
- 记忆沉淀：保存成功经验到长期记忆

## 示例
需求: "生成5道代数选择题，难度中等"
1. 调用 estimate_complexity(complexity_level="simple", estimated_steps=4, reason="标准命题任务")
2. 调用 generate_plan(steps=[
    {"name": "知识检索", "action": "search_knowledge", "expected_output": "代数相关知识点"},
    {"name": "试题生成", "action": "generate_questions", "expected_output": "5道选择题"},
    {"name": "质量审核", "action": "audit_questions", "expected_output": "审核结果"},
    {"name": "记忆沉淀", "action": "save_experience", "expected_output": "经验记录"}
])

需求: "出一套高考数学模拟卷"
1. 调用 estimate_complexity(complexity_level="complex", estimated_steps=15, reason="需要多题型、多知识点、难度梯度设计")
2. 调用 decompose_task(subtasks=[
    {"name": "分析考纲", "description": "分析高考数学考纲要求"},
    {"name": "设计结构", "description": "设计试卷结构和题型分布"},
    {"name": "生成试题", "description": "分模块生成试题"},
    {"name": "审核调整", "description": "审核并调整试题"},
    {"name": "整理输出", "description": "整理最终试卷"}
])
3. 调用 generate_plan(...)
"""


class PlannerAgentV2(ToolCallingAgent):
    """
    规划 Agent V2

    使用 Tool Calling 模式进行任务规划和分解。
    """

    def __init__(self, llm: Optional[BaseChatModel] = None):
        super().__init__(
            llm=llm or get_llm(temperature=0),
            tools=[
                DecomposeTaskTool(),
                EstimateComplexityTool(),
                GeneratePlanTool()
            ],
            max_iterations=5,
            verbose=False
        )

    @property
    def name(self) -> str:
        return "planner"

    @property
    def system_prompt(self) -> str:
        return PLANNER_SYSTEM_PROMPT

    def create_plan(
        self,
        topic: str,
        question_type: str,
        difficulty: str,
        count: int,
        additional_requirements: str = ""
    ) -> Dict[str, Any]:
        """
        创建执行计划

        Args:
            topic: 知识点
            question_type: 题型
            difficulty: 难度
            count: 数量
            additional_requirements: 额外要求

        Returns:
            执行计划
        """
        # 构建输入
        user_input = f"请为以下命题需求创建执行计划：\n"
        user_input += f"- 知识点: {topic}\n"
        user_input += f"- 题型: {question_type}\n"
        user_input += f"- 难度: {difficulty}\n"
        user_input += f"- 数量: {count}\n"
        if additional_requirements:
            user_input += f"- 额外要求: {additional_requirements}\n"

        # 运行 Agent
        trace = self.run_with_tools(user_input)

        # 解析结果
        result = {
            "plan_steps": [
                "检索业务知识库",
                "生成试题",
                "质量审核",
                "记忆沉淀"
            ],
            "estimated_tasks": 4,
            "complexity": "simple",
            "subtasks": [],
            "trace": trace.to_dict()
        }

        # 从决策中提取信息
        for decision in trace.decisions:
            if decision.action == "estimate_complexity":
                result["complexity"] = decision.action_input.get(
                    "complexity_level", "simple")
                result["estimated_tasks"] = decision.action_input.get(
                    "estimated_steps", 4)

            elif decision.action == "decompose_task":
                try:
                    subtasks = decision.action_input.get("subtasks", "[]")
                    result["subtasks"] = json.loads(
                        subtasks) if isinstance(subtasks, str) else subtasks
                except json.JSONDecodeError:
                    pass

            elif decision.action == "generate_plan":
                try:
                    steps = decision.action_input.get("steps", "[]")
                    steps_list = json.loads(steps) if isinstance(
                        steps, str) else steps
                    if steps_list:
                        result["plan_steps"] = [
                            s.get("name", s.get("action", "")) for s in steps_list]
                        result["estimated_tasks"] = len(steps_list)
                except json.JSONDecodeError:
                    pass

        return result


# ==================== 兼容旧版本的节点函数 ====================

def planner_node_v2(state: AgentState) -> AgentState:
    """
    规划节点函数 V2

    使用 Tool Calling 版本的 Planner Agent。
    与旧版本保持兼容的接口。
    """
    new_state = add_status_message(state, "📝 正在规划任务...")

    # 获取需求参数
    params = state["extracted_params"]

    # 创建规划 Agent
    agent = PlannerAgentV2()

    # 创建执行计划
    plan = agent.create_plan(
        topic=params.get("topic", ""),
        question_type=params.get("question_type", ""),
        difficulty=params.get("difficulty", ""),
        count=params.get("count", 1),
        additional_requirements=params.get("additional_requirements", "")
    )

    # 更新状态
    new_state = dict(new_state)
    new_state["plan_steps"] = plan["plan_steps"]
    new_state["current_step_index"] = 0
    new_state["next_node"] = "executor"

    # 添加复杂度信息
    if plan.get("complexity"):
        new_state["task_complexity"] = plan["complexity"]

    # 如果有子任务，保存
    if plan.get("subtasks"):
        new_state["subtasks"] = plan["subtasks"]

    # 添加状态消息
    steps_str = " -> ".join(plan["plan_steps"])
    new_state = add_status_message(new_state, f"📋 执行计划: {steps_str}")
    new_state = add_status_message(
        new_state, f"📊 复杂度: {plan.get('complexity', 'simple')}, 预计步骤: {plan.get('estimated_tasks', 4)}")

    # 保存追踪信息
    new_state["agent_trace"] = plan.get("trace", {})

    return new_state
