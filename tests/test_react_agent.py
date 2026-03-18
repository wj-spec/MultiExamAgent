"""
ReAct 循环单元测试

测试 ReAct Agent 的核心功能。
"""

import pytest
import json
from unittest.mock import Mock, patch, MagicMock

# ==================== ReAct 基类测试 ====================


def test_react_step():
    """测试 ReActStep 数据结构"""
    from agents.base.react_agent import ReActStep, ReActState

    step = ReActStep(
        step_number=1,
        thought="需要分析用户意图",
        action="classify_intent",
        action_input={"query": "出题"},
        observation="意图: proposition",
        state=ReActState.ACTION
    )

    # 测试序列化
    step_dict = step.to_dict()
    assert step_dict["step_number"] == 1
    assert step_dict["thought"] == "需要分析用户意图"
    assert step_dict["action"] == "classify_intent"
    assert step_dict["state"] == "action"


def test_react_trace():
    """测试 ReActTrace 数据结构"""
    from agents.base.react_agent import ReActTrace, ReActStep, ReActState

    trace = ReActTrace(
        agent_name="test_agent",
        task="测试任务"
    )

    # 添加步骤
    step1 = ReActStep(step_number=1, thought="思考1", state=ReActState.THOUGHT)
    step2 = ReActStep(step_number=2, action="test_action",
                      state=ReActState.ACTION)

    trace.add_step(step1)
    trace.add_step(step2)

    assert trace.step_count == 2

    # 测试序列化
    trace_dict = trace.to_dict()
    assert trace_dict["agent_name"] == "test_agent"
    assert trace_dict["step_count"] == 2
    assert len(trace_dict["steps"]) == 2


def test_react_state_enum():
    """测试 ReActState 枚举"""
    from agents.base.react_agent import ReActState

    assert ReActState.THOUGHT.value == "thought"
    assert ReActState.ACTION.value == "action"
    assert ReActState.OBSERVATION.value == "observation"
    assert ReActState.FINISH.value == "finish"


# ==================== ReAct Agent 响应解析测试 ====================

def test_parse_response_with_action():
    """测试解析包含 Action 的响应"""
    from agents.base.react_agent import ReActAgent, ReActState

    # 创建一个简单的测试 Agent
    class TestReActAgent(ReActAgent):
        @property
        def name(self) -> str:
            return "test"

        @property
        def system_prompt(self) -> str:
            return "test"

    agent = TestReActAgent()

    # 测试解析
    response = """Thought: 需要分析用户意图
Action: classify_intent
Action Input: {"intent": "proposition", "confidence": 0.9}"""

    state, result = agent._parse_response(response)

    assert state == ReActState.ACTION
    assert result["thought"] == "需要分析用户意图"
    assert result["action"] == "classify_intent"
    assert result["action_input"]["intent"] == "proposition"


def test_parse_response_with_final_answer():
    """测试解析包含 Final Answer 的响应"""
    from agents.base.react_agent import ReActAgent, ReActState

    class TestReActAgent(ReActAgent):
        @property
        def name(self) -> str:
            return "test"

        @property
        def system_prompt(self) -> str:
            return "test"

    agent = TestReActAgent()

    response = """Thought: 任务已完成
Final Answer: 意图是命题，知识点是代数"""

    state, result = agent._parse_response(response)

    assert state == ReActState.FINISH
    assert result["final_answer"] == "意图是命题，知识点是代数"


def test_parse_response_json_action_input():
    """测试解析 JSON 格式的 Action Input"""
    from agents.base.react_agent import ReActAgent, ReActState

    class TestReActAgent(ReActAgent):
        @property
        def name(self) -> str:
            return "test"

        @property
        def system_prompt(self) -> str:
            return "test"

    agent = TestReActAgent()

    response = """Thought: 提取实体
Action: extract_entities
Action Input: {"topic": "代数", "count": 5, "difficulty": "medium"}"""

    state, result = agent._parse_response(response)

    assert result["action_input"]["topic"] == "代数"
    assert result["action_input"]["count"] == 5
    assert result["action_input"]["difficulty"] == "medium"


# ==================== ReAct Router Agent 测试 ====================

def test_react_router_tools():
    """测试 ReAct Router 的工具"""
    from agents.react_router_agent import (
        ClassifyIntentTool,
        ExtractEntitiesTool,
        CheckCompletenessTool,
        GenerateFollowUpTool
    )

    # 测试意图分类工具
    classify_tool = ClassifyIntentTool()
    result = classify_tool(intent="proposition",
                           confidence=0.9, reason="用户要求出题")
    assert result.success
    assert result.data["intent"] == "proposition"

    # 测试实体提取工具
    extract_tool = ExtractEntitiesTool()
    result = extract_tool(topic="代数", question_type="choice", count=5)
    assert result.success
    assert result.data["topic"] == "代数"
    assert result.data["count"] == 5

    # 测试完整性检查工具
    check_tool = CheckCompletenessTool()
    result = check_tool(
        is_complete=False, missing_fields='["difficulty"]', suggested_question="请问难度？")
    assert result.success
    assert result.data["is_complete"] == False
    assert "difficulty" in result.data["missing_fields"]

    # 测试追问生成工具
    followup_tool = GenerateFollowUpTool()
    result = followup_tool(
        question="请问难度要求？", options='["简单", "中等", "困难"]', purpose="确定难度")
    assert result.success
    assert result.data["question"] == "请问难度要求？"
    assert len(result.data["options"]) == 3


def test_react_router_agent_structure():
    """测试 ReAct Router Agent 结构"""
    from agents.react_router_agent import ReActRouterAgent

    # 创建 Agent（不调用 LLM）
    agent = ReActRouterAgent.__new__(ReActRouterAgent)
    agent._tools = {}
    agent.max_iterations = 6
    agent.verbose = False

    # 测试属性
    assert agent.name == "react_router"
    assert "classify_intent" in agent.system_prompt


def test_react_router_tool_descriptions():
    """测试工具描述生成"""
    from agents.base.react_agent import ReActAgent
    from agents.react_router_agent import ClassifyIntentTool

    class TestAgent(ReActAgent):
        @property
        def name(self) -> str:
            return "test"

        @property
        def system_prompt(self) -> str:
            return "test"

    agent = TestAgent(tools=[ClassifyIntentTool()])
    descriptions = agent._get_tool_descriptions()

    assert "classify_intent" in descriptions
    assert "intent" in descriptions


# ==================== 历史记录构建测试 ====================

def test_build_history():
    """测试历史记录构建"""
    from agents.base.react_agent import ReActAgent, ReActStep, ReActState

    class TestAgent(ReActAgent):
        @property
        def name(self) -> str:
            return "test"

        @property
        def system_prompt(self) -> str:
            return "test"

    agent = TestAgent()

    steps = [
        ReActStep(step_number=1, thought="思考1", action="action1",
                  action_input={"a": 1}, observation="结果1"),
        ReActStep(step_number=2, thought="思考2", action="action2",
                  action_input={"b": 2}, observation="结果2")
    ]

    history = agent._build_history(steps)

    assert "Thought: 思考1" in history
    assert "Action: action1" in history
    assert "Observation: 结果1" in history
    assert "Thought: 思考2" in history


# ==================== 工具执行测试 ====================

def test_tool_execution():
    """测试工具执行"""
    from agents.base.react_agent import ReActAgent
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

    class TestAgent(ReActAgent):
        @property
        def name(self) -> str:
            return "test"

        @property
        def system_prompt(self) -> str:
            return "test"

    agent = TestAgent(tools=[MockTool()])

    # 测试工具执行
    result = agent._execute_tool("mock_tool", {"input": "test"})
    assert "processed: test" in result

    # 测试不存在的工具
    result = agent._execute_tool("nonexistent", {})
    assert "错误" in result


# ==================== 节点函数测试 ====================

def test_react_router_node_structure():
    """测试 ReAct Router 节点函数结构"""
    from agents.react_router_agent import react_router_node

    # 验证函数存在且可调用
    assert callable(react_router_node)


# ==================== 集成测试 ====================

def test_react_agent_full_flow_mock():
    """测试 ReAct Agent 完整流程（Mock LLM）"""
    from agents.base.react_agent import ReActAgent, ReActState
    from agents.tools.base import BaseTool, ToolParameter, ToolResult

    class TestTool(BaseTool):
        def __init__(self):
            super().__init__()
            self._name = "test_tool"
            self._description = "测试工具"
            self._parameters = [
                ToolParameter(name="value", type="string",
                              description="值", required=True)
            ]

        def execute(self, value: str) -> ToolResult:
            return ToolResult(success=True, data={"result": f"echo: {value}"})

    class TestReActAgent(ReActAgent):
        @property
        def name(self) -> str:
            return "test_react"

        @property
        def system_prompt(self) -> str:
            return "你是一个测试 Agent"

    # 创建 Agent
    agent = TestReActAgent(tools=[TestTool()])

    # 验证工具注册
    assert "test_tool" in agent.list_tools()

    # 验证工具执行
    result = agent._execute_tool("test_tool", {"value": "hello"})
    assert "echo: hello" in result


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
