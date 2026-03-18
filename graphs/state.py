"""
AgentState - LangGraph 全局状态定义

这是 LangGraph 流转的核心数据载体，定义了整个系统中各 Agent 之间传递的数据结构。
"""

from typing import TypedDict, List, Optional, Annotated, Literal, Any
import operator
from datetime import datetime


def merge_chat_history(left: List[dict], right: List[dict]) -> List[dict]:
    """合并聊天历史的 reducer 函数"""
    return left + right


class QuestionItem(TypedDict):
    """单个试题的数据结构"""
    id: str
    content: str
    question_type: str  # "choice" | "fill_blank" | "essay"
    difficulty: float  # 0.0 - 1.0
    topic: str
    options: Optional[List[str]]  # 选择题选项
    answer: str
    explanation: str
    audit_passed: bool
    audit_feedback: Optional[str]


class ExtractedParams(TypedDict):
    """提取的命题参数"""
    topic: str  # 知识点
    question_type: str  # 题型: choice, fill_blank, essay
    difficulty: str  # 难度: easy, medium, hard
    count: int  # 数量
    additional_requirements: Optional[str]  # 额外要求


class MemoryItem(TypedDict):
    """记忆项的数据结构"""
    id: str
    timestamp: str
    type: Literal["user_preference", "task_experience", "feedback"]
    content: str
    metadata: dict


class AgentState(TypedDict):
    """
    LangGraph 全局状态定义

    包含三个主要部分：
    1. 输入输出：用户输入、对话历史、最终响应
    2. 路由状态：意图识别结果
    3. 业务状态：记忆、需求分析、执行、生成与反思状态
    """

    # === 输入输出 ===
    user_input: str  # 用户当前输入
    chat_history: Annotated[List[dict], operator.add]  # 短期记忆（对话历史）
    final_response: str  # 最终输出给用户的响应

    # === 路由状态 ===
    intent: Literal["proposition", "grading", "chat"]  # 意图类型
    routing_reason: str  # 路由决策原因

    # === 话题追踪（用于意图识别优化）===
    last_intent: str  # 上一次意图
    last_topic: str  # 上一次知识点话题
    topic_changed: bool  # 话题是否改变

    # === 记忆认知层产出 ===
    retrieved_long_term_memory: List[MemoryItem]  # 从JSON检索到的历史经验
    extracted_params: ExtractedParams  # 提取的命题参数
    is_info_complete: bool  # Agent 自主判断需求是否完整
    missing_info: List[str]  # 缺失的信息列表
    follow_up_question: str  # 追问用户的问题

    # === 执行层状态 ===
    plan_steps: List[str]  # 执行计划步骤
    current_step_index: int  # 当前执行步骤索引
    current_step: str  # 当前步骤名称
    retrieved_knowledge: str  # RAG检索到的业务知识

    # === 生成与反思状态 ===
    draft_questions: List[QuestionItem]  # 生成的试题草稿
    audit_feedback: str  # 质检反馈
    revision_count: int  # 修订次数
    max_revisions: int  # 最大修订次数

    # === 控制流状态 ===
    should_continue: bool  # 是否继续执行
    next_node: str  # 下一个要执行的节点
    error_message: Optional[str]  # 错误信息

    # === 元数据 ===
    session_id: str  # 会话ID
    timestamp: str  # 当前时间戳
    status_messages: List[str]  # 状态消息列表（用于前端展示）


def create_initial_state(user_input: str, session_id: str = None) -> AgentState:
    """
    创建初始状态

    Args:
        user_input: 用户输入
        session_id: 会话ID，如果不提供则自动生成

    Returns:
        初始化的 AgentState
    """
    import uuid

    return AgentState(
        # 输入输出
        user_input=user_input,
        chat_history=[],
        final_response="",

        # 路由状态
        intent="chat",
        routing_reason="",

        # 话题追踪
        last_intent="",
        last_topic="",
        topic_changed=True,

        # 记忆认知层
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

        # 控制流
        should_continue=True,
        next_node="router",
        error_message=None,

        # 元数据
        session_id=session_id or str(uuid.uuid4()),
        timestamp=datetime.now().isoformat(),
        status_messages=[]
    )


def add_status_message(state: AgentState, message: str) -> AgentState:
    """
    添加状态消息（用于前端展示 Agent 内部动作）

    Args:
        state: 当前状态
        message: 状态消息

    Returns:
        更新后的状态
    """
    new_state = dict(state)
    new_state["status_messages"] = state["status_messages"] + [message]
    return new_state


def add_chat_message(state: AgentState, role: str, content: str) -> AgentState:
    """
    添加聊天消息到历史

    Args:
        state: 当前状态
        role: 消息角色 (user/assistant)
        content: 消息内容

    Returns:
        更新后的状态
    """
    new_state = dict(state)
    new_state["chat_history"] = state["chat_history"] + [{
        "role": role,
        "content": content,
        "timestamp": datetime.now().isoformat()
    }]
    return new_state
