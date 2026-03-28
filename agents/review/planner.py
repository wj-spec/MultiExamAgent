"""
审题 Planner Agent (agents/review/planner.py)

职责：接收用户上传的试题/试卷，分析后生成专业的审题待办清单。

专业审题工作流遵循：
1. 阅题理解（把握整体结构和考查意图）
2. 课标核查（知识点与考纲对齐）
3. 科学性验证（内容正确性）
4. 难度评估（难度系数、区分度分析）
5. 答案校验（参考答案数学/逻辑验证）
6. 表述规范（命题语言规范性）
7. 综合报告（出具专业审题意见书）
"""

import json
from typing import Optional, Callable, Awaitable, List

from pydantic import BaseModel, Field

from services.todo_service import TodoService
from utils.config import get_llm


# ==================== Planner 输出结构（复用命题版）====================

class PlannedTask(BaseModel):
    title: str
    description: str = ""
    task_type: str
    dependencies: List[str] = Field(default_factory=list)
    order: int = 0


class PlannerOutput(BaseModel):
    title: str
    summary: str
    tasks: List[PlannedTask]


# ==================== 审题 Planner System Prompt ====================

REVIEW_PLANNER_PROMPT = """你是一位拥有丰富经验的高考命题审核专家，负责对试题/试卷进行全面专业的审核。
你的职责是：**根据待审材料，制定一套系统、专业的审题工作待办清单**。

## 你的审题专业框架

### 审题五维标准
1. **科学性**：内容知识点无错误，答案唯一正确，无歧义
2. **有效性**：题目能有效测量预期的学习目标，不考查超纲内容
3. **可靠性**：评分标准明确，评分者间信度高
4. **公平性**：无文化偏见，语言表述不存在歧视性元素
5. **规范性**：符合命题语言规范，格式标准

### 审题工作模块（按实际情况取舍）
- **阅题梳理 (comprehension)**：理解试卷整体结构、分值分布、考查意图
- **对抗审核 (student_adversarial_review)**：模拟学生身份真实做题，验证题目条件是否充分、是否存在多解或歧义
- **课纲核查 (syllabus_check)**：逐题核对考查内容是否在课程标准范围内
- **科学性审核 (science_check)**：验证物理公式/数学推导/化学方程式/事实依据
- **难度评估 (difficulty_assessment)**：估算每题难度系数，分析试卷整体难度结构
- **答案验证 (answer_verify)**：严格推导/计算验证参考答案
- **表述审核 (language_review)**：检查命题语言规范性、标点、歧义
- **评分标准审核 (scoring_review)**：审核评分标准的完整性和操作性
- **综合报告 (report_generate)**：出具专业审题意见书

## 输出要求（严格 JSON 格式，不含 markdown 代码块）：
{
  "title": "审核任务标题，如'高三物理期末考试审题'",
  "summary": "审核规划说明，说明审核侧重点和方法论",
  "tasks": [
    {
      "title": "任务标题",
      "description": "审核要点和方法说明",
      "task_type": "comprehension|student_adversarial_review|syllabus_check|science_check|difficulty_assessment|answer_verify|language_review|scoring_review|report_generate",
      "dependencies": ["依赖任务title"],
      "order": 0
    }
  ]
}

## 注意事项
- 根据试题数量和复杂度决定任务粒度（题量少可合并，题量多可拆分）
- 科学性严格的学科（物理/化学/数学）必须包含专门的答案验证任务
- 综合报告应作为最后一个任务（依赖其他所有任务完成）
"""


# ==================== 审题 Planner 核心类 ====================

class ReviewPlanner:
    """
    审题规划 Agent
    
    将用户上传的试题内容转化为结构化的审题任务清单。
    """

    def __init__(self, mcp_tools: list = None, skills: list = None):
        self.llm = get_llm(temperature=0.2)
        self.mcp_tools = mcp_tools or []
        self.skills = skills or []

    def _build_messages(self, exam_content: str, user_instructions: str = "") -> list:
        from langchain_core.messages import SystemMessage, HumanMessage

        user_msg = f"待审试题内容：\n\n{exam_content}"
        if user_instructions:
            user_msg += f"\n\n用户特别说明：{user_instructions}"
        user_msg += "\n\n请制定审题任务清单。"

        return [SystemMessage(content=REVIEW_PLANNER_PROMPT), HumanMessage(content=user_msg)]

    def _parse_output(self, raw: str) -> PlannerOutput:
        raw = raw.strip()
        if raw.startswith("```"):
            lines = raw.split("\n")
            raw = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])
        return PlannerOutput(**json.loads(raw))

    async def aplan(self, exam_content: str, user_instructions: str = "") -> PlannerOutput:
        """异步规划审题任务"""
        messages = self._build_messages(exam_content, user_instructions)
        response = await self.llm.ainvoke(messages)
        return self._parse_output(response.content)

    def plan(self, exam_content: str, user_instructions: str = "") -> PlannerOutput:
        """同步规划审题任务"""
        messages = self._build_messages(exam_content, user_instructions)
        response = self.llm.invoke(messages)
        return self._parse_output(response.content)


# ==================== 工具函数 ====================

def review_planner_output_to_todo_group(
    output: PlannerOutput,
    session_id: str,
) -> dict:
    """将 PlannerOutput 转换为 TodoGroup 并保存到数据库"""
    task_dicts = [
        {
            "title": t.title,
            "description": t.description,
            "task_type": t.task_type,
            "dependencies": [],
            "order": t.order,
        }
        for t in output.tasks
    ]
    return TodoService.create_group(
        session_id=session_id,
        scene="review",
        title=output.title,
        tasks=task_dicts,
        planner_summary=output.summary,
    )


# ==================== LangGraph 节点 ====================

async def review_planner_node(
    state: dict,
    websocket_send: Optional[Callable[[dict], Awaitable[None]]] = None,
) -> dict:
    """
    审题 Planner LangGraph 节点

    输入：state["user_input"]（包含试题内容或上传文件路径）
    输出：state["current_todo_group"]（审题任务组）
    """
    from graphs.state_v3 import add_status_message_v3

    new_state = add_status_message_v3(state, "🔍 正在制定审题计划...")
    session_id = state.get("session_id", "")
    exam_content = state.get("user_input", "")
    user_instructions = state.get("extracted_params", {}).get("additional_requirements", "")

    try:
        planner = ReviewPlanner()
        plan_output = await planner.aplan(exam_content, user_instructions)
        group = review_planner_output_to_todo_group(plan_output, session_id)

        new_state = dict(new_state)
        new_state["current_todo_group"] = group
        new_state = add_status_message_v3(
            new_state,
            f"✅ 审题计划制定完成，共 {len(group['tasks'])} 个审核任务"
        )

        if websocket_send:
            await websocket_send({
                "type": "todo_group_created",
                "group": group,
            })

    except Exception as e:
        new_state = dict(new_state)
        new_state["error_message"] = f"审题规划失败: {str(e)}"

    return new_state
