"""
试题操作工具集

提供试题生成、格式化、验证等工具。
支持 Tool Calling 模式，可被 Agent 直接调用。
"""

import json
import re
import uuid
from typing import List, Optional, Dict, Any
from agents.tools.base import BaseTool, ToolParameter, ToolResult, register_tool


@register_tool
class GenerateQuestionTool(BaseTool):
    """
    试题生成工具

    根据知识点、题型、难度等参数生成试题。
    """

    def __init__(self):
        super().__init__()
        self._name = "generate_question"
        self._description = (
            "根据知识点、题型、难度等参数生成试题。"
            "支持选择题、填空题、解答题等多种题型。"
            "当需要创建新的试题时使用此工具。"
        )
        self._parameters = [
            ToolParameter(
                name="topic",
                type="string",
                description="知识点名称，如'代数'、'辛亥革命'",
                required=True
            ),
            ToolParameter(
                name="question_type",
                type="string",
                description="题型：choice(选择题)、fill_blank(填空题)、essay(解答题)",
                required=True,
                enum=["choice", "fill_blank", "essay"]
            ),
            ToolParameter(
                name="difficulty",
                type="string",
                description="难度：easy(简单)、medium(中等)、hard(困难)",
                required=True,
                enum=["easy", "medium", "hard"]
            ),
            ToolParameter(
                name="knowledge_context",
                type="string",
                description="相关知识内容，用于辅助生成更准确的试题",
                required=False,
                default=""
            ),
            ToolParameter(
                name="additional_requirements",
                type="string",
                description="额外要求，如'需要计算过程'、'结合实际案例'",
                required=False,
                default=""
            )
        ]

    def execute(
        self,
        topic: str,
        question_type: str,
        difficulty: str,
        knowledge_context: str = "",
        additional_requirements: str = ""
    ) -> ToolResult:
        """
        生成试题

        Args:
            topic: 知识点
            question_type: 题型
            difficulty: 难度
            knowledge_context: 知识上下文
            additional_requirements: 额外要求

        Returns:
            生成的试题
        """
        # 注意：这个工具返回的是试题模板，实际生成由 Creator Agent 调用 LLM 完成
        # 这里提供的是结构化的试题框架

        question_id = f"q_{uuid.uuid4().hex[:8]}"

        question_template = {
            "id": question_id,
            "topic": topic,
            "question_type": question_type,
            "difficulty": difficulty,
            "content": "",  # 由 Agent 填充
            "options": [],  # 选择题选项
            "answer": "",  # 答案
            "explanation": "",  # 解析
            "knowledge_context": knowledge_context,
            "additional_requirements": additional_requirements,
            "metadata": {
                "generated": False,
                "needs_llm_generation": True
            }
        }

        return ToolResult(
            success=True,
            data={
                "question_template": question_template,
                "message": "试题模板已创建，需要调用 LLM 生成具体内容"
            },
            metadata={
                "topic": topic,
                "question_type": question_type,
                "difficulty": difficulty
            }
        )


@register_tool
class FormatQuestionsTool(BaseTool):
    """
    试题格式化工具

    将试题列表格式化为用户友好的 Markdown 格式。
    """

    def __init__(self):
        super().__init__()
        self._name = "format_questions"
        self._description = (
            "将试题列表格式化为用户友好的 Markdown 格式。"
            "用于在展示试题给用户之前进行格式化处理。"
        )
        self._parameters = [
            ToolParameter(
                name="questions",
                type="string",
                description="JSON 格式的试题列表字符串",
                required=True
            ),
            ToolParameter(
                name="include_answer",
                type="boolean",
                description="是否包含答案和解析",
                required=False,
                default=True
            )
        ]

    def execute(self, questions: str, include_answer: bool = True) -> ToolResult:
        """
        格式化试题

        Args:
            questions: JSON 格式的试题字符串
            include_answer: 是否包含答案

        Returns:
            格式化后的 Markdown 文本
        """
        try:
            # 解析 JSON
            if isinstance(questions, str):
                question_list = json.loads(questions)
            else:
                question_list = questions

            if not question_list:
                return ToolResult(
                    success=True,
                    data={"markdown": "暂无试题", "count": 0},
                    metadata={}
                )

            # 格式化映射
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

            # 构建 Markdown
            markdown = "# 生成的试题\n\n"

            for i, q in enumerate(question_list, 1):
                q_type = q.get("question_type", "choice")
                difficulty = q.get("difficulty", "medium")

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

                markdown += f"## 第 {i} 题\n\n"
                markdown += f"**题型**: {question_type_map.get(q_type, q_type)}\n"
                markdown += f"**难度**: {diff_str}\n"
                markdown += f"**知识点**: {q.get('topic', '未知')}\n\n"
                markdown += f"{q.get('content', '')}\n\n"

                # 选择题选项
                if q_type == "choice" and q.get("options"):
                    for opt in q["options"]:
                        markdown += f"{opt}\n"
                    markdown += "\n"

                # 答案和解析
                if include_answer:
                    markdown += f"<details>\n<summary>点击查看答案与解析</summary>\n\n"
                    markdown += f"**答案**: {q.get('answer', '暂无')}\n\n"
                    markdown += f"**解析**: {q.get('explanation', '暂无解析')}\n\n"
                    markdown += f"</details>\n\n"

                markdown += "---\n\n"

            return ToolResult(
                success=True,
                data={
                    "markdown": markdown,
                    "count": len(question_list)
                },
                metadata={"include_answer": include_answer}
            )

        except json.JSONDecodeError as e:
            return ToolResult(
                success=False,
                data=None,
                error=f"JSON 解析失败: {str(e)}"
            )
        except Exception as e:
            return ToolResult(
                success=False,
                data=None,
                error=f"格式化试题失败: {str(e)}"
            )


@register_tool
class ValidateQuestionTool(BaseTool):
    """
    试题验证工具

    验证试题的结构完整性和内容有效性。
    """

    def __init__(self):
        super().__init__()
        self._name = "validate_question"
        self._description = (
            "验证试题的结构完整性和内容有效性。"
            "检查试题是否包含必要字段，内容是否合理。"
        )
        self._parameters = [
            ToolParameter(
                name="question",
                type="string",
                description="JSON 格式的试题对象字符串",
                required=True
            )
        ]

    def execute(self, question: str) -> ToolResult:
        """
        验证试题

        Args:
            question: JSON 格式的试题字符串

        Returns:
            验证结果
        """
        try:
            # 解析 JSON
            if isinstance(question, str):
                q = json.loads(question)
            else:
                q = question

            issues = []
            warnings = []

            # 必填字段检查
            required_fields = ["topic", "question_type",
                               "difficulty", "content", "answer"]
            for field in required_fields:
                if field not in q or not q.get(field):
                    issues.append(f"缺少必填字段: {field}")

            # 题型特定检查
            q_type = q.get("question_type", "")
            if q_type == "choice":
                if not q.get("options") or len(q.get("options", [])) < 2:
                    issues.append("选择题至少需要 2 个选项")

                # 检查答案是否在选项中
                answer = q.get("answer", "")
                options = q.get("options", [])
                if answer and options:
                    answer_letters = [opt[0] for opt in options if opt]
                    if answer.upper() not in answer_letters:
                        warnings.append(f"答案 '{answer}' 不在选项中")

            elif q_type == "fill_blank":
                content = q.get("content", "")
                if "____" not in content and "（  ）" not in content and "（）" not in content:
                    warnings.append("填空题内容中未找到填空标记")

            # 难度检查
            difficulty = q.get("difficulty")
            if difficulty not in ["easy", "medium", "hard", None]:
                if not isinstance(difficulty, (int, float)):
                    warnings.append(f"难度值 '{difficulty}' 不标准")

            # 内容长度检查
            content = q.get("content", "")
            if len(content) < 10:
                warnings.append("试题内容过短")
            elif len(content) > 2000:
                warnings.append("试题内容过长，可能影响阅读")

            # 解析检查
            explanation = q.get("explanation", "")
            if not explanation:
                warnings.append("缺少解析内容")

            # 汇总结果
            is_valid = len(issues) == 0

            return ToolResult(
                success=True,
                data={
                    "is_valid": is_valid,
                    "issues": issues,
                    "warnings": warnings,
                    "question_id": q.get("id", "unknown")
                },
                metadata={
                    "issue_count": len(issues),
                    "warning_count": len(warnings)
                }
            )

        except json.JSONDecodeError as e:
            return ToolResult(
                success=False,
                data=None,
                error=f"JSON 解析失败: {str(e)}"
            )
        except Exception as e:
            return ToolResult(
                success=False,
                data=None,
                error=f"验证试题失败: {str(e)}"
            )


@register_tool
class ParseQuestionRequestTool(BaseTool):
    """
    试题请求解析工具

    解析用户的自然语言试题请求，提取结构化参数。
    """

    def __init__(self):
        super().__init__()
        self._name = "parse_question_request"
        self._description = (
            "解析用户的自然语言试题请求，提取知识点、题型、难度、数量等结构化参数。"
            "用于将用户输入转换为可执行的命题参数。"
        )
        self._parameters = [
            ToolParameter(
                name="user_input",
                type="string",
                description="用户的自然语言请求，如'帮我出5道代数选择题'",
                required=True
            )
        ]

    def execute(self, user_input: str) -> ToolResult:
        """
        解析试题请求

        Args:
            user_input: 用户输入

        Returns:
            解析出的参数
        """
        result = {
            "topic": None,
            "question_type": None,
            "difficulty": None,
            "count": 1,
            "additional_requirements": None,
            "raw_input": user_input
        }

        # 数量提取
        count_patterns = [
            r'(\d+)\s*[道个条]',
            r'[出写生成].*?(\d+)',
            r'(\d+)\s*题'
        ]
        for pattern in count_patterns:
            match = re.search(pattern, user_input)
            if match:
                result["count"] = int(match.group(1))
                break

        # 题型提取
        type_keywords = {
            "choice": ["选择题", "单选", "多选", "选择"],
            "fill_blank": ["填空题", "填空", "填"],
            "essay": ["解答题", "简答题", "论述题", "计算题", "解答", "简答"]
        }
        for q_type, keywords in type_keywords.items():
            if any(kw in user_input for kw in keywords):
                result["question_type"] = q_type
                break

        # 难度提取
        difficulty_keywords = {
            "easy": ["简单", "基础", "容易", "入门"],
            "medium": ["中等", "一般", "普通"],
            "hard": ["困难", "难", "挑战", "高难", "复杂"]
        }
        for diff, keywords in difficulty_keywords.items():
            if any(kw in user_input for kw in keywords):
                result["difficulty"] = diff
                break

        # 知识点提取（简单规则，实际应由 LLM 完成）
        # 移除已知关键词后剩余的内容可能是知识点
        stop_words = ["帮我", "请", "出", "生成", "写", "道", "个", "题", "简单", "中等", "困难",
                      "选择题", "填空题", "解答题", "简答题", "计算题", "的", "一些", "若干"]

        cleaned = user_input
        for word in stop_words:
            cleaned = cleaned.replace(word, "")

        # 移除数字
        cleaned = re.sub(r'\d+', '', cleaned)

        if cleaned.strip():
            result["topic"] = cleaned.strip()

        return ToolResult(
            success=True,
            data=result,
            metadata={"extraction_method": "rule_based"}
        )


# 便捷函数：获取试题工具列表
def get_question_tools() -> List[BaseTool]:
    """
    获取所有试题操作工具

    Returns:
        工具列表
    """
    from agents.tools.base import registry
    return registry.get_tools([
        "generate_question",
        "format_questions",
        "validate_question",
        "parse_question_request"
    ])
