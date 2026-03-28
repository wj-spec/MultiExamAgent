"""
AgentState v3 - LangGraph 全局状态定义 (v3.0 重构版)

v3.0 新增：
- 场景（Scene）感知：chat / proposition / review
- TodoTask 结构：待办任务管理
- Solver 执行状态追踪
- 统一的 Agent 能力注入（MCP / Skills）
"""

from typing import TypedDict, List, Optional, Annotated, Literal, Any, Dict
import operator
from datetime import datetime


# ==================== 待办任务数据模型 ====================

class TodoComment(TypedDict):
    """待办任务的用户/Agent 评论"""
    id: str
    author: Literal["user", "agent"]       # 来源
    content: str
    created_at: str


class TodoTask(TypedDict):
    """单个待办任务"""
    id: str
    task_group_id: str                     # 所属任务组 ID
    title: str                             # 任务标题（展示用）
    description: str                       # 任务详细说明
    task_type: str                         # 任务类型（knowledge_analysis/generate/audit/export...）
    status: Literal[
        "pending",                         # 待规划（Planner 初始输出）
        "ready",                           # 待执行（用户确认/依赖满足后）
        "running",                         # 进行中
        "done",                            # 已完成
        "need_revision",                   # 需修订（用户评论后 Planner 标记）
        "skipped",                         # 已跳过
    ]
    dependencies: List[str]                # 依赖的任务 ID 列表
    comments: List[TodoComment]            # 评论列表
    result: Optional[str]                  # 执行结果（Markdown 格式）
    result_data: Optional[Dict]            # 结构化执行结果（可选）
    created_at: str
    updated_at: str
    elapsed_ms: Optional[int]             # 执行耗时（毫秒）
    order: int                             # 显示顺序


class TodoGroup(TypedDict):
    """待办任务组（一次 Planner 规划对应一个 Group）"""
    id: str
    session_id: str
    scene: Literal["proposition", "review"]  # 所属场景
    title: str                               # 任务组标题（如"高考数学模拟卷"）
    status: Literal["planning", "ready", "running", "done", "replanning"]
    tasks: List[TodoTask]
    planner_summary: str                     # Planner 的规划说明
    created_at: str
    updated_at: str


# ==================== 复用的结构（保持兼容性）====================

class QuestionItem(TypedDict):
    """单个试题的数据结构"""
    id: str
    content: str
    question_type: str
    difficulty: float
    topic: str
    options: Optional[List[str]]
    answer: str
    explanation: str
    audit_passed: bool
    audit_feedback: Optional[str]


class ExtractedParams(TypedDict):
    """提取的命题参数"""
    topic: str
    question_type: str
    difficulty: str
    count: int
    additional_requirements: Optional[str]


class MemoryItem(TypedDict):
    """记忆项"""
    id: str
    timestamp: str
    type: Literal["user_preference", "task_experience", "feedback"]
    content: str
    metadata: dict


# ==================== v3.0 AgentState ====================

class AgentStateV3(TypedDict):
    """
    LangGraph 全局状态 v3.0

    核心变化：
    1. 新增 scene 字段区分三大场景
    2. 新增 current_todo_group / pending_tasks 支持待办流程
    3. 新增 solver_context 追踪当前 Solver 执行状态
    4. 保留所有旧字段以保持向后兼容
    """

    # ===================== 基础 I/O =====================
    user_input: str
    chat_history: Annotated[List[dict], operator.add]
    final_response: str

    # ===================== 场景感知 =====================
    scene: Literal["chat", "proposition", "review"]   # 当前激活场景
    scene_switch_hint: Optional[str]                  # Agent 建议切换场景时的提示文字

    # ===================== 路由 =====================
    intent: Literal["proposition", "grading", "chat"]
    primary_intent: Literal["proposition", "chat", "grading"]
    routing_reason: str
    routing_confidence: float
    next_node: str
    should_continue: bool
    error_message: Optional[str]

    # ===================== 记忆 =====================
    retrieved_long_term_memory: List[MemoryItem]
    extracted_params: ExtractedParams
    is_info_complete: bool
    missing_info: List[str]
    follow_up_question: str

    # ===================== 待办任务（新增 v3.0）=====================
    current_todo_group: Optional[TodoGroup]          # 当前激活的任务组
    active_task_id: Optional[str]                    # 当前 Solver 正在执行的任务 ID
    solver_context: Dict[str, Any]                   # Solver 执行上下文（跨任务传递数据）

    # ===================== 执行层（保持兼容）=====================
    plan_steps: List[str]
    current_step_index: int
    current_step: str
    retrieved_knowledge: str

    # ===================== 生成与反思（保持兼容）=====================
    draft_questions: List[QuestionItem]
    audit_feedback: str
    revision_count: int
    max_revisions: int

    # ===================== 多源检索 =====================
    search_route: str
    search_query: str
    search_sources: List[dict]

    # ===================== 话题追踪 =====================
    last_intent: str
    last_topic: str
    topic_changed: bool

    # ===================== 元数据 =====================
    session_id: str
    timestamp: str
    status_messages: List[str]

    # ===================== v3.0 扩展字段 =====================
    # 模式切换（保持旧版兼容）
    current_mode: Literal["proposition", "chat", "mixed"]
    mode_transition: Literal["enter", "exit", "none"]
    proposition_needed: bool
    proposition_context: str


def create_initial_state_v3(
    user_input: str,
    session_id: str = None,
    scene: str = "chat"
) -> AgentStateV3:
    """
    创建 v3.0 初始状态

    Args:
        user_input: 用户输入
        session_id: 会话ID，如果不提供则自动生成
        scene: 初始场景（chat/proposition/review）
    """
    import uuid

    return AgentStateV3(
        # 基础 I/O
        user_input=user_input,
        chat_history=[],
        final_response="",

        # 场景
        scene=scene,
        scene_switch_hint=None,

        # 路由
        intent="chat",
        primary_intent="chat",
        routing_reason="",
        routing_confidence=0.0,
        next_node="router",
        should_continue=True,
        error_message=None,

        # 记忆
        retrieved_long_term_memory=[],
        extracted_params=ExtractedParams(
            topic="",
            question_type="",
            difficulty="",
            count=0,
            additional_requirements=""
        ),
        is_info_complete=False,
        missing_info=[],
        follow_up_question="",

        # 待办任务
        current_todo_group=None,
        active_task_id=None,
        solver_context={},

        # 执行层
        plan_steps=[],
        current_step_index=0,
        current_step="",
        retrieved_knowledge="",

        # 生成与反思
        draft_questions=[],
        audit_feedback="",
        revision_count=0,
        max_revisions=3,

        # 多源检索
        search_route="",
        search_query="",
        search_sources=[],

        # 话题追踪
        last_intent="",
        last_topic="",
        topic_changed=True,

        # 元数据
        session_id=session_id or str(uuid.uuid4()),
        timestamp=datetime.now().isoformat(),
        status_messages=[],

        # 旧版兼容
        current_mode="chat",
        mode_transition="none",
        proposition_needed=False,
        proposition_context="",
    )


def add_status_message_v3(state: AgentStateV3, message: str) -> AgentStateV3:
    """添加状态消息"""
    new_state = dict(state)
    new_state["status_messages"] = state.get("status_messages", []) + [message]
    return new_state


def update_todo_task(
    state: AgentStateV3,
    task_id: str,
    **kwargs
) -> AgentStateV3:
    """
    更新待办任务组中某个任务的字段

    Args:
        state: 当前状态
        task_id: 要更新的任务 ID
        **kwargs: 要更新的字段
    """
    new_state = dict(state)
    group = state.get("current_todo_group")
    if not group:
        return new_state

    new_group = dict(group)
    new_tasks = []
    for task in group.get("tasks", []):
        if task["id"] == task_id:
            updated = dict(task)
            updated.update(kwargs)
            updated["updated_at"] = datetime.now().isoformat()
            new_tasks.append(updated)
        else:
            new_tasks.append(task)

    new_group["tasks"] = new_tasks
    new_group["updated_at"] = datetime.now().isoformat()
    new_state["current_todo_group"] = new_group
    return new_state
