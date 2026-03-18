"""
Agent 基类模块

提供支持 Tool Calling 的 Agent 基类。
"""

from abc import ABC, abstractmethod
from typing import List, Optional, Dict, Any, Callable, Awaitable
from dataclasses import dataclass, field
from datetime import datetime
import json

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import SystemMessage, HumanMessage, AIMessage, ToolMessage
from langchain_core.tools import BaseTool as LangChainTool

from agents.tools.base import BaseTool, ToolResult, registry


@dataclass
class AgentDecision:
    """Agent 决策记录"""
    thought: str  # 思考过程
    action: str  # 选择的动作/工具
    action_input: Dict[str, Any]  # 动作输入
    observation: str  # 观察结果
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())


@dataclass
class AgentTrace:
    """Agent 执行追踪"""
    agent_name: str
    decisions: List[AgentDecision] = field(default_factory=list)
    final_result: Optional[str] = None
    success: bool = True
    error: Optional[str] = None
    start_time: str = field(default_factory=lambda: datetime.now().isoformat())
    end_time: Optional[str] = None

    def add_decision(self, decision: AgentDecision):
        """添加决策记录"""
        self.decisions.append(decision)

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "agent_name": self.agent_name,
            "decisions": [
                {
                    "thought": d.thought,
                    "action": d.action,
                    "action_input": d.action_input,
                    "observation": d.observation,
                    "timestamp": d.timestamp
                }
                for d in self.decisions
            ],
            "final_result": self.final_result,
            "success": self.success,
            "error": self.error,
            "start_time": self.start_time,
            "end_time": self.end_time
        }


class ToolCallingAgent(ABC):
    """
    支持 Tool Calling 的 Agent 基类

    提供：
    - 工具绑定与执行
    - 多轮工具调用
    - 决策追踪
    - 错误处理与重试
    """

    def __init__(
        self,
        llm: Optional[BaseChatModel] = None,
        tools: Optional[List[BaseTool]] = None,
        max_iterations: int = 5,
        verbose: bool = False
    ):
        """
        初始化 Agent

        Args:
            llm: 语言模型实例
            tools: 可用工具列表
            max_iterations: 最大迭代次数
            verbose: 是否打印详细日志
        """
        self.llm = llm
        self._tools: Dict[str, BaseTool] = {}
        self._langchain_tools: List[LangChainTool] = []
        self.max_iterations = max_iterations
        self.verbose = verbose
        self._trace: Optional[AgentTrace] = None

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
        self._langchain_tools.append(tool.to_langchain_tool())

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

    def get_openai_tools(self) -> List[Dict[str, Any]]:
        """获取 OpenAI 格式的工具定义"""
        return [tool.to_openai_function() for tool in self._tools.values()]

    def _execute_tool(self, tool_name: str, tool_args: Dict[str, Any]) -> ToolResult:
        """
        执行工具

        Args:
            tool_name: 工具名称
            tool_args: 工具参数

        Returns:
            执行结果
        """
        tool = self._tools.get(tool_name)
        if not tool:
            return ToolResult(
                success=False,
                data=None,
                error=f"未找到工具: {tool_name}"
            )

        return tool(**tool_args)

    def _build_messages(
        self,
        user_input: str,
        context: Optional[Dict[str, Any]] = None
    ) -> List:
        """
        构建消息列表

        Args:
            user_input: 用户输入
            context: 额外上下文

        Returns:
            消息列表
        """
        messages = [SystemMessage(content=self.system_prompt)]

        # 添加上下文
        if context:
            context_str = "\n".join(
                f"{k}: {v}" for k, v in context.items() if v)
            if context_str:
                messages.append(HumanMessage(content=f"上下文信息:\n{context_str}"))

        messages.append(HumanMessage(content=user_input))

        return messages

    def run_with_tools(
        self,
        user_input: str,
        context: Optional[Dict[str, Any]] = None
    ) -> AgentTrace:
        """
        使用工具运行 Agent

        Args:
            user_input: 用户输入
            context: 额外上下文

        Returns:
            执行追踪
        """
        # 初始化追踪
        self._trace = AgentTrace(agent_name=self.name)

        try:
            # 构建初始消息
            messages = self._build_messages(user_input, context)

            # 绑定工具到 LLM
            llm_with_tools = self.llm.bind_tools(self._langchain_tools)

            # 迭代执行
            for iteration in range(self.max_iterations):
                # 调用 LLM
                response = llm_with_tools.invoke(messages)

                # 检查是否有工具调用
                if not response.tool_calls:
                    # 没有工具调用，返回最终结果
                    self._trace.final_result = response.content
                    self._trace.success = True
                    break

                # 处理工具调用
                messages.append(response)

                for tool_call in response.tool_calls:
                    tool_name = tool_call["name"]
                    tool_args = tool_call["args"]

                    # 执行工具
                    result = self._execute_tool(tool_name, tool_args)
                    observation = str(result)

                    # 记录决策
                    decision = AgentDecision(
                        thought=response.content or "",
                        action=tool_name,
                        action_input=tool_args,
                        observation=observation
                    )
                    self._trace.add_decision(decision)

                    if self.verbose:
                        print(f"[{self.name}] Tool: {tool_name}")
                        print(f"[{self.name}] Args: {tool_args}")
                        print(f"[{self.name}] Result: {observation[:200]}...")

                    # 添加工具消息
                    messages.append(ToolMessage(
                        content=observation,
                        tool_call_id=tool_call["id"]
                    ))

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

    async def arun_with_tools(
        self,
        user_input: str,
        context: Optional[Dict[str, Any]] = None
    ) -> AgentTrace:
        """
        异步运行 Agent（使用工具）

        Args:
            user_input: 用户输入
            context: 额外上下文

        Returns:
            执行追踪
        """
        # 初始化追踪
        self._trace = AgentTrace(agent_name=self.name)

        try:
            # 构建初始消息
            messages = self._build_messages(user_input, context)

            # 绑定工具到 LLM
            llm_with_tools = self.llm.bind_tools(self._langchain_tools)

            # 迭代执行
            for iteration in range(self.max_iterations):
                # 异步调用 LLM
                response = await llm_with_tools.ainvoke(messages)

                # 检查是否有工具调用
                if not response.tool_calls:
                    # 没有工具调用，返回最终结果
                    self._trace.final_result = response.content
                    self._trace.success = True
                    break

                # 处理工具调用
                messages.append(response)

                for tool_call in response.tool_calls:
                    tool_name = tool_call["name"]
                    tool_args = tool_call["args"]

                    # 执行工具
                    result = self._execute_tool(tool_name, tool_args)
                    observation = str(result)

                    # 记录决策
                    decision = AgentDecision(
                        thought=response.content or "",
                        action=tool_name,
                        action_input=tool_args,
                        observation=observation
                    )
                    self._trace.add_decision(decision)

                    if self.verbose:
                        print(f"[{self.name}] Tool: {tool_name}")
                        print(f"[{self.name}] Args: {tool_args}")
                        print(f"[{self.name}] Result: {observation[:200]}...")

                    # 添加工具消息
                    messages.append(ToolMessage(
                        content=observation,
                        tool_call_id=tool_call["id"]
                    ))

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

    def get_trace(self) -> Optional[AgentTrace]:
        """获取最近一次执行的追踪"""
        return self._trace


class SimpleAgent(ABC):
    """
    简单 Agent 基类

    不使用 Tool Calling，仅通过 Prompt 驱动。
    适用于简单的分类、生成任务。
    """

    def __init__(self, llm: Optional[BaseChatModel] = None):
        """
        初始化 Agent

        Args:
            llm: 语言模型实例
        """
        self.llm = llm

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

    def run(self, user_input: str, context: Optional[Dict[str, Any]] = None) -> str:
        """
        运行 Agent

        Args:
            user_input: 用户输入
            context: 额外上下文

        Returns:
            Agent 响应
        """
        messages = [SystemMessage(content=self.system_prompt)]

        if context:
            context_str = "\n".join(
                f"{k}: {v}" for k, v in context.items() if v)
            if context_str:
                messages.append(HumanMessage(content=f"上下文信息:\n{context_str}"))

        messages.append(HumanMessage(content=user_input))

        response = self.llm.invoke(messages)
        return response.content

    async def arun(self, user_input: str, context: Optional[Dict[str, Any]] = None) -> str:
        """
        异步运行 Agent

        Args:
            user_input: 用户输入
            context: 额外上下文

        Returns:
            Agent 响应
        """
        messages = [SystemMessage(content=self.system_prompt)]

        if context:
            context_str = "\n".join(
                f"{k}: {v}" for k, v in context.items() if v)
            if context_str:
                messages.append(HumanMessage(content=f"上下文信息:\n{context_str}"))

        messages.append(HumanMessage(content=user_input))

        response = await self.llm.ainvoke(messages)
        return response.content
