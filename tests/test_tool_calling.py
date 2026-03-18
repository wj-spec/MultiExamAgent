"""
Tool Calling 功能测试

测试 Agent 的 Tool Calling 能力。
"""

import pytest
import json
from unittest.mock import Mock, patch, MagicMock

# 测试工具基类


def test_tool_base():
    """测试工具基类"""
    from agents.tools.base import BaseTool, ToolParameter, ToolResult

    class TestTool(BaseTool):
        def __init__(self):
            super().__init__()
            self._name = "test_tool"
            self._description = "测试工具"
            self._parameters = [
                ToolParameter(name="input", type="string",
                              description="输入", required=True)
            ]

        def execute(self, input: str) -> ToolResult:
            return ToolResult(success=True, data={"output": input.upper()})

    tool = TestTool()

    # 测试属性
    assert tool.name == "test_tool"
    assert tool.description == "测试工具"
    assert len(tool.parameters) == 1

    # 测试调用
    result = tool(input="hello")
    assert result.success
    assert result.data["output"] == "HELLO"

    # 测试 OpenAI 格式
    openai_func = tool.to_openai_function()
    assert openai_func["type"] == "function"
    assert openai_func["function"]["name"] == "test_tool"


def test_tool_parameter_validation():
    """测试参数验证"""
    from agents.tools.base import BaseTool, ToolParameter, ToolResult

    class ValidatedTool(BaseTool):
        def __init__(self):
            super().__init__()
            self._name = "validated_tool"
            self._parameters = [
                ToolParameter(name="count", type="integer",
                              description="数量", required=True),
                ToolParameter(name="choice", type="string",
                              description="选择", required=True, enum=["a", "b", "c"])
            ]

        def execute(self, **kwargs) -> ToolResult:
            return ToolResult(success=True, data=kwargs)

    tool = ValidatedTool()

    # 测试缺少必需参数
    result = tool()
    assert not result.success
    assert "缺少必需参数" in result.error

    # 测试无效枚举值
    result = tool(count=1, choice="d")
    assert not result.success
    assert "应为" in result.error

    # 测试有效参数
    result = tool(count=1, choice="a")
    assert result.success


def test_tool_registry():
    """测试工具注册中心"""
    from agents.tools.base import BaseTool, ToolRegistry, ToolParameter, ToolResult, register_tool

    registry = ToolRegistry()

    @register_tool
    class RegistryTestTool(BaseTool):
        def __init__(self):
            super().__init__()
            self._name = "registry_test"
            self._description = "注册测试工具"
            self._parameters = []

        def execute(self) -> ToolResult:
            return ToolResult(success=True, data={"test": True})

    # 检查注册
    assert "registry_test" in registry.list_tools()

    # 获取工具
    tool = registry.get("registry_test")
    assert tool is not None
    assert tool.name == "registry_test"


# 测试知识检索工具
def test_knowledge_tools():
    """测试知识检索工具"""
    from agents.tools.knowledge_tools import SearchKnowledgeTool

    tool = SearchKnowledgeTool()

    # 测试工具属性
    assert tool.name == "search_knowledge"
    assert len(tool.parameters) == 3

    # 测试 OpenAI 格式导出
    openai_func = tool.to_openai_function()
    assert "query" in openai_func["function"]["parameters"]["properties"]


# 测试试题工具
def test_question_tools():
    """测试试题操作工具"""
    from agents.tools.question_tools import (
        GenerateQuestionTool,
        FormatQuestionsTool,
        ValidateQuestionTool
    )

    # 测试生成工具
    gen_tool = GenerateQuestionTool()
    result = gen_tool(topic="代数", question_type="choice", difficulty="easy")
    assert result.success
    assert "question_template" in result.data

    # 测试格式化工具
    format_tool = FormatQuestionsTool()
    questions = json.dumps([{
        "id": "q_001",
        "topic": "代数",
        "question_type": "choice",
        "difficulty": "easy",
        "content": "1+1=?",
        "options": ["A. 1", "B. 2", "C. 3", "D. 4"],
        "answer": "B",
        "explanation": "1+1=2"
    }])
    result = format_tool(questions=questions)
    assert result.success
    assert "# 生成的试题" in result.data["markdown"]

    # 测试验证工具
    valid_tool = ValidateQuestionTool()
    valid_question = json.dumps({
        "id": "q_001",
        "topic": "代数",
        "question_type": "choice",
        "difficulty": "easy",
        "content": "1+1=?",
        "options": ["A. 1", "B. 2", "C. 3", "D. 4"],
        "answer": "B"
    })
    result = valid_tool(question=valid_question)
    assert result.success
    assert result.data["is_valid"]


# 测试验证工具
def test_validation_tools():
    """测试验证工具集"""
    from agents.tools.validation_tools import (
        ValidateFormatTool,
        CheckDifficultyTool,
        ValidateAnswerTool
    )

    # 测试格式验证
    format_tool = ValidateFormatTool()
    valid_json = json.dumps({"test": "data"})
    result = format_tool(content=valid_json)
    assert result.success
    assert result.data["is_valid"]

    # 测试难度检查
    diff_tool = CheckDifficultyTool()
    result = diff_tool(
        content="这是一个简单的概念题，考察基础定义。",
        declared_difficulty="easy"
    )
    assert result.success

    # 测试答案验证
    answer_tool = ValidateAnswerTool()
    result = answer_tool(
        question_type="choice",
        answer="A",
        options='["A. 选项A", "B. 选项B", "C. 选项C", "D. 选项D"]'
    )
    assert result.success


# 测试 Agent 基类
def test_tool_calling_agent_base():
    """测试 Tool Calling Agent 基类"""
    from agents.base import ToolCallingAgent, AgentTrace, AgentDecision
    from agents.tools.base import BaseTool, ToolParameter, ToolResult

    class MockTool(BaseTool):
        def __init__(self):
            super().__init__()
            self._name = "mock_tool"
            self._description = "模拟工具"
            self._parameters = [
                ToolParameter(name="input", type="string",
                              description="输入", required=True)
            ]

        def execute(self, input: str) -> ToolResult:
            return ToolResult(success=True, data={"result": f"processed: {input}"})

    class TestAgent(ToolCallingAgent):
        @property
        def name(self) -> str:
            return "test_agent"

        @property
        def system_prompt(self) -> str:
            return "你是一个测试 Agent"

    # 创建 Agent（不实际调用 LLM）
    agent = TestAgent(tools=[MockTool()])

    # 测试工具注册
    assert "mock_tool" in agent.list_tools()

    # 测试工具执行
    result = agent._execute_tool("mock_tool", {"input": "test"})
    assert result.success
    assert "processed: test" in result.data["result"]


# 测试 Agent Trace
def test_agent_trace():
    """测试 Agent 执行追踪"""
    from agents.base import AgentTrace, AgentDecision

    trace = AgentTrace(agent_name="test")

    # 添加决策
    decision = AgentDecision(
        thought="需要调用工具",
        action="mock_tool",
        action_input={"input": "test"},
        observation="工具执行成功"
    )
    trace.add_decision(decision)

    # 测试序列化
    trace_dict = trace.to_dict()
    assert trace_dict["agent_name"] == "test"
    assert len(trace_dict["decisions"]) == 1


# 集成测试：Router Agent V2
def test_router_agent_v2_structure():
    """测试 Router Agent V2 结构"""
    from agents.router_agent_v2 import RouterAgentV2, ClassifyIntentTool, ExtractEntitiesTool

    # 测试工具
    classify_tool = ClassifyIntentTool()
    assert classify_tool.name == "classify_intent"

    extract_tool = ExtractEntitiesTool()
    assert extract_tool.name == "extract_entities"

    # 测试 Agent 结构（不调用 LLM）
    agent = RouterAgentV2.__new__(RouterAgentV2)
    agent._tools = {
        "classify_intent": classify_tool,
        "extract_entities": extract_tool
    }

    assert agent.name == "router"
    assert "classify_intent" in agent.list_tools()


# 集成测试：Planner Agent V2
def test_planner_agent_v2_structure():
    """测试 Planner Agent V2 结构"""
    from agents.planner_agent_v2 import PlannerAgentV2, DecomposeTaskTool, EstimateComplexityTool

    # 测试工具
    decompose_tool = DecomposeTaskTool()
    assert decompose_tool.name == "decompose_task"

    estimate_tool = EstimateComplexityTool()
    assert estimate_tool.name == "estimate_complexity"


# 集成测试：Creator Agent V2
def test_creator_agent_v2_structure():
    """测试 Creator Agent V2 结构"""
    from agents.creator_agent_v2 import CreatorAgentV2, CreateQuestionTool

    # 测试工具
    create_tool = CreateQuestionTool()
    assert create_tool.name == "create_question"

    # 测试试题创建
    result = create_tool(
        content="1+1=?",
        question_type="choice",
        options='["A. 1", "B. 2", "C. 3", "D. 4"]',
        answer="B",
        explanation="1+1=2"
    )
    assert result.success
    assert result.data["content"] == "1+1=?"


# 集成测试：Consolidator Agent V2
def test_consolidator_agent_v2_structure():
    """测试 Consolidator Agent V2 结构"""
    from agents.consolidator_agent_v2 import ConsolidatorAgentV2, SummarizeExperienceTool

    # 测试工具
    summarize_tool = SummarizeExperienceTool()
    assert summarize_tool.name == "summarize_experience"

    # 测试经验总结
    result = summarize_tool(
        experience_type="task_experience",
        content="成功生成代数选择题",
        keywords="代数,选择题"
    )
    assert result.success


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
