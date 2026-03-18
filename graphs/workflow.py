"""
LangGraph 工作流构建

定义多智能体协作的状态流转图。
"""

from typing import Literal, TypedDict
from langgraph.graph import StateGraph, END

from graphs.state import AgentState, create_initial_state
from agents.router_agent import router_node
from agents.memory_agent import memory_recall_node, cognitive_node, ask_user_node
from agents.planner_agent import planner_node
from agents.executor_agent import knowledge_retrieval_node, creator_node, auditor_node
from agents.consolidator_agent import consolidator_node, chat_reply_node


def route_by_intent(state: AgentState) -> Literal["memory_recall", "chat_reply"]:
    """
    根据意图路由

    Args:
        state: 当前状态

    Returns:
        下一个节点名称
    """
    intent = state.get("intent", "chat")
    if intent == "proposition":
        return "memory_recall"
    elif intent == "grading":
        # TODO: 实现阅卷功能
        return "chat_reply"
    else:
        return "chat_reply"


def route_by_completeness(state: AgentState) -> Literal["planner", "ask_user"]:
    """
    根据需求完整性路由

    Args:
        state: 当前状态

    Returns:
        下一个节点名称
    """
    if state.get("is_info_complete", False):
        return "planner"
    else:
        return "ask_user"


def route_by_audit_result(state: AgentState) -> Literal["creator", "consolidator"]:
    """
    根据审核结果路由

    Args:
        state: 当前状态

    Returns:
        下一个节点名称
    """
    revision_count = state.get("revision_count", 0)
    max_revisions = state.get("max_revisions", 3)

    if revision_count >= max_revisions:
        return "consolidator"

    # 检查最后一条审核反馈
    audit_feedback = state.get("audit_feedback", "")
    if "通过" in audit_feedback or audit_feedback == "":
        return "consolidator"
    else:
        return "creator"


def build_workflow() -> StateGraph:
    """
    构建工作流图

    Returns:
        编译后的工作流图
    """
    # 创建状态图
    workflow = StateGraph(AgentState)

    # 添加节点
    # 第一层：入口路由
    workflow.add_node("router", router_node)

    # 第二层：业务控制层
    workflow.add_node("memory_recall", memory_recall_node)
    workflow.add_node("cognitive", cognitive_node)
    workflow.add_node("ask_user", ask_user_node)
    workflow.add_node("planner", planner_node)

    # 第三层：执行层
    workflow.add_node("knowledge_retrieval", knowledge_retrieval_node)
    workflow.add_node("creator", creator_node)
    workflow.add_node("auditor", auditor_node)
    workflow.add_node("consolidator", consolidator_node)

    # 闲聊节点
    workflow.add_node("chat_reply", chat_reply_node)

    # 设置入口点
    workflow.set_entry_point("router")

    # 添加边
    # 路由 -> 根据意图分发
    workflow.add_conditional_edges(
        "router",
        route_by_intent,
        {
            "memory_recall": "memory_recall",
            "chat_reply": "chat_reply"
        }
    )

    # 闲聊直接结束
    workflow.add_edge("chat_reply", END)

    # 记忆召回 -> 认知分析
    workflow.add_edge("memory_recall", "cognitive")

    # 认知分析 -> 根据完整性分发
    workflow.add_conditional_edges(
        "cognitive",
        route_by_completeness,
        {
            "planner": "planner",
            "ask_user": "ask_user"
        }
    )

    # 追问用户 -> 结束（等待用户回复）
    workflow.add_edge("ask_user", END)

    # 规划 -> 知识检索
    workflow.add_edge("planner", "knowledge_retrieval")

    # 知识检索 -> 生成
    workflow.add_edge("knowledge_retrieval", "creator")

    # 生成 -> 审核
    workflow.add_edge("creator", "auditor")

    # 审核 -> 根据结果分发
    workflow.add_conditional_edges(
        "auditor",
        route_by_audit_result,
        {
            "creator": "creator",
            "consolidator": "consolidator"
        }
    )

    # 记忆沉淀 -> 结束
    workflow.add_edge("consolidator", END)

    return workflow


def compile_workflow():
    """
    编译工作流

    Returns:
        编译后的可执行图
    """
    workflow = build_workflow()
    return workflow.compile()


# 预编译的工作流实例
compiled_workflow = None


def get_workflow():
    """
    获取编译后的工作流实例（单例模式）

    Returns:
        编译后的工作流
    """
    global compiled_workflow
    if compiled_workflow is None:
        compiled_workflow = compile_workflow()
    return compiled_workflow


def run_workflow(user_input: str, session_id: str = None, chat_history: list = None) -> AgentState:
    """
    运行工作流

    Args:
        user_input: 用户输入
        session_id: 会话ID
        chat_history: 对话历史

    Returns:
        最终状态
    """
    workflow = get_workflow()

    # 创建初始状态
    initial_state = create_initial_state(user_input, session_id)

    # 如果有对话历史，添加到状态
    if chat_history:
        initial_state["chat_history"] = chat_history

    # 运行工作流
    final_state = workflow.invoke(initial_state)

    return final_state


def run_workflow_stream(user_input: str, session_id: str = None, chat_history: list = None):
    """
    流式运行工作流

    生成每个节点执行后的状态更新。

    Args:
        user_input: 用户输入
        session_id: 会话ID
        chat_history: 对话历史

    Yields:
        每一步的状态更新
    """
    workflow = get_workflow()

    # 创建初始状态
    initial_state = create_initial_state(user_input, session_id)

    # 如果有对话历史，添加到状态
    if chat_history:
        initial_state["chat_history"] = chat_history

    # 流式运行工作流
    for state in workflow.stream(initial_state):
        yield state


# 工作流可视化
def visualize_workflow():
    """
    生成工作流可视化图

    Returns:
        Mermaid 格式的流程图字符串
    """
    mermaid = """
```mermaid
graph TD
    User[用户输入] --> Router[路由节点]
    Router -->|命题意图| MemoryRecall[记忆召回]
    Router -->|闲聊| ChatReply[闲聊回复]
    Router -->|阅卷| ChatReply

    MemoryRecall --> Cognitive[认知分析]
    Cognitive -->|需求完整| Planner[规划]
    Cognitive -->|需求缺失| AskUser[追问用户]

    AskUser --> End1[等待用户回复]

    Planner --> KnowledgeRetrieval[知识检索]
    KnowledgeRetrieval --> Creator[试题生成]
    Creator --> Auditor[质量审核]

    Auditor -->|通过| Consolidator[记忆沉淀]
    Auditor -->|不通过| Creator

    Consolidator --> End2[完成]
    ChatReply --> End3[完成]
```
    """
    return mermaid


if __name__ == "__main__":
    # 测试工作流
    print("构建工作流...")
    graph = compile_workflow()

    print("\n运行测试...")
    result = run_workflow("帮我出两道关于导数的选择题")

    print("\n最终状态:")
    print(f"意图: {result.get('intent')}")
    print(f"需求完整: {result.get('is_info_complete')}")
    print(f"生成的试题数: {len(result.get('draft_questions', []))}")
    print(f"\n最终响应:\n{result.get('final_response')}")
