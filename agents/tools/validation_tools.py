"""
验证工具集

提供格式验证、难度检查、答案验证等工具。
支持 Tool Calling 模式，可被 Agent 直接调用。
"""

import re
import json
from typing import List, Optional, Dict, Any
from agents.tools.base import BaseTool, ToolParameter, ToolResult, register_tool


@register_tool
class ValidateFormatTool(BaseTool):
    """
    格式验证工具

    验证试题格式是否符合标准规范。
    """

    def __init__(self):
        super().__init__()
        self._name = "validate_format"
        self._description = (
            "验证试题格式是否符合标准规范。"
            "检查 JSON 结构、字段类型、必填项等。"
        )
        self._parameters = [
            ToolParameter(
                name="content",
                type="string",
                description="待验证的内容，可以是 JSON 字符串或普通文本",
                required=True
            ),
            ToolParameter(
                name="content_type",
                type="string",
                description="内容类型：question(试题)、questions(试题列表)、json(JSON对象)",
                required=False,
                default="json",
                enum=["question", "questions", "json"]
            )
        ]

    def execute(self, content: str, content_type: str = "json") -> ToolResult:
        """
        执行格式验证

        Args:
            content: 待验证内容
            content_type: 内容类型

        Returns:
            验证结果
        """
        try:
            # JSON 解析测试
            try:
                parsed = json.loads(content)
            except json.JSONDecodeError as e:
                return ToolResult(
                    success=True,
                    data={
                        "is_valid": False,
                        "error": f"JSON 解析失败: {str(e)}",
                        "error_position": f"行 {e.lineno}, 列 {e.colno}"
                    },
                    metadata={"content_type": content_type}
                )

            # 根据类型进行特定验证
            if content_type == "question":
                return self._validate_single_question(parsed)
            elif content_type == "questions":
                return self._validate_question_list(parsed)
            else:
                return ToolResult(
                    success=True,
                    data={
                        "is_valid": True,
                        "message": "JSON 格式有效",
                        "type": type(parsed).__name__
                    },
                    metadata={"content_type": content_type}
                )

        except Exception as e:
            return ToolResult(
                success=False,
                data=None,
                error=f"验证过程出错: {str(e)}"
            )

    def _validate_single_question(self, q: dict) -> ToolResult:
        """验证单个试题"""
        errors = []
        warnings = []

        # 必填字段
        required = ["topic", "question_type", "content", "answer"]
        for field in required:
            if field not in q:
                errors.append(f"缺少必填字段: {field}")

        # 类型检查
        if "question_type" in q:
            valid_types = ["choice", "fill_blank", "essay"]
            if q["question_type"] not in valid_types:
                errors.append(f"无效的题型: {q['question_type']}")

        if "difficulty" in q:
            valid_diff = ["easy", "medium", "hard"]
            if q["difficulty"] not in valid_diff:
                warnings.append(f"非标准难度值: {q['difficulty']}")

        # 选择题选项检查
        if q.get("question_type") == "choice":
            if "options" not in q or not isinstance(q.get("options"), list):
                errors.append("选择题需要 options 字段（数组类型）")
            elif len(q.get("options", [])) < 2:
                errors.append("选择题至少需要 2 个选项")

        return ToolResult(
            success=True,
            data={
                "is_valid": len(errors) == 0,
                "errors": errors,
                "warnings": warnings
            },
            metadata={"question_id": q.get("id", "unknown")}
        )

    def _validate_question_list(self, questions: list) -> ToolResult:
        """验证试题列表"""
        if not isinstance(questions, list):
            return ToolResult(
                success=True,
                data={
                    "is_valid": False,
                    "errors": ["试题列表应为数组类型"],
                    "warnings": []
                },
                metadata={}
            )

        all_errors = []
        question_results = []

        for i, q in enumerate(questions):
            if not isinstance(q, dict):
                all_errors.append(f"第 {i+1} 题不是有效对象")
                continue

            result = self._validate_single_question(q)
            question_results.append({
                "index": i + 1,
                "is_valid": result.data.get("is_valid", False),
                "errors": result.data.get("errors", [])
            })

            if not result.data.get("is_valid", False):
                all_errors.extend(
                    [f"第 {i+1} 题: {e}" for e in result.data.get("errors", [])])

        return ToolResult(
            success=True,
            data={
                "is_valid": len(all_errors) == 0,
                "total_questions": len(questions),
                "valid_questions": sum(1 for r in question_results if r["is_valid"]),
                "errors": all_errors,
                "details": question_results
            },
            metadata={"count": len(questions)}
        )


@register_tool
class CheckDifficultyTool(BaseTool):
    """
    难度检查工具

    检查试题难度设置是否合理。
    """

    def __init__(self):
        super().__init__()
        self._name = "check_difficulty"
        self._description = (
            "检查试题难度设置是否合理。"
            "基于试题内容和知识点评估难度匹配度。"
        )
        self._parameters = [
            ToolParameter(
                name="content",
                type="string",
                description="试题内容",
                required=True
            ),
            ToolParameter(
                name="declared_difficulty",
                type="string",
                description="声明的难度：easy、medium、hard",
                required=True,
                enum=["easy", "medium", "hard"]
            ),
            ToolParameter(
                name="topic",
                type="string",
                description="知识点名称",
                required=False,
                default=""
            )
        ]

    def execute(self, content: str, declared_difficulty: str, topic: str = "") -> ToolResult:
        """
        检查难度

        Args:
            content: 试题内容
            declared_difficulty: 声明的难度
            topic: 知识点

        Returns:
            难度检查结果
        """
        # 难度评估指标
        indicators = {
            "easy": {
                "keywords": ["基础", "简单", "基本", "定义", "概念"],
                "content_length_range": (10, 200),
            },
            "medium": {
                "keywords": ["分析", "比较", "解释", "说明", "应用"],
                "content_length_range": (100, 500),
            },
            "hard": {
                "keywords": ["综合", "设计", "证明", "推导", "创新", "复杂"],
                "content_length_range": (200, 2000),
            }
        }

        # 计算内容长度得分
        content_len = len(content)
        length_scores = {}
        for diff, indicator in indicators.items():
            min_len, max_len = indicator["content_length_range"]
            if min_len <= content_len <= max_len:
                length_scores[diff] = 1.0
            elif content_len < min_len:
                length_scores[diff] = content_len / min_len
            else:
                length_scores[diff] = max(
                    0, 1 - (content_len - max_len) / max_len)

        # 计算关键词匹配得分
        keyword_scores = {}
        for diff, indicator in indicators.items():
            matches = sum(1 for kw in indicator["keywords"] if kw in content)
            keyword_scores[diff] = min(1.0, matches / 3)

        # 综合评分
        total_scores = {}
        for diff in ["easy", "medium", "hard"]:
            total_scores[diff] = 0.6 * length_scores[diff] + \
                0.4 * keyword_scores[diff]

        # 预测难度
        predicted = max(total_scores, key=total_scores.get)

        # 判断是否匹配
        is_match = predicted == declared_difficulty

        # 生成建议
        suggestions = []
        if not is_match:
            suggestions.append(
                f"声明难度为 '{declared_difficulty}'，但内容特征更接近 '{predicted}'")
            if total_scores[predicted] > total_scores[declared_difficulty] + 0.2:
                suggestions.append("建议调整难度标签或修改试题内容")

        return ToolResult(
            success=True,
            data={
                "is_match": is_match,
                "declared_difficulty": declared_difficulty,
                "predicted_difficulty": predicted,
                "confidence": total_scores[predicted],
                "scores": total_scores,
                "suggestions": suggestions
            },
            metadata={"content_length": content_len, "topic": topic}
        )


@register_tool
class ValidateAnswerTool(BaseTool):
    """
    答案验证工具

    验证试题答案的正确性和完整性。
    """

    def __init__(self):
        super().__init__()
        self._name = "validate_answer"
        self._description = (
            "验证试题答案的正确性和完整性。"
            "检查答案格式、是否与选项匹配等。"
        )
        self._parameters = [
            ToolParameter(
                name="question_type",
                type="string",
                description="题型：choice、fill_blank、essay",
                required=True,
                enum=["choice", "fill_blank", "essay"]
            ),
            ToolParameter(
                name="answer",
                type="string",
                description="试题答案",
                required=True
            ),
            ToolParameter(
                name="options",
                type="string",
                description="选择题选项（JSON 数组字符串），仅选择题需要",
                required=False,
                default="[]"
            ),
            ToolParameter(
                name="explanation",
                type="string",
                description="答案解析",
                required=False,
                default=""
            )
        ]

    def execute(
        self,
        question_type: str,
        answer: str,
        options: str = "[]",
        explanation: str = ""
    ) -> ToolResult:
        """
        验证答案

        Args:
            question_type: 题型
            answer: 答案
            options: 选项（选择题）
            explanation: 解析

        Returns:
            验证结果
        """
        issues = []
        warnings = []

        # 基本检查
        if not answer or not answer.strip():
            issues.append("答案为空")
            return ToolResult(
                success=True,
                data={"is_valid": False, "issues": issues, "warnings": warnings},
                metadata={"question_type": question_type}
            )

        answer = answer.strip()

        # 题型特定检查
        if question_type == "choice":
            # 解析选项
            try:
                options_list = json.loads(options) if isinstance(
                    options, str) else options
            except json.JSONDecodeError:
                options_list = []

            # 检查答案格式（应为 A、B、C、D 等）
            answer_pattern = r'^[A-Za-z](,?\s*[A-Za-z])*$'  # 支持多选
            if not re.match(answer_pattern, answer):
                warnings.append(f"选择题答案格式不标准: '{answer}'，建议使用 A、B、C、D 格式")

            # 检查答案是否在选项范围内
            if options_list:
                # A, B, C, ...
                valid_letters = [chr(65 + i) for i in range(len(options_list))]
                answer_letters = [a.strip().upper() for a in answer.split(',')]
                for letter in answer_letters:
                    if letter not in valid_letters:
                        issues.append(f"答案 '{letter}' 超出选项范围 {valid_letters}")

        elif question_type == "fill_blank":
            # 填空题答案检查
            if len(answer) < 1:
                issues.append("填空题答案过短")
            # 检查是否有多个答案
            if ';' in answer or '；' in answer or '或' in answer:
                warnings.append("检测到可能的多个答案，请确认格式")

        elif question_type == "essay":
            # 解答题答案检查
            if len(answer) < 10:
                warnings.append("解答题答案过短，可能不够完整")

        # 解析检查
        if not explanation:
            warnings.append("缺少答案解析")
        elif len(explanation) < 10:
            warnings.append("解析内容过短")

        return ToolResult(
            success=True,
            data={
                "is_valid": len(issues) == 0,
                "issues": issues,
                "warnings": warnings,
                "answer_length": len(answer),
                "has_explanation": bool(explanation)
            },
            metadata={"question_type": question_type}
        )


@register_tool
class CheckScientificTool(BaseTool):
    """
    科学性检查工具

    检查试题内容的科学性和准确性。
    """

    def __init__(self):
        super().__init__()
        self._name = "check_scientific"
        self._description = (
            "检查试题内容的科学性和准确性。"
            "识别可能的科学性错误或不规范表述。"
        )
        self._parameters = [
            ToolParameter(
                name="content",
                type="string",
                description="试题内容",
                required=True
            ),
            ToolParameter(
                name="topic",
                type="string",
                description="知识点",
                required=False,
                default=""
            )
        ]

    def execute(self, content: str, topic: str = "") -> ToolResult:
        """
        检查科学性

        Args:
            content: 试题内容
            topic: 知识点

        Returns:
            检查结果
        """
        warnings = []
        suggestions = []

        # 常见问题模式
        problem_patterns = [
            (r'大约\s*\d+\s*左右', "数值表述冗余：'大约...左右' 语义重复"),
            (r'可能\s*也许', "表述冗余：'可能也许' 语义重复"),
            (r'\d+\s*多个', "数量表述模糊，建议明确具体数字"),
            (r'[。，]{2,}', "标点符号重复"),
            (r'[？!]{2,}', "问号或感叹号重复"),
        ]

        for pattern, message in problem_patterns:
            if re.search(pattern, content):
                warnings.append(message)

        # 内容完整性检查
        if len(content) < 20:
            suggestions.append("试题内容过短，可能信息不完整")

        # 检查是否有明确的问句
        if '?' not in content and '？' not in content:
            if '选择' not in content and '填空' not in content:
                suggestions.append("试题可能缺少明确的提问部分")

        # 检查是否有歧义表述
        ambiguous_words = ["有些", "某些", "部分", "可能", "大概"]
        ambiguous_count = sum(1 for word in ambiguous_words if word in content)
        if ambiguous_count > 2:
            warnings.append(f"检测到 {ambiguous_count} 处模糊表述，可能影响试题明确性")

        return ToolResult(
            success=True,
            data={
                "is_valid": len(warnings) == 0,
                "warnings": warnings,
                "suggestions": suggestions,
                "content_length": len(content)
            },
            metadata={"topic": topic, "warning_count": len(warnings)}
        )


# 便捷函数：获取验证工具列表
def get_validation_tools() -> List[BaseTool]:
    """
    获取所有验证工具

    Returns:
        工具列表
    """
    from agents.tools.base import registry
    return registry.get_tools([
        "validate_format",
        "check_difficulty",
        "validate_answer",
        "check_scientific"
    ])
