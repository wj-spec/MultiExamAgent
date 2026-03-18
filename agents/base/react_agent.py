"""
ReAct Agent 基类

实现完整的 Thought-Action-Observation 推理循环。
ReAct = Reasoning + Acting
"""

import re
import json
from abc import abstractmethod
from typing import List, Optional, Dict, Any, Tuple
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import SystemMessage, HumanMessage, AIMessage

from agents.tools.base import BaseTool, ToolResult, registry


class ReActState(Enum):
    """ReAct 状态"""
    THOUGHT = "thought"
    ACTION = "action"
    OBSERVATION = "observation"
    FINISH = "finish"


@dataclass
class ReActStep:
    """ReAct 单步执行记录"""
    step_number: int
    thought: str = ""
    action: str = ""
    action_input: Dict[str, Any] = field(default_factory=dict)
    observation: str = ""
    state: ReActState = ReActState.THOUGHT
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())

    def to_dict(self) -> Dict[str, Any]:
        return {
            "step_number": self.step_number,
            "thought": self.thought,
            "action": self.action,
            "action_input": self.action_input,
            "observation": self.observation,
            "state": self.state.value,
            "timestamp": self.timestamp
        }


@dataclass
class ReActTrace:
    """ReAct 完整执行追踪"""
    agent_name: str
    task: str
    steps: List[ReActStep] = field(default_factory=list)
    final_answer: str = ""
    success: bool = True
    error: Optional[str] = None
    total_tokens: int = 0
    start_time: str = field(default_factory=lambda: datetime.now().isoformat())
    end_time: Optional[str] = None

    def add_step(self, step: ReActStep):
        self.steps.append(step)

    @property
    def step_count(self) -> int:
        return len(self.steps)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "agent_name": self.agent_name,
            "task": self.task,
            "steps": [s.to_dict() for s in self.steps],
            "final_answer": self.final_answer,
            "success": self.success,
            "error": self.error,
            "total_tokens": self.total_tokens,
            "start_time": self.start_time,
            "end_time": self.end_time,
            "step_count": self.step_count
        }


class ReActAgent:
    """
    ReAct Agent 基类

    实现完整的 Thought-Action-Observation 推理循环：
    1. Thought: LLM 思考下一步应该做什么
    2. Action: 决定执行什么工具
    3. Observation: 执行工具并观察结果
    4. 重复直到得出最终答案

    特点：
    - 显式的推理过程，可解释性强
    - 支持多步推理和工具链调用
    - 自动处理错误和重试
    """

    # ReAct 提示词模板
    REACT_PROMPT_TEMPLATE = """你是一个智能 Agent，使用 ReAct 模式进行推理和行动。

## ReAct 格式
每次响应请严格按照以下格式：

Thought: [你的思考过程，分析当前状态和下一步行动]
Action: [工具名称]
Action Input: [工具输入参数，JSON格式]

或者当任务完成时：

Thought: [最终思考]
Final Answer: [最终答案]

## 可用工具
{tool_descriptions}

## 当前任务
{task}

## 历史记录
{history}

请继续执行任务。"""

    def __init__(
        self,
        llm: Optional[BaseChatModel] = None,
        tools: Optional[List[BaseTool]] = None,
        max_iterations: int = 10,
        verbose: bool = False
    ):
        """
        初始化 ReAct Agent

        Args:
            llm: 语言模型实例
            tools: 可用工具列表
            max_iterations: 最大迭代次数
            verbose: 是否打印详细日志
        """
        self.llm = llm
        self._tools: Dict[str, BaseTool] = {}
        self.max_iterations = max_iterations
        self.verbose = verbose
        self._trace: Optional[ReActTrace] = None

        # 注册工具
        if tools:
            for tool in tools:
                self.register_tool(tool)

    @property
    @abstractmethod
    def name(self) -> str:
        """Agent 名称"""
        pass

    @property
    @abstractmethod
    def system_prompt(self) -> str:
        """系统提示词"""
        pass

    def register_tool(self, tool: BaseTool):
        """注册工具"""
        self._tools[tool.name] = tool

    def register_tools(self, tools: List[BaseTool]):
        """批量注册工具"""
        for tool in tools:
            self.register_tool(tool)

    def get_tool(self, name: str) -> Optional[BaseTool]:
        """获取工具"""
        return self._tools.get(name)

    def list_tools(self) -> List[str]:
        """列出所有工具名称"""
        return list(self._tools.keys())

    def _get_tool_descriptions(self) -> str:
        """获取工具描述"""
        descriptions = []
        for name, tool in self._tools.items():
            desc = f"- {name}: {tool.description}\n"
            desc += "  参数:\n"
            for param in tool.parameters:
                required = "必需" if param.required else "可选"
                desc += f"    - {param.name} ({param.type}, {required}): {param.description}\n"
            descriptions.append(desc)
        return "\n".join(descriptions)

    def _parse_response(self, response: str) -> Tuple[ReActState, Dict[str, Any]]:
        """
        解析 LLM 响应

        Args:
            response: LLM 响应文本

        Returns:
            (状态, 解析结果)
        """
        result = {
            "thought": "",
            "action": "",
            "action_input": {},
            "final_answer": ""
        }

        # 提取 Thought
        thought_match = re.search(
            r'Thought:\s*(.+?)(?=Action:|Final Answer:|$)', response, re.DOTALL)
        if thought_match:
            result["thought"] = thought_match.group(1).strip()

        # 检查是否是最终答案
        final_match = re.search(r'Final Answer:\s*(.+?)$', response, re.DOTALL)
        if final_match:
            result["final_answer"] = final_match.group(1).strip()
            return ReActState.FINISH, result

        # 提取 Action
        action_match = re.search(r'Action:\s*(\w+)', response)
        if action_match:
            result["action"] = action_match.group(1).strip()

        # 提取 Action Input
        input_match = re.search(
            r'Action Input:\s*(.+?)(?=Thought:|Action:|Final Answer:|$)', response, re.DOTALL)
        if input_match:
            input_str = input_match.group(1).strip()
            try:
                result["action_input"] = json.loads(input_str)
            except json.JSONDecodeError:
                # 尝试简单解析
                result["action_input"] = {"input": input_str}

        # 判断状态
        if result["action"]:
            return ReActState.ACTION, result
        elif result["thought"]:
            return ReActState.THOUGHT, result
        else:
            return ReActState.THOUGHT, result

    def _execute_tool(self, tool_name: str, tool_args: Dict[str, Any]) -> str:
        """
        执行工具

        Args:
            tool_name: 工具名称
            tool_args: 工具参数

        Returns:
            执行结果字符串
        """
        tool = self._tools.get(tool_name)
        if not tool:
            return f"错误: 未找到工具 '{tool_name}'。可用工具: {list(self._tools.keys())}"

        result = tool(**tool_args)
        return str(result)

    def _build_history(self, steps: List[ReActStep]) -> str:
        """构建历史记录"""
        history_parts = []
        for step in steps:
            if step.thought:
                history_parts.append(f"Thought: {step.thought}")
            if step.action:
                history_parts.append(f"Action: {step.action}")
                history_parts.append(
                    f"Action Input: {json.dumps(step.action_input, ensure_ascii=False)}")
            if step.observation:
                history_parts.append(f"Observation: {step.observation}")
        return "\n".join(history_parts)

    def run(self, task: str, context: Optional[Dict[str, Any]] = None) -> ReActTrace:
        """
        运行 ReAct 循环

        Args:
            task: 任务描述
            context: 额外上下文

        Returns:
            执行追踪
        """
        # 初始化追踪
        self._trace = ReActTrace(
            agent_name=self.name,
            task=task
        )

        try:
            steps: List[ReActStep] = []

            for iteration in range(self.max_iterations):
                # 构建提示
                prompt = self.REACT_PROMPT_TEMPLATE.format(
                    tool_descriptions=self._get_tool_descriptions(),
                    task=task,
                    history=self._build_history(steps) if steps else "无"
                )

                # 添加上下文
                if context:
                    context_str = "\n".join(
                        f"{k}: {v}" for k, v in context.items() if v)
                    prompt = f"上下文信息:\n{context_str}\n\n{prompt}"

                # 调用 LLM
                messages = [
                    SystemMessage(content=self.system_prompt),
                    HumanMessage(content=prompt)
                ]
                response = self.llm.invoke(messages)
                response_text = response.content

                if self.verbose:
                    print(f"\n--- Step {iteration + 1} ---")
                    print(response_text)

                # 解析响应
                state, parsed = self._parse_response(response_text)

                # 创建步骤记录
                step = ReActStep(
                    step_number=iteration + 1,
                    thought=parsed.get("thought", ""),
                    action=parsed.get("action", ""),
                    action_input=parsed.get("action_input", {}),
                    state=state
                )

                # 如果是最终答案
                if state == ReActState.FINISH:
                    step.observation = "任务完成"
                    self._trace.final_answer = parsed.get("final_answer", "")
                    self._trace.add_step(step)
                    break

                # 执行工具
                if step.action:
                    observation = self._execute_tool(
                        step.action, step.action_input)
                    step.observation = observation

                    if self.verbose:
                        print(f"\nObservation: {observation[:500]}...")

                self._trace.add_step(step)
                steps.append(step)

            else:
                # 达到最大迭代次数
                self._trace.success = False
                self._trace.error = f"达到最大迭代次数 {self.max_iterations}"

        except Exception as e:
            self._trace.success = False
            self._trace.error = str(e)

        finally:
            self._trace.end_time = datetime.now().isoformat()

        return self._trace

    async def arun(self, task: str, context: Optional[Dict[str, Any]] = None) -> ReActTrace:
        """
        异步运行 ReAct 循环

        Args:
            task: 任务描述
            context: 额外上下文

        Returns:
            执行追踪
        """
        # 初始化追踪
        self._trace = ReActTrace(
            agent_name=self.name,
            task=task
        )

        try:
            steps: List[ReActStep] = []

            for iteration in range(self.max_iterations):
                # 构建提示
                prompt = self.REACT_PROMPT_TEMPLATE.format(
                    tool_descriptions=self._get_tool_descriptions(),
                    task=task,
                    history=self._build_history(steps) if steps else "无"
                )

                if context:
                    context_str = "\n".join(
                        f"{k}: {v}" for k, v in context.items() if v)
                    prompt = f"上下文信息:\n{context_str}\n\n{prompt}"

                # 异步调用 LLM
                messages = [
                    SystemMessage(content=self.system_prompt),
                    HumanMessage(content=prompt)
                ]
                response = await self.llm.ainvoke(messages)
                response_text = response.content

                if self.verbose:
                    print(f"\n--- Step {iteration + 1} ---")
                    print(response_text)

                # 解析响应
                state, parsed = self._parse_response(response_text)

                # 创建步骤记录
                step = ReActStep(
                    step_number=iteration + 1,
                    thought=parsed.get("thought", ""),
                    action=parsed.get("action", ""),
                    action_input=parsed.get("action_input", {}),
                    state=state
                )

                # 如果是最终答案
                if state == ReActState.FINISH:
                    step.observation = "任务完成"
                    self._trace.final_answer = parsed.get("final_answer", "")
                    self._trace.add_step(step)
                    break

                # 执行工具
                if step.action:
                    observation = self._execute_tool(
                        step.action, step.action_input)
                    step.observation = observation

                    if self.verbose:
                        print(f"\nObservation: {observation[:500]}...")

                self._trace.add_step(step)
                steps.append(step)

            else:
                self._trace.success = False
                self._trace.error = f"达到最大迭代次数 {self.max_iterations}"

        except Exception as e:
            self._trace.success = False
            self._trace.error = str(e)

        finally:
            self._trace.end_time = datetime.now().isoformat()

        return self._trace

    def get_trace(self) -> Optional[ReActTrace]:
        """获取最近一次执行的追踪"""
        return self._trace

    def get_final_answer(self) -> str:
        """获取最终答案"""
        if self._trace:
            return self._trace.final_answer
        return ""


class SimpleReActAgent(ReActAgent):
    """
    简单 ReAct Agent

    用于快速创建特定任务的 ReAct Agent。
    """

    def __init__(
        self,
        name: str,
        system_prompt: str,
        llm: Optional[BaseChatModel] = None,
        tools: Optional[List[BaseTool]] = None,
        max_iterations: int = 10,
        verbose: bool = False
    ):
        self._name = name
        self._system_prompt = system_prompt
        super().__init__(llm, tools, max_iterations, verbose)

    @property
    def name(self) -> str:
        return self._name

    @property
    def system_prompt(self) -> str:
        return self._system_prompt
