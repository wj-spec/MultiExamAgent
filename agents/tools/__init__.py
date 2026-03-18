"""
Agent Tools 模块

提供各 Agent 可调用的工具集，支持 Tool Calling 模式。
"""

from agents.tools.base import BaseTool, ToolRegistry
from agents.tools.knowledge_tools import (
    SearchKnowledgeTool,
    GetDocumentSummaryTool,
    ListCollectionsTool
)
from agents.tools.question_tools import (
    GenerateQuestionTool,
    FormatQuestionsTool,
    ValidateQuestionTool
)
from agents.tools.validation_tools import (
    ValidateFormatTool,
    CheckDifficultyTool,
    ValidateAnswerTool
)

__all__ = [
    # Base
    "BaseTool",
    "ToolRegistry",
    # Knowledge Tools
    "SearchKnowledgeTool",
    "GetDocumentSummaryTool",
    "ListCollectionsTool",
    # Question Tools
    "GenerateQuestionTool",
    "FormatQuestionsTool",
    "ValidateQuestionTool",
    # Validation Tools
    "ValidateFormatTool",
    "CheckDifficultyTool",
    "ValidateAnswerTool",
]
