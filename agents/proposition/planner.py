"""
命题 Planner Agent (agents/proposition/planner.py)

职责：接收用户的命题/命卷需求，分析后生成结构化的待办任务清单。
规划结果通过 TodoService 持久化，并实时推送到前端看板。

设计特点：
1. Prompt 嵌入现代教育命题专业逻辑（课标对齐、认知目标分层、题型配比）
2. 支持"重新规划"（基于用户评论修改方案）
3. 输出严格的 JSON 结构，Pydantic 校验保稳定性
4. 支持 MCP/Skills 扩展注入
"""

import json
import uuid
from datetime import datetime
from typing import List, Dict, Any, Optional, Callable, Awaitable

from pydantic import BaseModel, Field

from services.todo_service import TodoService
from utils.config import get_llm


# ==================== Planner 输出数据结构 ====================

class PlannedTask(BaseModel):
    """Planner 规划的单个任务"""
    title: str = Field(..., description="任务标题，简洁明确")
    description: str = Field("", description="任务详细说明，包含执行要点")
    task_type: str = Field(..., description=(
        "任务类型：knowledge_analysis / question_generate / quality_audit / "
        "difficulty_calibration / answer_verify / report_generate / document_export"
    ))
    dependencies: List[str] = Field(default_factory=list, description="依赖任务的 title 列表（执行后转换为 ID）")
    order: int = Field(..., description="执行顺序（从 0 开始）")


class PlannerOutput(BaseModel):
    """Planner 完整输出"""
    title: str = Field(..., description="任务组标题（简洁描述整体目标）")
    summary: str = Field(..., description="规划说明：为什么这样规划，背后的教育逻辑")
    tasks: List[PlannedTask] = Field(..., description="待办任务列表（按执行顺序排列）")


# ==================== 命题 Planner System Prompt ====================

PROPOSITION_PLANNER_PROMPT = """你是一位资深命题专家和教育测量专家，专注于为中国 K-12 及高考命题提供专业规划。
你的职责是：**根据用户需求，制定一套科学、专业、符合现代教育测量理论的命题工作待办清单**。

## 你掌握的专业知识

### 命题基本原则
- **课标对齐**：题目必须对应《义务教育课程标准》或《普通高中课程标准》的具体内容标准
- **布鲁姆认知目标分层**：记忆→理解→应用→分析→综合→创造，试卷应覆盖多个层次
- **双向细目表**：题型×知识点×认知层次的交叉矩阵，确保考查全面性
- **难度系数控制**：
  - 课内测试：易:中:难 ≈ 3:5:2
  - 模拟/高考：约 0.5~0.6（平均难度系数）
- **区分度要求**：每道题区分度 D ≥ 0.3（优秀题目 D ≥ 0.4）
- **信效度保证**：试卷整体信度系数 ≥ 0.8

### 各题型规范
- **选择题**：干净的单一考点，4选1，选项平行无干扰
- **填空题**：知识核心点直接考查，答案唯一明确
- **解答题**：需有梯度（基础分+提高分），明确评分标准
- **综合题**：知识迁移应用，情境具体

### 高考/模拟卷结构标准（以数学为例）
- 选择题 12 道 × 5分 = 60分
- 填空题 4 道 × 5分 = 20分
- 解答题：基础2道 + 提高3道 + 压轴1道 = 70分

## 工作流程

当用户提出命题需求，你需要规划以下工作流（按实际需求取舍）：

1. **知识点分析 (knowledge_analysis)**：分析考查的知识点，与课标对齐，建立双向细目表
2. **题目生成 (question_generate)**：按题型分批生成试题（通常按题型分为多个任务）
3. **难度校准 (difficulty_calibration)**：估算每题难度系数，调整至目标难度
4. **质量审核 (quality_audit)**：科学性检查（无错误）、规范性检查（表述符合规范）
5. **答案验证 (answer_verify)**：验证参考答案和评分标准
6. **报告生成 (report_generate)**：生成命题说明（含双向细目表）
7. **文档导出 (document_export)**：导出为 Word/PDF 格式

## 输出要求

你必须严格输出 JSON 格式（不要有 markdown 代码块），遵循以下 Schema：
{
  "title": "简洁的任务组标题，如'2024届高三数学模拟卷'",
  "summary": "规划说明，100字以内，解释规划逻辑和专业考量",
  "tasks": [
    {
      "title": "任务标题",
      "description": "执行要点和具体要求",
      "task_type": "knowledge_analysis|question_generate|quality_audit|...",
      "dependencies": ["依赖任务的title列表，空则为[]"],
      "order": 0
    }
  ]
}

## 注意事项
- 不同学科、不同题型应拆分为独立任务（便于用户分阶段确认和注释）
- 依赖关系要合理（如题目生成依赖知识点分析）
- 任务描述要具体，让 AI 执行者清楚每步的操作要点
"""


# ==================== 命题 Planner 核心类 ====================

class PropositionPlanner:
    """
    命题规划 Agent

    使用 LLM 将用户的命题需求转化为结构化的 TodoGroup。
    支持初次规划和基于用户评论的重新规划。
    """

    def __init__(self, mcp_tools: list = None, skills: list = None):
        self.llm = get_llm(temperature=0.3)
        self.mcp_tools = mcp_tools or []
        self.skills = skills or []

    def _build_messages(self, user_query: str, context: str = "") -> list:
        """构建 LLM 消息列表"""
        from langchain_core.messages import SystemMessage, HumanMessage
        messages = [SystemMessage(content=PROPOSITION_PLANNER_PROMPT)]
        if context:
            messages.append(HumanMessage(content=f"[上下文参考]\n{context}\n\n[用户需求]\n{user_query}"))
        else:
            messages.append(HumanMessage(content=user_query))
        return messages

    def _parse_output(self, raw: str) -> PlannerOutput:
        """解析 LLM 输出为 PlannerOutput"""
        # 清理可能的 markdown 代码块
        raw = raw.strip()
        if raw.startswith("```"):
            lines = raw.split("\n")
            raw = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])

        data = json.loads(raw)
        return PlannerOutput(**data)

    def plan(self, user_query: str, context: str = "") -> PlannerOutput:
        """
        同步规划（适合非 async 环境）

        Args:
            user_query: 用户的完整命题需求描述
            context: 额外上下文（用户历史偏好、上次的规划等）

        Returns:
            PlannerOutput（含任务列表）
        """
        messages = self._build_messages(user_query, context)
        response = self.llm.invoke(messages)
        return self._parse_output(response.content)

    async def aplan(self, user_query: str, context: str = "") -> PlannerOutput:
        """
        异步规划

        Args:
            user_query: 用户需求描述
            context: 额外上下文

        Returns:
            PlannerOutput（含任务列表）
        """
        messages = self._build_messages(user_query, context)
        response = await self.llm.ainvoke(messages)
        return self._parse_output(response.content)

    def replan(self, original_plan: dict, user_feedback: str) -> PlannerOutput:
        """
        基于用户评论重新规划

        Args:
            original_plan: 原始任务组字典（含现有任务）
            user_feedback: 用户的修改意见

        Returns:
            新的 PlannerOutput
        """
        # 构建重新规划上下文
        original_tasks_str = json.dumps(
            [{"title": t["title"], "description": t["description"], "comments": [c["content"] for c in t.get("comments", [])]}
             for t in original_plan.get("tasks", [])],
            ensure_ascii=False, indent=2
        )

        context = f"""[原有规划]
任务组：{original_plan.get('title', '')}
已有任务：
{original_tasks_str}

[用户修改意见]
{user_feedback}

请根据用户反馈调整规划方案。保留合理的原有任务，根据反馈新增/删除/修改必要的任务。"""

        return self.plan("请根据用户反馈调整命题规划方案", context)


# ==================== 工具函数：持久化 Planner 输出 ====================

def planner_output_to_todo_group(
    output: PlannerOutput,
    session_id: str,
    scene: str = "proposition",
) -> dict:
    """
    将 PlannerOutput 转换为 TodoGroup 并保存到数据库

    Returns:
        保存后的 TodoGroup 字典（含 DB 分配的 ID）
    """
    # 先转为任务字典列表（此时无 DB ID，依赖关系用 title 表示）
    task_dicts = [
        {
            "title": t.title,
            "description": t.description,
            "task_type": t.task_type,
            "dependencies": [],  # 依赖关系在创建后根据 title → ID 映射更新（简化版先留空）
            "order": t.order,
        }
        for t in output.tasks
    ]

    # 持久化
    group = TodoService.create_group(
        session_id=session_id,
        scene=scene,
        title=output.title,
        tasks=task_dicts,
        planner_summary=output.summary,
    )
    return group


# ==================== LangGraph 节点：命题规划 ====================

async def proposition_planner_node(
    state: dict,
    websocket_send: Optional[Callable[[dict], Awaitable[None]]] = None,
) -> dict:
    """
    命题 Planner LangGraph 节点

    功能：
    1. 调用 PropositionPlanner 生成规划
    2. 保存到 TodoService（SQLite）
    3. 通过 websocket_send 推送 todo_group_created 事件

    Args:
        state: AgentStateV3 字典
        websocket_send: WebSocket 发送函数（可选，用于实时推送）

    Returns:
        更新后的 state（含 current_todo_group）
    """
    from graphs.state_v3 import add_status_message_v3

    new_state = add_status_message_v3(state, "📋 正在规划命题任务清单...")
    session_id = state.get("session_id", "")
    user_input = state.get("user_input", "")

    # 构建上下文（记忆 + 历史偏好）
    memories = state.get("retrieved_long_term_memory", [])
    context_parts = []
    if memories:
        mem_str = "\n".join(f"- {m.get('content', '')}" for m in memories[:5])
        context_parts.append(f"[用户历史偏好]\n{mem_str}")

    # 如果是重新规划，带入原有规划
    existing_group = state.get("current_todo_group")
    if existing_group and state.get("intent") == "replan":
        context_parts.append(f"[当前规划（待修订）]\n"
                              f"任务组：{existing_group.get('title', '')}")

    context = "\n\n".join(context_parts)

    try:
        planner = PropositionPlanner()
        plan_output = await planner.aplan(user_input, context)
        group = planner_output_to_todo_group(plan_output, session_id, scene="proposition")

        new_state = dict(new_state)
        new_state["current_todo_group"] = group
        new_state = add_status_message_v3(new_state, f"✅ 命题规划完成，共 {len(group['tasks'])} 个任务")

        # 推送到前端
        if websocket_send:
            await websocket_send({
                "type": "todo_group_created",
                "group": group,
            })

    except json.JSONDecodeError as e:
        new_state = dict(new_state)
        new_state["error_message"] = f"规划输出解析失败: {str(e)}"
        new_state = add_status_message_v3(new_state, "❌ 任务规划解析失败，请重试")
    except Exception as e:
        new_state = dict(new_state)
        new_state["error_message"] = f"规划失败: {str(e)}"
        new_state = add_status_message_v3(new_state, f"❌ 任务规划失败: {str(e)}")

    return new_state
