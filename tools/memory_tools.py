"""
长期记忆读写工具

提供 Agent 可调用的记忆检索和存储工具。
这些工具被封装为 LangChain Tool 格式，可以在 Agent 执行过程中调用。
"""

from typing import Optional, Type
from pydantic import BaseModel, Field
from langchain_core.tools import BaseTool

from utils.memory_manager import get_memory_manager


class RetrieveMemoryInput(BaseModel):
    """记忆检索工具的输入参数"""
    query: str = Field(description="检索查询字符串，可以是关键词或描述性语句")
    top_k: int = Field(default=5, description="返回的最大记忆数量")
    memory_type: Optional[str] = Field(
        default=None,
        description="记忆类型过滤：user_preference(用户偏好), task_experience(任务经验), feedback(反馈)"
    )


class SaveMemoryInput(BaseModel):
    """记忆保存工具的输入参数"""
    content: str = Field(description="要保存的记忆内容")
    memory_type: str = Field(
        default="task_experience",
        description="记忆类型：user_preference(用户偏好), task_experience(任务经验), feedback(反馈)"
    )
    metadata: Optional[dict] = Field(
        default=None,
        description="可选的元数据，如评分、来源等"
    )


class RetrieveMemoryTool(BaseTool):
    """记忆检索工具"""

    name: str = "retrieve_memory"
    description: str = (
        "从长期记忆库中检索相关的历史记忆。"
        "可以检索用户偏好、任务经验和反馈等信息。"
        "当需要了解用户历史偏好或类似任务的经验时使用此工具。"
    )
    args_schema: Type[BaseModel] = RetrieveMemoryInput

    def _run(
        self,
        query: str,
        top_k: int = 5,
        memory_type: Optional[str] = None
    ) -> str:
        """执行记忆检索"""
        manager = get_memory_manager()
        memories = manager.retrieve_memory(query, top_k, memory_type)

        if not memories:
            return "未找到相关记忆。"

        result = "找到以下相关记忆：\n\n"
        for i, mem in enumerate(memories, 1):
            result += f"【记忆 {i}】\n"
            result += f"类型: {mem.get('type', 'unknown')}\n"
            result += f"时间: {mem.get('timestamp', 'unknown')}\n"
            result += f"内容: {mem.get('content', '')}\n"
            if mem.get('metadata'):
                result += f"元数据: {mem.get('metadata')}\n"
            result += "\n"

        return result


class SaveMemoryTool(BaseTool):
    """记忆保存工具"""

    name: str = "save_memory"
    description: str = (
        "将新的记忆保存到长期记忆库。"
        "用于记录用户偏好、成功的任务经验或用户反馈。"
        "当完成任务后需要总结经验或发现新的用户偏好时使用此工具。"
    )
    args_schema: Type[BaseModel] = SaveMemoryInput

    def _run(
        self,
        content: str,
        memory_type: str = "task_experience",
        metadata: Optional[dict] = None
    ) -> str:
        """执行记忆保存"""
        manager = get_memory_manager()
        memory = manager.save_memory(content, memory_type, metadata)

        return f"已成功保存记忆，ID: {memory['id']}"


class GetUserPreferencesTool(BaseTool):
    """获取用户偏好工具"""

    name: str = "get_user_preferences"
    description: str = (
        "获取用户的偏好设置摘要。"
        "返回用户在历史对话中表现出的偏好，如难度偏好、题型偏好等。"
        "当需要快速了解用户偏好时使用此工具。"
    )

    def _run(self) -> str:
        """获取用户偏好"""
        manager = get_memory_manager()
        preferences = manager.get_user_preferences()

        if not preferences:
            return "暂未发现用户偏好记录。"

        result = "用户偏好摘要：\n"
        for key, value in preferences.items():
            result += f"- {key}: {value}\n"

        return result


class GetMemoryStatsTool(BaseTool):
    """获取记忆统计工具"""

    name: str = "get_memory_stats"
    description: str = (
        "获取长期记忆库的统计信息。"
        "返回记忆总数、各类型记忆数量等信息。"
        "当需要了解记忆库状态时使用此工具。"
    )

    def _run(self) -> str:
        """获取记忆统计"""
        manager = get_memory_manager()
        stats = manager.get_statistics()

        result = "长期记忆库统计：\n"
        result += f"- 总记忆数: {stats['total_count']}\n"
        result += f"- 类型分布: {stats['type_counts']}\n"

        return result


def get_memory_tools() -> list:
    """
    获取所有记忆相关工具

    Returns:
        记忆工具列表
    """
    return [
        RetrieveMemoryTool(),
        SaveMemoryTool(),
        GetUserPreferencesTool(),
        GetMemoryStatsTool()
    ]


# 便捷函数（供 Agent 直接调用，不通过 Tool 机制）
def retrieve_memory(query: str, top_k: int = 5, memory_type: str = None) -> list:
    """
    便捷函数：检索记忆

    Args:
        query: 查询字符串
        top_k: 返回数量
        memory_type: 类型过滤

    Returns:
        记忆列表
    """
    manager = get_memory_manager()
    return manager.retrieve_memory(query, top_k, memory_type)


def save_memory(content: str, memory_type: str = "task_experience", metadata: dict = None) -> dict:
    """
    便捷函数：保存记忆

    Args:
        content: 记忆内容
        memory_type: 记忆类型
        metadata: 元数据

    Returns:
        保存的记忆项
    """
    manager = get_memory_manager()
    return manager.save_memory(content, memory_type, metadata)


def get_user_preferences() -> dict:
    """
    便捷函数：获取用户偏好

    Returns:
        用户偏好字典
    """
    manager = get_memory_manager()
    return manager.get_user_preferences()
