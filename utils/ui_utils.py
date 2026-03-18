"""
Chainlit UI 工具封装

封装常用的 Chainlit UI 组件，便于在 Agent 节点中使用。
"""

import chainlit as cl
from typing import Optional, List, Dict, Any


async def create_step(name: str, step_type: str = "run") -> cl.Step:
    """
    创建一个 Chainlit Step 上下文管理器

    Args:
        name: Step 名称（会显示在 UI 上）
        step_type: Step 类型

    Returns:
        Chainlit Step 对象
    """
    return cl.Step(name=name, type=step_type)


async def stream_token(step: cl.Step, token: str):
    """
    向 Step 流式输出文本

    Args:
        step: Chainlit Step 对象
        token: 要输出的文本
    """
    await step.stream_token(token)


async def stream_tokens(step: cl.Step, tokens: List[str]):
    """
    批量流式输出文本

    Args:
        step: Chainlit Step 对象
        tokens: 文本列表
    """
    for token in tokens:
        await step.stream_token(token)


def set_step_error(step: cl.Step, is_error: bool = True):
    """
    设置 Step 为错误状态（会标红显示）

    Args:
        step: Chainlit Step 对象
        is_error: 是否为错误
    """
    step.is_error = is_error


async def show_memory_card(memories: List[Dict]) -> str:
    """
    格式化记忆内容用于展示

    Args:
        memories: 记忆列表

    Returns:
        格式化的记忆字符串
    """
    if not memories:
        return "🈚 未检索到历史偏好，作为新用户处理。"

    result = f"✅ 检索到 {len(memories)} 条历史偏好：\n"
    for i, mem in enumerate(memories[:3], 1):
        mem_type = mem.get("type", "unknown")
        content = mem.get("content", "")[:50]
        result += f"  {i}. [{mem_type}] {content}...\n"
    return result


async def show_audit_result(passed: bool, feedback: str, revision_count: int = 0) -> str:
    """
    格式化审核结果

    Args:
        passed: 是否通过
        feedback: 审核反馈
        revision_count: 当前修订次数

    Returns:
        格式化的审核结果字符串
    """
    if passed:
        return f"✅ 审核通过！试题符合标准。\n"
    else:
        return f"⚠️ 审核发现问题: {feedback}\n🔄 准备第 {revision_count + 1} 次修正...\n"


async def show_plan_steps(steps: List[str]) -> str:
    """
    格式化执行计划

    Args:
        steps: 计划步骤列表

    Returns:
        格式化的计划字符串
    """
    result = "📋 执行计划：\n"
    for i, step in enumerate(steps, 1):
        result += f"  {i}. {step}\n"
    return result


class StepContext:
    """
    Step 上下文管理器封装类

    用于简化 async with 语法
    """

    def __init__(self, name: str, step_type: str = "run"):
        self.name = name
        self.step_type = step_type
        self.step: Optional[cl.Step] = None

    async def __aenter__(self):
        self.step = cl.Step(name=self.name, type=self.step_type)
        await self.step.__aenter__()
        return self.step

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.step:
            await self.step.__aexit__(exc_type, exc_val, exc_tb)


def make_step(name: str, step_type: str = "run") -> StepContext:
    """
    创建 Step 上下文管理器

    用法:
        async with make_step("💡 记忆认知") as step:
            await step.stream_token("正在处理...")

    Args:
        name: Step 名称
        step_type: Step 类型

    Returns:
        StepContext 对象
    """
    return StepContext(name, step_type)


# 常用的 Step 名称常量
class StepNames:
    """Step 名称常量"""
    ROUTER = "🤔 正在思考"
    MEMORY = "💡 记忆认知"
    PLANNER = "📋 任务规划"
    KNOWLEDGE = "🔍 知识检索"
    CREATOR = "✍️ 试题生成"
    AUDITOR = "🧐 质量审核"
    CONSOLIDATOR = "💾 经验沉淀"
    CHAT = "💬 对话回复"


# 状态消息模板
class StatusMessages:
    """状态消息模板"""

    @staticmethod
    def router_proposition():
        return "识别为命题任务，正在转交专家组..."

    @staticmethod
    def router_grading():
        return "识别为阅卷任务，正在准备批改..."

    @staticmethod
    def router_chat():
        return "识别为普通对话，正在生成回复..."

    @staticmethod
    def memory_search(query: str):
        return f"🔍 正在检索与 '{query}' 相关的历史记忆...\n"

    @staticmethod
    def memory_found(count: int):
        return f"✅ 检索到 {count} 条相关记忆\n"

    @staticmethod
    def memory_not_found():
        return "🈚 未检索到历史偏好，作为新用户处理\n"

    @staticmethod
    def memory_analyzing():
        return "🧠 正在结合上下文分析需求完整性...\n"

    @staticmethod
    def memory_complete(params: dict):
        return f"✅ 需求完整: 知识点={params.get('topic')}, 题型={params.get('question_type')}\n"

    @staticmethod
    def memory_incomplete(missing: list):
        return f"❓ 信息不完整，缺失: {', '.join(missing)}\n"

    @staticmethod
    def planner_created(steps: list):
        return f"📋 执行计划已制定: {' → '.join(steps[:4])}\n"

    @staticmethod
    def knowledge_searching(topic: str):
        return f"🔍 正在检索知识库: {topic}\n"

    @staticmethod
    def knowledge_found(count: int):
        return f"📚 检索到 {count} 条相关知识内容\n"

    @staticmethod
    def creator_generating(count: int):
        return f"✍️ 正在生成 {count} 道试题...\n"

    @staticmethod
    def creator_generated(count: int):
        return f"✅ 已生成 {count} 道试题\n"

    @staticmethod
    def auditor_checking(revision: int):
        return f"🧐 正在进行第 {revision + 1} 次质量审核...\n"

    @staticmethod
    def auditor_passed():
        return "✅ 审核通过！试题符合标准\n"

    @staticmethod
    def auditor_failed(feedback: str, revision: int, max_revision: int):
        return f"⚠️ 发现问题: {feedback}\n🔄 触发修正 ({revision}/{max_revision})\n"

    @staticmethod
    def consolidator_saving(count: int):
        return f"💾 正在保存 {count} 条经验到记忆库...\n"

    @staticmethod
    def consolidator_saved(count: int):
        return f"✅ 已保存 {count} 条新记忆\n"
