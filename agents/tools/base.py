"""
工具基类与注册中心

定义 Agent 工具的统一接口和注册机制。
"""

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional, Callable, Type
from dataclasses import dataclass, field
import json


@dataclass
class ToolParameter:
    """工具参数定义"""
    name: str
    type: str  # "string", "integer", "number", "boolean", "array", "object"
    description: str
    required: bool = True
    enum: Optional[List[str]] = None
    default: Optional[Any] = None


@dataclass
class ToolResult:
    """工具执行结果"""
    success: bool
    data: Any
    error: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "success": self.success,
            "data": self.data,
            "error": self.error,
            "metadata": self.metadata
        }

    def __str__(self) -> str:
        if self.success:
            return json.dumps(self.data, ensure_ascii=False, indent=2)
        else:
            return f"Error: {self.error}"


class BaseTool(ABC):
    """
    工具基类

    所有 Agent 工具都应继承此类，实现统一的接口。
    支持转换为 LangChain Tool 和 OpenAI Function Calling 格式。
    """

    def __init__(self):
        self._name: str = self.__class__.__name__.replace("Tool", "").lower()
        self._description: str = ""
        self._parameters: List[ToolParameter] = []

    @property
    def name(self) -> str:
        """工具名称"""
        return self._name

    @property
    def description(self) -> str:
        """工具描述"""
        return self._description

    @property
    def parameters(self) -> List[ToolParameter]:
        """工具参数列表"""
        return self._parameters

    @abstractmethod
    def execute(self, **kwargs) -> ToolResult:
        """
        执行工具逻辑

        Args:
            **kwargs: 工具参数

        Returns:
            执行结果
        """
        pass

    def validate_parameters(self, **kwargs) -> Optional[str]:
        """
        验证参数

        Args:
            **kwargs: 输入参数

        Returns:
            错误信息，None 表示验证通过
        """
        for param in self._parameters:
            if param.required and param.name not in kwargs:
                return f"缺少必需参数: {param.name}"

            if param.name in kwargs:
                value = kwargs[param.name]
                # 类型检查
                if param.type == "integer" and not isinstance(value, int):
                    try:
                        kwargs[param.name] = int(value)
                    except (ValueError, TypeError):
                        return f"参数 {param.name} 应为整数"
                elif param.type == "number" and not isinstance(value, (int, float)):
                    try:
                        kwargs[param.name] = float(value)
                    except (ValueError, TypeError):
                        return f"参数 {param.name} 应为数字"

                # 枚举检查
                if param.enum and value not in param.enum:
                    return f"参数 {param.name} 的值应为: {param.enum}"

        return None

    def __call__(self, **kwargs) -> ToolResult:
        """
        调用工具

        Args:
            **kwargs: 工具参数

        Returns:
            执行结果
        """
        # 验证参数
        error = self.validate_parameters(**kwargs)
        if error:
            return ToolResult(success=False, data=None, error=error)

        # 执行
        try:
            return self.execute(**kwargs)
        except Exception as e:
            return ToolResult(success=False, data=None, error=str(e))

    def to_openai_function(self) -> Dict[str, Any]:
        """
        转换为 OpenAI Function Calling 格式

        Returns:
            OpenAI function 定义
        """
        properties = {}
        required = []

        for param in self._parameters:
            prop = {
                "type": param.type,
                "description": param.description
            }
            if param.enum:
                prop["enum"] = param.enum
            if param.default is not None:
                prop["default"] = param.default

            properties[param.name] = prop
            if param.required:
                required.append(param.name)

        return {
            "type": "function",
            "function": {
                "name": self._name,
                "description": self._description,
                "parameters": {
                    "type": "object",
                    "properties": properties,
                    "required": required
                }
            }
        }

    def to_langchain_tool(self):
        """
        转换为 LangChain Tool

        Returns:
            LangChain StructuredTool
        """
        from langchain_core.tools import StructuredTool
        from pydantic import BaseModel, create_model
        from typing import Optional as Opt

        # 动态创建 Pydantic 模型
        field_definitions = {}
        for param in self._parameters:
            # 类型映射
            type_map = {
                "string": str,
                "integer": int,
                "number": float,
                "boolean": bool,
                "array": list,
                "object": dict
            }
            py_type = type_map.get(param.type, str)

            if param.required:
                field_definitions[param.name] = (py_type, ...)
            else:
                field_definitions[param.name] = (Opt[py_type], param.default)

        ArgsModel = create_model(
            f"{self._name}_args",
            **field_definitions
        )

        def _run(**kwargs):
            result = self(**kwargs)
            return str(result)

        return StructuredTool(
            name=self._name,
            description=self._description,
            func=_run,
            args_schema=ArgsModel
        )


class ToolRegistry:
    """
    工具注册中心

    管理所有可用工具，支持按需获取和批量导出。
    """

    _instance: Optional["ToolRegistry"] = None
    _tools: Dict[str, BaseTool] = {}

    def __new__(cls) -> "ToolRegistry":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def register(self, tool: BaseTool) -> None:
        """注册工具"""
        self._tools[tool.name] = tool

    def unregister(self, name: str) -> None:
        """注销工具"""
        self._tools.pop(name, None)

    def get(self, name: str) -> Optional[BaseTool]:
        """获取工具"""
        return self._tools.get(name)

    def list_tools(self) -> List[str]:
        """列出所有工具名称"""
        return list(self._tools.keys())

    def get_tools(self, names: List[str] = None) -> List[BaseTool]:
        """
        获取工具列表

        Args:
            names: 工具名称列表，None 表示获取全部

        Returns:
            工具列表
        """
        if names is None:
            return list(self._tools.values())
        return [self._tools[name] for name in names if name in self._tools]

    def to_openai_functions(self, names: List[str] = None) -> List[Dict[str, Any]]:
        """
        导出为 OpenAI Functions 格式

        Args:
            names: 工具名称列表

        Returns:
            OpenAI functions 列表
        """
        tools = self.get_tools(names)
        return [tool.to_openai_function() for tool in tools]

    def to_langchain_tools(self, names: List[str] = None) -> List:
        """
        导出为 LangChain Tools 格式

        Args:
            names: 工具名称列表

        Returns:
            LangChain tools 列表
        """
        tools = self.get_tools(names)
        return [tool.to_langchain_tool() for tool in tools]


# 全局注册中心实例
registry = ToolRegistry()


def register_tool(tool_class: Type[BaseTool]) -> Type[BaseTool]:
    """
    工具注册装饰器

    使用方式:
        @register_tool
        class MyTool(BaseTool):
            ...
    """
    tool = tool_class()
    registry.register(tool)
    return tool_class
