"""
执行器 Agent (Executor Agent)

第三层核心模块，包含试题生成、质检和循环修正的协作闭环。
"""

import json
import re
import uuid
from typing import Dict, Any, Optional, List
from langchain_core.language_models import BaseChatModel
from langchain_core.output_parsers import StrOutputParser
from langchain_openai import ChatOpenAI

from graphs.state import (
    AgentState, add_status_message, QuestionItem
)
from utils.prompts import CREATOR_PROMPT, AUDITOR_PROMPT
from rag_engine.hybrid_retriever import get_hybrid_retriever
from utils.config import get_llm


class CreatorAgent:
    """
    试题生成 Agent

    根据需求参数和知识库内容生成试题。
    """

    def __init__(self, llm: Optional[BaseChatModel] = None):
        """
        初始化生成 Agent

        Args:
            llm: 语言模型实例
        """
        self.llm = llm or get_llm(temperature=0.7)

    def _parse_questions(self, response: str) -> List[Dict[str, Any]]:
        """
        解析生成的试题

        Args:
            response: LLM 返回的响应

        Returns:
            试题列表
        """
        # 尝试提取 JSON 数组
        json_match = re.search(r'\[[\s\S]*\]', response)
        if json_match:
            try:
                questions = json.loads(json_match.group())
                # 确保每个试题都有 ID
                for i, q in enumerate(questions):
                    if "id" not in q:
                        q["id"] = f"q_{uuid.uuid4().hex[:8]}"
                    # 设置默认值
                    q.setdefault("audit_passed", False)
                    q.setdefault("audit_feedback", None)
                return questions
            except json.JSONDecodeError:
                pass

        return []

    def generate(
        self,
        topic: str,
        question_type: str,
        difficulty: str,
        count: int,
        knowledge_context: str = "",
        additional_requirements: str = ""
    ) -> List[Dict[str, Any]]:
        """
        生成试题

        Args:
            topic: 知识点
            question_type: 题型
            difficulty: 难度
            count: 数量
            knowledge_context: 知识库上下文
            additional_requirements: 额外要求

        Returns:
            生成的试题列表
        """
        # 构建并执行链
        chain = CREATOR_PROMPT | self.llm | StrOutputParser()

        try:
            response = chain.invoke({
                "knowledge_context": knowledge_context or "无相关知识库内容",
                "topic": topic,
                "question_type": question_type,
                "difficulty": difficulty,
                "count": count,
                "additional_requirements": additional_requirements or "无"
            })
            return self._parse_questions(response)
        except Exception as e:
            print(f"试题生成出错: {e}")
            return []


class AuditorAgent:
    """
    质检 Agent

    审核试题的科学性、规范性和适切性。
    """

    def __init__(self, llm: Optional[BaseChatModel] = None):
        """
        初始化质检 Agent

        Args:
            llm: 语言模型实例
        """
        self.llm = llm or get_llm(temperature=0)

    def _parse_audit_result(self, response: str) -> Dict[str, Any]:
        """
        解析审核结果

        Args:
            response: LLM 返回的响应

        Returns:
            审核结果字典
        """
        # 尝试提取 JSON
        json_match = re.search(r'\{[\s\S]*\}', response)
        if json_match:
            try:
                result = json.loads(json_match.group())
                return {
                    "passed": result.get("passed", False),
                    "feedback": result.get("feedback", ""),
                    "issues": result.get("issues", [])
                }
            except json.JSONDecodeError:
                pass

        return {
            "passed": False,
            "feedback": "无法解析审核结果",
            "issues": []
        }

    def audit(
        self,
        questions: List[Dict[str, Any]],
        topic: str,
        question_type: str,
        difficulty: str,
        skills_tools: List = None,
        skills_prompt: str = ""
    ) -> Dict[str, Any]:
        """
        审核试题

        Args:
            questions: 待审核的试题列表
            topic: 知识点
            question_type: 题型
            difficulty: 难度
            skills_tools: 技能注入的 LangChain Tools 列表（可选）
            skills_prompt: 技能注入的额外 Prompt（可选）

        Returns:
            审核结果
        """
        try:
            questions_str = json.dumps(questions, ensure_ascii=False, indent=2)

            # 如果有 Skills 工具，使用 tool-calling 模式
            if skills_tools:
                return self._audit_with_skills(
                    questions_str, topic, question_type, difficulty,
                    skills_tools, skills_prompt
                )

            # 标准审核（无 Skills）
            chain = AUDITOR_PROMPT | self.llm | StrOutputParser()
            response = chain.invoke({
                "questions": questions_str,
                "topic": topic,
                "question_type": question_type,
                "difficulty": difficulty
            })
            return self._parse_audit_result(response)

        except Exception as e:
            print(f"试题审核出错: {e}")
            return {
                "passed": False,
                "feedback": f"审核出错: {str(e)}",
                "issues": []
            }

    def _audit_with_skills(
        self,
        questions_str: str,
        topic: str,
        question_type: str,
        difficulty: str,
        skills_tools: list,
        skills_prompt: str
    ) -> Dict[str, Any]:
        """
        使用 Skills 增强审核（tool-calling 模式）

        Args:
            questions_str: JSON 格式的试题字符串
            topic: 知识点
            question_type: 题型
            difficulty: 难度
            skills_tools: LangChain Tool 列表
            skills_prompt: 额外 Prompt

        Returns:
            审核结果
        """
        from langchain_core.messages import SystemMessage, HumanMessage

        # 构建系统消息（包含 Skills Prompt）
        system_msg = (
            "你是一个专业的试题质检 Agent。请审核以下试题的科学性、规范性和适切性。\n\n"
            f"知识点: {topic}\n题型: {question_type}\n难度: {difficulty}\n\n"
        )
        if skills_prompt:
            system_msg += f"\n{skills_prompt}\n"

        system_msg += (
            "\n请审核完成后，返回 JSON 格式的审核结果：\n"
            '{"passed": true/false, "feedback": "审核反馈", "issues": ["问题列表"]}'
        )

        human_msg = f"请审核以下试题：\n\n{questions_str}"

        messages = [
            SystemMessage(content=system_msg),
            HumanMessage(content=human_msg)
        ]

        # 绑定工具到 LLM
        llm_with_tools = self.llm.bind_tools(skills_tools)

        try:
            # 第一轮调用
            response = llm_with_tools.invoke(messages)

            # 处理可能的 tool calls（最多迭代 3 轮）
            tool_map = {t.name: t for t in skills_tools}
            max_iterations = 3

            for _ in range(max_iterations):
                if not hasattr(response, "tool_calls") or not response.tool_calls:
                    break

                # 执行 tool calls
                messages.append(response)
                from langchain_core.messages import ToolMessage
                for tc in response.tool_calls:
                    tool_name = tc["name"]
                    tool_args = tc["args"]
                    if tool_name in tool_map:
                        try:
                            result = tool_map[tool_name].invoke(tool_args)
                            messages.append(ToolMessage(
                                content=str(result),
                                tool_call_id=tc["id"]
                            ))
                        except Exception as e:
                            messages.append(ToolMessage(
                                content=f"工具执行失败: {str(e)}",
                                tool_call_id=tc["id"]
                            ))

                # 继续对话
                response = llm_with_tools.invoke(messages)

            # 提取最终文本内容
            final_text = response.content if hasattr(
                response, "content") else str(response)
            return self._parse_audit_result(final_text)

        except Exception as e:
            print(f"Skills 增强审核出错: {e}")
            # 降级到标准审核
            chain = AUDITOR_PROMPT | self.llm | StrOutputParser()
            response = chain.invoke({
                "questions": questions_str,
                "topic": topic,
                "question_type": question_type,
                "difficulty": difficulty
            })
            return self._parse_audit_result(response)


def knowledge_retrieval_node(state: AgentState) -> AgentState:
    """
    知识检索节点

    使用多源混合检索器从多个来源检索相关知识内容。
    支持本地知识库、网络搜索和深度网页爬取。

    Args:
        state: 当前状态

    Returns:
        更新后的状态
    """
    new_state = add_status_message(state, "正在智能检索知识...")

    # 获取知识点和额外要求
    params = state.get("extracted_params", {})
    topic = params.get("topic", "")
    additional_requirements = params.get("additional_requirements", "")

    # 构建检索查询
    query = f"{topic} {additional_requirements}".strip()

    # 使用多源混合检索器
    retriever = get_hybrid_retriever()
    result = retriever.smart_retrieve(query, top_k=4, use_rerank=True)

    # 更新状态
    new_state = dict(new_state)
    new_state["retrieved_knowledge"] = result["context_str"]
    new_state["route_decision"] = result["route_decision"]
    new_state["search_route"] = result["route"]
    new_state["search_query"] = result["search_query"]
    new_state["search_sources"] = result["sources_info"]
    new_state["current_step_index"] = 1
    new_state["current_step"] = "生成试题"
    new_state["next_node"] = "creator"

    # 添加状态消息
    route = result["route"]
    doc_count = result["doc_count"]
    route_messages = {
        "local": f"检索本地知识库完成，找到 {doc_count} 条相关内容",
        "api": f"网络搜索完成，找到 {doc_count} 条相关资讯",
        "browser": f"深度网页提取完成，找到 {doc_count} 条内容",
        "hybrid": f"多源混合检索完成，找到 {doc_count} 条相关内容"
    }
    new_state = add_status_message(
        new_state, route_messages.get(route, f"检索完成，找到 {doc_count} 条内容"))

    return new_state


def creator_node(state: AgentState) -> AgentState:
    """
    试题生成节点

    根据参数和知识库内容生成试题。

    Args:
        state: 当前状态

    Returns:
        更新后的状态
    """
    new_state = add_status_message(state, "✍️ 正在生成试题...")

    # 获取参数
    params = state["extracted_params"]

    # 创建生成 Agent
    agent = CreatorAgent()

    # 生成试题
    questions = agent.generate(
        topic=params.get("topic", ""),
        question_type=params.get("question_type", ""),
        difficulty=params.get("difficulty", ""),
        count=params.get("count", 1),
        knowledge_context=state.get("retrieved_knowledge", ""),
        additional_requirements=params.get("additional_requirements", "")
    )

    # 更新状态
    new_state = dict(new_state)
    new_state["draft_questions"] = questions
    new_state["current_step_index"] = 2
    new_state["current_step"] = "质量审核"
    new_state["next_node"] = "auditor"

    if questions:
        new_state = add_status_message(
            new_state, f"📝 已生成 {len(questions)} 道试题")
    else:
        new_state = add_status_message(new_state, "⚠️ 试题生成失败")
        new_state["error_message"] = "试题生成失败"

    return new_state


def auditor_node(state: AgentState) -> AgentState:
    """
    质检节点

    审核生成的试题，决定是否通过或需要修订。

    Args:
        state: 当前状态

    Returns:
        更新后的状态
    """
    new_state = add_status_message(state, "🧐 正在进行质量审核...")

    # 获取参数
    params = state["extracted_params"]
    questions = state["draft_questions"]

    # 创建质检 Agent
    agent = AuditorAgent()

    # 审核试题
    audit_result = agent.audit(
        questions=questions,
        topic=params.get("topic", ""),
        question_type=params.get("question_type", ""),
        difficulty=params.get("difficulty", "")
    )

    # 更新状态
    new_state = dict(new_state)
    new_state["audit_feedback"] = audit_result["feedback"]
    new_state["current_step_index"] = 3

    if audit_result["passed"]:
        # 审核通过
        new_state["next_node"] = "consolidator"
        new_state = add_status_message(new_state, "✅ 质量审核通过")

        # 标记所有试题为已通过
        for q in new_state["draft_questions"]:
            q["audit_passed"] = True
    else:
        # 审核未通过
        revision_count = state["revision_count"] + 1
        new_state["revision_count"] = revision_count

        if revision_count >= state["max_revisions"]:
            # 达到最大修订次数，强制通过
            new_state["next_node"] = "consolidator"
            new_state = add_status_message(
                new_state,
                f"⚠️ 已达最大修订次数({revision_count})，使用当前版本"
            )
        else:
            # 需要修订
            new_state["next_node"] = "creator"
            new_state = add_status_message(
                new_state,
                f"⚠️ 审核发现问题: {audit_result['feedback'][:50]}...，正在修正({revision_count}/{state['max_revisions']})"
            )

            # 将问题反馈添加到参数中
            params_copy = dict(params)
            params_copy["additional_requirements"] = (
                f"{params.get('additional_requirements', '')}\n"
                f"请修正以下问题: {audit_result['feedback']}"
            )
            new_state["extracted_params"] = params_copy

    return new_state


def format_questions_response(questions: List[Dict[str, Any]]) -> str:
    """
    格式化试题响应

    将试题列表转换为用户友好的 Markdown 格式。

    Args:
        questions: 试题列表

    Returns:
        格式化的响应字符串
    """
    if not questions:
        return "抱歉，未能生成试题。"

    response = "# 生成的试题\n\n"

    difficulty_map = {
        "easy": "简单",
        "medium": "中等",
        "hard": "困难"
    }

    question_type_map = {
        "choice": "选择题",
        "fill_blank": "填空题",
        "essay": "解答题"
    }

    for i, q in enumerate(questions, 1):
        q_type = q.get("question_type", "choice")
        difficulty = q.get("difficulty", 0.5)

        # 难度描述
        if isinstance(difficulty, (int, float)):
            if difficulty >= 0.8:
                diff_str = "困难"
            elif difficulty >= 0.5:
                diff_str = "中等"
            else:
                diff_str = "简单"
        else:
            diff_str = difficulty_map.get(difficulty, "中等")

        response += f"## 第 {i} 题\n\n"
        response += f"**题型**: {question_type_map.get(q_type, q_type)}\n"
        response += f"**难度**: {diff_str}\n"
        response += f"**知识点**: {q.get('topic', '未知')}\n\n"
        response += f"{q.get('content', '')}\n\n"

        # 选择题选项
        if q_type == "choice" and q.get("options"):
            for opt in q["options"]:
                response += f"{opt}\n"
            response += "\n"

        # 答案和解析（默认折叠）
        response += f"<details>\n<summary>点击查看答案与解析</summary>\n\n"
        response += f"**答案**: {q.get('answer', '暂无')}\n\n"
        response += f"**解析**: {q.get('explanation', '暂无解析')}\n\n"
        response += f"</details>\n\n"
        response += "---\n\n"

    return response
