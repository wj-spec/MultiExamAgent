"""
试题生成 Agent (Tool Calling 版本)

使用 Tool Calling 模式进行试题生成。
支持知识检索、试题生成、格式验证等工具调用。
"""

import json
import re
import uuid
from typing import Dict, Any, Optional, List
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import SystemMessage, HumanMessage

from agents.base import ToolCallingAgent, AgentTrace
from agents.tools.base import BaseTool, ToolParameter, ToolResult, register_tool
from graphs.state import AgentState, add_status_message
from utils.config import get_llm


# ==================== Creator 专用工具 ====================

@register_tool
class CreateQuestionTool(BaseTool):
    """
    试题创建工具

    创建单个试题的结构化数据。
    """

    def __init__(self):
        super().__init__()
        self._name = "create_question"
        self._description = (
            "创建单个试题的结构化数据。"
            "返回包含题目、选项、答案、解析的完整试题对象。"
        )
        self._parameters = [
            ToolParameter(
                name="content",
                type="string",
                description="试题内容/题干",
                required=True
            ),
            ToolParameter(
                name="question_type",
                type="string",
                description="题型：choice/fill_blank/essay",
                required=True,
                enum=["choice", "fill_blank", "essay"]
            ),
            ToolParameter(
                name="options",
                type="string",
                description="选择题选项，JSON数组格式，如[\"A. 选项1\", \"B. 选项2\"]",
                required=False,
                default="[]"
            ),
            ToolParameter(
                name="answer",
                type="string",
                description="正确答案",
                required=True
            ),
            ToolParameter(
                name="explanation",
                type="string",
                description="答案解析",
                required=True
            ),
            ToolParameter(
                name="difficulty",
                type="string",
                description="难度：easy/medium/hard",
                required=False,
                default="medium"
            )
        ]

    def execute(
        self,
        content: str,
        question_type: str,
        answer: str,
        explanation: str,
        options: str = "[]",
        difficulty: str = "medium"
    ) -> ToolResult:
        """执行试题创建"""
        try:
            options_list = json.loads(options) if isinstance(
                options, str) else options
        except json.JSONDecodeError:
            options_list = []

        question = {
            "id": f"q_{uuid.uuid4().hex[:8]}",
            "content": content,
            "question_type": question_type,
            "options": options_list,
            "answer": answer,
            "explanation": explanation,
            "difficulty": difficulty,
            "audit_passed": False,
            "audit_feedback": None
        }

        return ToolResult(
            success=True,
            data=question
        )


@register_tool
class BatchCreateQuestionsTool(BaseTool):
    """
    批量试题创建工具

    一次创建多个试题。
    """

    def __init__(self):
        super().__init__()
        self._name = "batch_create_questions"
        self._description = (
            "一次创建多个试题。"
            "用于批量生成试题的场景。"
        )
        self._parameters = [
            ToolParameter(
                name="questions",
                type="string",
                description="JSON数组格式的试题列表",
                required=True
            )
        ]

    def execute(self, questions: str) -> ToolResult:
        """执行批量创建"""
        try:
            questions_list = json.loads(questions) if isinstance(
                questions, str) else questions

            # 为每个试题添加 ID
            for q in questions_list:
                if "id" not in q:
                    q["id"] = f"q_{uuid.uuid4().hex[:8]}"
                q.setdefault("audit_passed", False)
                q.setdefault("audit_feedback", None)

            return ToolResult(
                success=True,
                data={
                    "questions": questions_list,
                    "count": len(questions_list)
                }
            )
        except json.JSONDecodeError as e:
            return ToolResult(
                success=False,
                data=None,
                error=f"JSON 解析失败: {str(e)}"
            )


@register_tool
class EnhanceQuestionTool(BaseTool):
    """
    试题增强工具

    根据审核反馈增强或修改试题。
    """

    def __init__(self):
        super().__init__()
        self._name = "enhance_question"
        self._description = (
            "根据审核反馈增强或修改试题。"
            "用于试题修正和优化。"
        )
        self._parameters = [
            ToolParameter(
                name="question_id",
                type="string",
                description="要修改的试题ID",
                required=True
            ),
            ToolParameter(
                name="modifications",
                type="string",
                description="JSON对象格式的修改内容",
                required=True
            ),
            ToolParameter(
                name="reason",
                type="string",
                description="修改原因",
                required=True
            )
        ]

    def execute(self, question_id: str, modifications: str, reason: str) -> ToolResult:
        """执行试题增强"""
        try:
            mods = json.loads(modifications) if isinstance(
                modifications, str) else modifications

            return ToolResult(
                success=True,
                data={
                    "question_id": question_id,
                    "modifications": mods,
                    "reason": reason,
                    "enhanced": True
                }
            )
        except json.JSONDecodeError as e:
            return ToolResult(
                success=False,
                data=None,
                error=f"JSON 解析失败: {str(e)}"
            )


# ==================== Creator Agent ====================

CREATOR_SYSTEM_PROMPT = """你是一个专业的试题生成 Agent，负责根据知识点和要求生成高质量试题。

## 可用工具
1. create_question: 创建单个试题
2. batch_create_questions: 批量创建试题
3. enhance_question: 增强或修改试题

## ⚠️ 重要约束（必须严格遵守）
1. **题型一致性**：所有生成的试题必须使用同一个题型（question_type），不能混合不同题型
2. **参数强制要求**：必须严格按照用户指定的题型参数生成试题，question_type 参数只能是以下值之一：
   - "choice": 选择题
   - "fill_blank": 填空题  
   - "essay": 解答题/简答题
3. 如果用户要求生成选择题，所有题目的 question_type 必须都是 "choice"
4. 如果用户要求生成填空题，所有题目的 question_type 必须都是 "fill_blank"
5. 如果用户要求生成解答题，所有题目的 question_type 必须都是 "essay"

## 试题生成原则
1. 科学性：内容准确，无科学性错误
2. 规范性：表述规范，语言通顺
3. 适切性：难度匹配，符合目标群体
4. 完整性：题干、选项、答案、解析齐全

## 工作流程
1. 分析知识点和需求，确定题型
2. 调用 create_question 或 batch_create_questions 生成试题
3. 确保每个试题的 question_type 与用户要求完全一致
4. 确保每个试题包含完整的内容、答案和解析

## 选择题规范 (question_type="choice")
- 选项数量：必须包含 4 个选项
- 选项格式：A. 选项内容
- 答案格式：单个字母，如 "A"
- 必须提供 options 参数

## 填空题规范 (question_type="fill_blank")
- 使用 ____ 或 （  ） 表示填空位置
- 答案应简洁明确
- 不需要 options 参数

## 解答题规范 (question_type="essay")
- 题目应明确具体
- 答案应包含完整的解题过程
- 解析应详细说明解题思路
- 不需要 options 参数

## 示例
生成5道代数选择题（注意：所有题目的 question_type 都是 "choice"）:
调用 batch_create_questions(
    questions='[
        {
            "content": "已知 x + 5 = 12，则 x 的值是",
            "question_type": "choice",
            "options": ["A. 5", "B. 6", "C. 7", "D. 8"],
            "answer": "C",
            "explanation": "移项得 x = 12 - 5 = 7",
            "difficulty": "easy"
        }
    ]'
)
"""


class CreatorAgentV2(ToolCallingAgent):
    """
    试题生成 Agent V2

    使用 Tool Calling 模式进行试题生成。
    """

    def __init__(self, llm: Optional[BaseChatModel] = None):
        super().__init__(
            llm=llm or get_llm(temperature=0.7),
            tools=[
                CreateQuestionTool(),
                BatchCreateQuestionsTool(),
                EnhanceQuestionTool()
            ],
            max_iterations=5,
            verbose=False
        )

        # 存储生成的试题
        self._generated_questions: List[Dict] = []

    @property
    def name(self) -> str:
        return "creator"

    @property
    def system_prompt(self) -> str:
        return CREATOR_SYSTEM_PROMPT

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
        # 构建输入（强调题型约束）
        question_type_cn = {
            "choice": "选择题",
            "fill_blank": "填空题",
            "essay": "解答题"
        }.get(question_type, question_type)

        user_input = f"请生成 {count} 道{question_type_cn}：\n"
        user_input += f"- 知识点: {topic}\n"
        user_input += f"- 题型: {question_type}（{question_type_cn}）\n"
        user_input += f"- 难度: {difficulty}\n"
        user_input += f"\n⚠️ 重要：所有 {count} 道题目必须是{question_type_cn}，question_type 参数必须全部为 \"{question_type}\"，不能混合其他题型！\n"
        if knowledge_context:
            user_input += f"\n相关知识内容：\n{knowledge_context[:2000]}\n"
        if additional_requirements:
            user_input += f"\n额外要求: {additional_requirements}\n"

        # 运行 Agent
        trace = self.run_with_tools(user_input)

        # 收集生成的试题
        questions = []
        for decision in trace.decisions:
            if decision.action == "create_question":
                # 单个试题
                if decision.observation:
                    try:
                        result = json.loads(decision.observation)
                        if result.get("success") and result.get("data"):
                            questions.append(result["data"])
                    except json.JSONDecodeError:
                        pass

            elif decision.action == "batch_create_questions":
                # 批量试题
                if decision.observation:
                    try:
                        result = json.loads(decision.observation)
                        if result.get("success") and result.get("data", {}).get("questions"):
                            questions.extend(result["data"]["questions"])
                    except json.JSONDecodeError:
                        pass

        # 如果没有通过工具生成，尝试从最终结果解析
        if not questions and trace.final_result:
            questions = self._parse_questions_from_text(trace.final_result)

        # 确保数量
        while len(questions) < count:
            # 生成默认试题
            questions.append({
                "id": f"q_{uuid.uuid4().hex[:8]}",
                "content": f"[待完善] {topic} 相关试题",
                "question_type": question_type,
                "options": ["A. 选项A", "B. 选项B", "C. 选项C", "D. 选项D"] if question_type == "choice" else [],
                "answer": "A" if question_type == "choice" else "待填写",
                "explanation": "待完善解析",
                "difficulty": difficulty,
                "topic": topic,
                "audit_passed": False,
                "audit_feedback": None
            })

        # 截取到指定数量
        questions = questions[:count]

        # 确保每个试题都有必要字段
        for q in questions:
            q.setdefault("topic", topic)
            q.setdefault("question_type", question_type)
            q.setdefault("difficulty", difficulty)

        self._generated_questions = questions
        return questions

    def _parse_questions_from_text(self, text: str) -> List[Dict[str, Any]]:
        """
        从文本中解析试题

        Args:
            text: 文本内容

        Returns:
            试题列表
        """
        questions = []

        # 尝试提取 JSON 数组
        json_match = re.search(r'\[[\s\S]*\]', text)
        if json_match:
            try:
                questions = json.loads(json_match.group())
                for q in questions:
                    if "id" not in q:
                        q["id"] = f"q_{uuid.uuid4().hex[:8]}"
                    q.setdefault("audit_passed", False)
                    q.setdefault("audit_feedback", None)
            except json.JSONDecodeError:
                pass

        return questions


# ==================== 兼容旧版本的节点函数 ====================

def creator_node_v2(state: AgentState) -> AgentState:
    """
    试题生成节点函数 V2

    使用 Tool Calling 版本的 Creator Agent。
    与旧版本保持兼容的接口。
    """
    new_state = add_status_message(state, "✍️ 正在生成试题...")

    # 获取参数
    params = state["extracted_params"]

    # 创建生成 Agent
    agent = CreatorAgentV2()

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

    # 保存追踪信息
    if agent.get_trace():
        new_state["agent_trace"] = agent.get_trace().to_dict()

    return new_state
