"""
纯 async 工作流包装（不依赖 Chainlit）

从 workflow_chainlit.py 提取核心业务逻辑，去除所有 cl.Step / cl.Message 调用。
通过 status_callback 回调向调用方通知步骤状态变化。

Args:
    status_callback: async def callback(step_name: str, content: str, params: dict = None)
"""

from typing import Optional, Callable, Awaitable, List, Dict, Any
from datetime import datetime

from graphs.state import AgentState, create_initial_state
from tools.memory_tools import retrieve_memory, get_user_preferences
from tools.retriever import search_knowledge
from utils.prompts import CHAT_PROMPT
from utils.ui_utils import StepNames

from agents.router_agent_v2 import RouterAgentV2
from agents.memory_agent import MemoryCognitiveAgent
from agents.planner_agent import PlannerAgent
from agents.executor_agent import CreatorAgent, AuditorAgent, format_questions_response
from agents.consolidator_agent import ConsolidatorAgent
from utils.config import get_llm

# 回调类型定义
StatusCallback = Optional[Callable[..., Awaitable[None]]]
DebateCallback = Optional[Callable[[str, str, str], Awaitable[None]]]
SpeculativeCallback = Optional[Callable[[str], Awaitable[None]]]


async def _cb(callback: StatusCallback, step: str, content: str, params: dict = None, step_id: str = None, parent_id: str = None):
    """安全调用回调"""
    if callback:
        await callback(step, content, params, step_id, parent_id)


async def _d_cb(callback: DebateCallback, role: str, avatar: str, content: str):
    """安全调用辩论回调"""
    if callback:
        await callback(role, avatar, content)


async def _s_cb(callback: SpeculativeCallback, status: str):
    """安全调用投机执行动画回调"""
    if callback:
        await callback(status)

# ==================== 工具函数 ====================


def check_topic_changed(state: AgentState) -> bool:
    """与 workflow_chainlit.py 保持一致的话题变化检测"""
    last_intent = state.get("last_intent", "")
    last_topic = state.get("last_topic", "")

    if last_intent != "proposition":
        return True
    if not last_topic:
        return True

    user_input = state.get("user_input", "")
    switch_keywords = ["换个", "换一个", "换题", "改成", "改为", "出点别的", "不同"]
    if any(kw in user_input for kw in switch_keywords):
        return True

    topic_keywords = ["关于", "出", "生成", "帮我", "来"]
    if any(kw in user_input for kw in topic_keywords):
        if last_topic and last_topic not in user_input:
            return True

    return False


# ==================== 各节点函数 ====================

async def router_node(state: AgentState, callback: StatusCallback) -> AgentState:
    """
    路由节点 - 使用 V2 版本支持模式切换
    """
    topic_changed = check_topic_changed(state)
    last_intent = state.get("last_intent", "")
    current_mode = state.get("current_mode", "chat")

    if not topic_changed and last_intent == "proposition":
        await _cb(callback, StepNames.ROUTER, "📌 话题延续，跳过意图识别 → 命题")
        new_state = dict(state)
        new_state["intent"] = last_intent
        new_state["topic_changed"] = False
        return new_state

    await _cb(callback, StepNames.ROUTER, "正在分析用户意图...")

    # 使用 V2 版本的 Router Agent
    agent = RouterAgentV2()
    result = agent.route(state["user_input"], current_mode)

    # 调试日志
    print(
        f"[DEBUG] Router result: intent={result.get('intent')}, mode_switch={result.get('mode_switch')}, mode_transition={result.get('mode_transition')}")

    # 兼容新旧字段名
    intent = result.get("primary_intent") or result.get("intent", "chat")
    reason = result.get("reason", "")
    mode_switch = result.get("mode_switch")
    mode_transition = result.get("mode_transition", "none")

    intent_emoji = {"proposition": "📋", "grading": "📝",
                    "paper_generation": "📋", "review": "🔍", "chat": "💬"}.get(intent, "❓")
    await _cb(callback, StepNames.ROUTER, f"{intent_emoji} 识别意图: {intent} — {reason}")

    new_state = dict(state)
    new_state["primary_intent"] = intent
    new_state["intent"] = intent  # 兼容旧代码
    new_state["proposition_needed"] = result.get("proposition_needed", intent in [
                                                 "proposition", "paper_generation"])
    new_state["mode_transition"] = mode_transition
    new_state["mode_switch"] = mode_switch
    new_state["current_mode"] = mode_switch if mode_switch else current_mode
    new_state["routing_reason"] = reason
    new_state["last_intent"] = intent
    new_state["topic_changed"] = True

    # 如果有模式切换，添加状态消息
    if mode_switch and mode_transition in ["enter", "switch"]:
        mode_names = {"proposition": "命题",
                      "grading": "审卷", "paper_generation": "组卷"}
        mode_name = mode_names.get(mode_switch, mode_switch)
        await _cb(callback, StepNames.ROUTER, f"🔄 建议切换到{mode_name}模式")

    return new_state


async def memory_recall_node(state: AgentState, callback: StatusCallback) -> AgentState:
    await _cb(callback, "💡 记忆召回", "正在检索历史记忆...")

    memories = retrieve_memory(state["user_input"], top_k=5)
    await _cb(callback, "💡 记忆召回", f"检索到 {len(memories)} 条历史记忆")

    new_state = dict(state)
    new_state["retrieved_long_term_memory"] = memories
    return new_state


async def cognitive_node(state: AgentState, callback: StatusCallback) -> AgentState:
    await _cb(callback, StepNames.MEMORY, "正在分析需求完整性...")

    agent = MemoryCognitiveAgent()
    result = agent.analyze(
        user_input=state["user_input"],
        chat_history=state["chat_history"],
        long_term_memory=state["retrieved_long_term_memory"]
    )

    if result["is_complete"]:
        params = result["extracted_params"]
        params_dict = {
            "topic": params.get("topic", ""),
            "question_type": params.get("question_type", ""),
            "difficulty": params.get("difficulty", ""),
            "count": params.get("count", 0),
        }
        await _cb(
            callback,
            StepNames.MEMORY,
            f"✅ 需求完整: {params.get('topic', '未知')} / {params.get('question_type', '未知')} / {params.get('count', 0)}题",
            params_dict
        )
    else:
        await _cb(callback, StepNames.MEMORY, f"❓ 缺失信息: {', '.join(result['missing_info'][:2])}")

    new_state = dict(state)
    new_state["is_info_complete"] = result["is_complete"]
    new_state["extracted_params"] = result["extracted_params"]
    new_state["missing_info"] = result["missing_info"]
    new_state["follow_up_question"] = result["follow_up_question"]

    if result["is_complete"] and result["extracted_params"].get("topic"):
        new_state["last_topic"] = result["extracted_params"].get("topic")

    return new_state


async def ask_user_node(state: AgentState, callback: StatusCallback, speculative_callback: SpeculativeCallback = None) -> AgentState:
    # 触发前端投机执行动画
    await _s_cb(speculative_callback, "start")

    # 模拟后台极速预判加载
    import asyncio
    await asyncio.sleep(0.5)

    new_state = dict(state)
    new_state["final_response"] = state["follow_up_question"]
    new_state["should_continue"] = False
    return new_state


async def planner_node(state: AgentState, callback: StatusCallback) -> AgentState:
    params = state["extracted_params"]
    await _cb(callback, StepNames.PLANNER, f"正在制定执行计划：{params.get('topic', '')}")

    agent = PlannerAgent()
    plan = agent.create_plan(
        topic=params.get("topic", ""),
        question_type=params.get("question_type", ""),
        difficulty=params.get("difficulty", ""),
        count=params.get("count", 1),
        additional_requirements=params.get("additional_requirements", "")
    )

    await _cb(callback, StepNames.PLANNER, f"{' → '.join(plan['plan_steps'][:4])}")

    new_state = dict(state)
    new_state["plan_steps"] = plan["plan_steps"]
    new_state["current_step_index"] = 0
    return new_state


async def knowledge_retrieval_node(state: AgentState, callback: StatusCallback) -> AgentState:
    topic = state["extracted_params"].get("topic", "")
    await _cb(callback, StepNames.KNOWLEDGE, f"正在检索知识库: {topic}")

    # 模拟一个子节点任务
    await _cb(callback, "🔍 向量检索", f"在本地 向量数据库 中搜索与 {topic} 相关的向量...", step_id="sub_search_1", parent_id=StepNames.KNOWLEDGE)
    import asyncio
    await asyncio.sleep(0.5)

    knowledge = search_knowledge(topic, top_k=3)

    await _cb(callback, "🔍 向量检索", "检索完成", step_id="sub_search_1", parent_id=StepNames.KNOWLEDGE)

    word_count = len(knowledge.split()) if knowledge else 0
    await _cb(callback, StepNames.KNOWLEDGE, f"📚 检索到 {word_count} 字相关知识")

    new_state = dict(state)
    new_state["retrieved_knowledge"] = knowledge
    new_state["current_step_index"] = 1
    return new_state


async def creator_node(state: AgentState, callback: StatusCallback) -> AgentState:
    params = state["extracted_params"]
    count = params.get("count", 1)
    revision = state.get("revision_count", 0)
    iter_label = f"第{revision + 1}次" if revision > 0 else ""
    await _cb(callback, StepNames.CREATOR, f"正在生成 {count} 道试题{iter_label}...")

    agent = CreatorAgent()
    questions = agent.generate(
        topic=params.get("topic", ""),
        question_type=params.get("question_type", ""),
        difficulty=params.get("difficulty", ""),
        count=count,
        knowledge_context=state.get("retrieved_knowledge", ""),
        additional_requirements=params.get("additional_requirements", "")
    )

    await _cb(callback, StepNames.CREATOR, f"✅ 已生成 {len(questions)} 道试题")

    new_state = dict(state)
    new_state["draft_questions"] = questions
    new_state["current_step_index"] = 2
    return new_state


async def auditor_node(state: AgentState, callback: StatusCallback, debate_callback: DebateCallback = None) -> AgentState:
    revision_count = state.get("revision_count", 0)
    max_revisions = state.get("max_revisions", 3)
    q_count = len(state["draft_questions"])
    await _cb(callback, StepNames.AUDITOR, f"正在进行多专家交叉审核 ({revision_count + 1}/{max_revisions})...")

    params = state["extracted_params"]
    topic = params.get("topic", "")
    questions = state["draft_questions"]

    # 引入辩论专家
    from agents.debate_experts import DomainExpert, FormatExaminer, MetaReviewer
    import asyncio

    domain_expert = DomainExpert()
    format_examiner = FormatExaminer()
    meta_reviewer = MetaReviewer()

    # 并行调用两个专家
    import time
    start_time = time.time()

    domain_task = asyncio.to_thread(domain_expert.review, questions, topic)
    format_task = asyncio.to_thread(format_examiner.review, questions)

    results = await asyncio.gather(domain_task, format_task, return_exceptions=True)

    domain_feedback = results[0] if not isinstance(
        results[0], Exception) else f"学科专家异常: {results[0]}"
    format_feedback = results[1] if not isinstance(
        results[1], Exception) else f"格式专家异常: {results[1]}"

    await _d_cb(debate_callback, "domain_expert", "👨‍🏫", domain_feedback)
    await _d_cb(debate_callback, "format_examiner", "🕵️", format_feedback)

    # 主理人汇总
    await _cb(callback, "⚖️ 主理人决策", "正在综合专家组意见...", step_id="sub_meta_review", parent_id=StepNames.AUDITOR)
    passed, finalize_feedback = await asyncio.to_thread(meta_reviewer.conclude, questions, domain_feedback, format_feedback)
    await _cb(callback, "⚖️ 主理人决策", "决策完成", step_id="sub_meta_review", parent_id=StepNames.AUDITOR)

    meta_msg = "✅ 意见统一，放行。" if passed else f"⚠️ 发现问题：{finalize_feedback}"
    await _d_cb(debate_callback, "meta_reviewer", "🟢", meta_msg)

    if passed:
        await _cb(callback, StepNames.AUDITOR, "✅ 多专家审核通过")
    else:
        await _cb(callback, StepNames.AUDITOR, f"⚠️ 专家组指出问题，打回重构 ({revision_count + 1}/{max_revisions})")

    new_state = dict(state)
    new_state["audit_feedback"] = finalize_feedback
    new_state["audit_passed"] = passed

    # 记录辩论历史
    debate_record = {
        "iteration": revision_count + 1,
        "domain": domain_feedback,
        "format": format_feedback,
        "meta": finalize_feedback
    }
    new_state["debate_history"] = state.get(
        "debate_history", []) + [debate_record]

    if not passed:
        new_state["revision_count"] = revision_count + 1
        params_copy = dict(params)
        params_copy["additional_requirements"] = (
            f"{params.get('additional_requirements', '')}\n"
            f"请严格修正以下专家组指出的问题:\n{finalize_feedback}"
        )
        new_state["extracted_params"] = params_copy

    return new_state


async def consolidator_node(state: AgentState, callback: StatusCallback) -> AgentState:
    await _cb(callback, StepNames.CONSOLIDATOR, "正在保存本次经验...")

    try:
        agent = ConsolidatorAgent()
        memories = agent.consolidate(
            user_input=state["user_input"],
            extracted_params=state["extracted_params"],
            questions=state["draft_questions"],
            audit_feedback=state.get("audit_feedback", "")
        )

        saved_count = 0
        if memories:
            saved_count = agent.save_memories(memories)

        final_response = format_questions_response(state["draft_questions"])
        await _cb(callback, StepNames.CONSOLIDATOR, f"🎉 完成！已保存 {saved_count} 条经验")

    except Exception as e:
        import traceback
        print(f"记忆沉淀节点出错: {e}")
        print(traceback.format_exc())
        final_response = format_questions_response(
            state.get("draft_questions", []))
        await _cb(callback, StepNames.CONSOLIDATOR, "⚠️ 完成但记忆保存失败")

    new_state = dict(state)

    # 构造 GraphRAG 拓扑图 (知识溯源)
    topic = state.get("last_topic", "未知模块")
    memories = state.get("retrieved_long_term_memory", [])
    memory_nodes = ""
    if memories:
        for i, m in enumerate(memories):
            # 取前20个字符作为摘要
            summary = m.get("content", "")[:20].replace('"', "'") + "..."
            memory_nodes += f"    M{i}[\"长臂记忆: {summary}\"] --> Central\n"

    topology = f"""```mermaid
graph TD
    classDef central fill:#7C7CF8,stroke:#5B5BD6,color:#fff,stroke-width:2px
    classDef memory fill:#10b981,stroke:#059669,color:#fff
    classDef rag fill:#f59e0b,stroke:#d97706,color:#fff

    Central(("当前考点:\\n{topic}")):::central
{memory_nodes}
    RAG1["知识库: 历年真题考频分析"]:::rag --> Central
    RAG2["知识库: 易错点预警"]:::rag --> Central
```"""

    new_state["knowledge_topology"] = topology
    new_state["final_response"] = final_response
    new_state["should_continue"] = False
    new_state["current_step_index"] = 4
    return new_state


async def chat_reply_node(state: AgentState, callback: StatusCallback) -> AgentState:
    await _cb(callback, StepNames.CHAT, "正在生成回复...")

    try:
        llm = get_llm(temperature=0.7)
        chat_history = []
        for msg in state["chat_history"][-5:]:
            chat_history.append((msg["role"], msg["content"]))

        chain = CHAT_PROMPT | llm
        response = chain.invoke({
            "chat_history": chat_history,
            "user_input": state["user_input"]
        })
        final_response = response.content
        await _cb(callback, StepNames.CHAT, "💬 已生成回复")

    except Exception as e:
        final_response = "您好！我是 IntelliExam 命题助手，可以帮助您生成各类试题。请告诉我您需要什么类型的题目？"
        await _cb(callback, StepNames.CHAT, "⚠️ 回复生成失败，使用默认回复")

    new_state = dict(state)
    new_state["final_response"] = final_response
    new_state["should_continue"] = False
    return new_state


# ==================== 主工作流函数 ====================

async def run_workflow_async_server(
    state: AgentState,
    chat_history: List[dict] = None,
    status_callback: StatusCallback = None,
    debate_callback: DebateCallback = None,
    speculative_callback: SpeculativeCallback = None
) -> AgentState:
    """
    纯 async 工作流（不依赖 Chainlit）

    Args:
        state: 初始状态
        chat_history: 对话历史
        status_callback: async def(step_name, content, params=None)
        debate_callback: async def(role, avatar, content)
        speculative_callback: async def(content)

    Returns:
        最终状态
    """
    if chat_history:
        state["chat_history"] = chat_history

    try:
        # 1. 路由
        state = await router_node(state, status_callback)

        # 使用 proposition_needed 判断（优先）或兼容 intent
        if state.get("proposition_needed") or state.get("intent") == "proposition":
            # 2. 记忆召回
            state = await memory_recall_node(state, status_callback)

            # 3. 认知分析
            state = await cognitive_node(state, status_callback)

            if state["is_info_complete"]:
                # 4. 规划
                state = await planner_node(state, status_callback)

                # 5. 知识检索
                state = await knowledge_retrieval_node(state, status_callback)

                # 6. 生成-审核循环
                max_iterations = 4
                iteration = 0
                while iteration < max_iterations:
                    state = await creator_node(state, status_callback)

                    if not state.get("draft_questions"):
                        state["final_response"] = "抱歉，试题生成失败，请重试。"
                        state["should_continue"] = False
                        break

                    state = await auditor_node(state, status_callback, debate_callback)

                    if state.get("audit_passed", False):
                        break

                    revision_count = state.get("revision_count", 0)
                    max_revisions = state.get("max_revisions", 3)
                    if revision_count >= max_revisions:
                        state["audit_passed"] = True
                        break

                    iteration += 1

                # 7. 记忆沉淀 & 生成最终响应
                if state.get("draft_questions"):
                    state = await consolidator_node(state, status_callback)
                elif not state.get("final_response"):
                    state["final_response"] = "抱歉，试题生成失败，请稍后重试。"

                    if not state.get("is_info_complete", False):
                        state = await ask_user_node(state, status_callback, speculative_callback)
            else:
                # 追问用户
                state = await ask_user_node(state, status_callback, speculative_callback)

        else:
            # 闲聊 / 阅卷
            state = await chat_reply_node(state, status_callback)

    except Exception as e:
        import traceback
        print(f"工作流执行出错: {e}")
        print(traceback.format_exc())
        state["final_response"] = f"抱歉，处理过程中出现了问题：{str(e)}\n\n请稍后重试或换个方式提问。"
        state["should_continue"] = False
        state["error_message"] = str(e)

    return state
