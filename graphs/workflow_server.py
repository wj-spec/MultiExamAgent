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

from agents.router_agent import RouterAgent
from agents.memory_agent import MemoryCognitiveAgent
from agents.planner_agent import PlannerAgent
from agents.executor_agent import CreatorAgent, AuditorAgent, format_questions_response
from agents.consolidator_agent import ConsolidatorAgent
from utils.config import get_llm

# 回调类型定义
StatusCallback = Optional[Callable[[str, str, Optional[dict]], Awaitable[None]]]


async def _cb(callback: StatusCallback, step: str, content: str, params: dict = None):
    """安全调用回调（callback 可为 None）"""
    if callback:
        await callback(step, content, params)


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
    topic_changed = check_topic_changed(state)
    last_intent = state.get("last_intent", "")

    if not topic_changed and last_intent == "proposition":
        await _cb(callback, StepNames.ROUTER, "📌 话题延续，跳过意图识别 → 命题")
        new_state = dict(state)
        new_state["intent"] = last_intent
        new_state["topic_changed"] = False
        return new_state

    await _cb(callback, StepNames.ROUTER, "正在分析用户意图...")

    agent = RouterAgent()
    result = agent.route(state["user_input"])
    intent = result["intent"]
    reason = result["reason"]

    intent_emoji = {"proposition": "📋", "grading": "📝", "chat": "💬"}.get(intent, "❓")
    await _cb(callback, StepNames.ROUTER, f"{intent_emoji} 识别意图: {intent} — {reason}")

    new_state = dict(state)
    new_state["intent"] = intent
    new_state["routing_reason"] = reason
    new_state["last_intent"] = intent
    new_state["topic_changed"] = True
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


async def ask_user_node(state: AgentState, callback: StatusCallback) -> AgentState:
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

    knowledge = search_knowledge(topic, top_k=3)

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


async def auditor_node(state: AgentState, callback: StatusCallback) -> AgentState:
    revision_count = state.get("revision_count", 0)
    max_revisions = state.get("max_revisions", 3)
    q_count = len(state["draft_questions"])
    await _cb(callback, StepNames.AUDITOR, f"正在审核 {q_count} 道试题 ({revision_count + 1}/{max_revisions})...")

    params = state["extracted_params"]

    # --- Skills 集成 ---
    skills_tools = []
    skills_prompt = ""
    try:
        from skills.registry import get_skill_registry
        registry = get_skill_registry()
        skills_tools = registry.get_tools_for_node("auditor")
        skills_prompt = registry.get_prompts_for_node("auditor")
        if skills_tools:
            skill_names = [t.name for t in skills_tools]
            await _cb(callback, "🔧 技能增强", f"已激活 {len(skills_tools)} 个技能工具: {', '.join(skill_names)}")
    except Exception as e:
        import traceback
        print(f"Skills 加载失败: {e}")
        traceback.print_exc()

    agent = AuditorAgent()
    audit_result = agent.audit(
        questions=state["draft_questions"],
        topic=params.get("topic", ""),
        question_type=params.get("question_type", ""),
        difficulty=params.get("difficulty", ""),
        skills_tools=skills_tools,
        skills_prompt=skills_prompt
    )

    if audit_result["passed"]:
        await _cb(callback, StepNames.AUDITOR, "✅ 审核通过")
    else:
        await _cb(callback, StepNames.AUDITOR,
                  f"⚠️ 审核未通过 ({revision_count + 1}/{max_revisions}): {audit_result['feedback'][:50]}")

    new_state = dict(state)
    new_state["audit_feedback"] = audit_result["feedback"]
    new_state["audit_passed"] = audit_result["passed"]

    if not audit_result["passed"]:
        new_state["revision_count"] = revision_count + 1
        params_copy = dict(params)
        params_copy["additional_requirements"] = (
            f"{params.get('additional_requirements', '')}\n"
            f"请修正: {audit_result['feedback']}"
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
        final_response = format_questions_response(state.get("draft_questions", []))
        await _cb(callback, StepNames.CONSOLIDATOR, "⚠️ 完成但记忆保存失败")

    new_state = dict(state)
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
    status_callback: StatusCallback = None
) -> AgentState:
    """
    纯 async 工作流（不依赖 Chainlit）

    Args:
        state: 初始状态
        chat_history: 对话历史
        status_callback: async def(step_name, content, params=None)

    Returns:
        最终状态
    """
    if chat_history:
        state["chat_history"] = chat_history

    try:
        # 1. 路由
        state = await router_node(state, status_callback)

        if state["intent"] == "proposition":
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

                    state = await auditor_node(state, status_callback)

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
            else:
                # 追问用户
                state = await ask_user_node(state, status_callback)

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
