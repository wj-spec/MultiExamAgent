"""
UI 工具封装 (utils/ui_utils.py)

提供 Agent 节点中使用的步骤名称常量和状态消息模板。
原 Chainlit 版本已迁移到 FastAPI + WebSocket 自定义前端，
本模块保留纯文字常量部分供 workflow_server.py 使用。
"""

from typing import Optional, Dict, Any, List


# ---------- 辅助函数（不依赖任何 UI 框架）----------

def format_memory_summary(memories: List[Dict]) -> str:
    """格式化记忆内容用于展示"""
    if not memories:
        return "🈚 未检索到历史偏好，作为新用户处理。"
    result = f"✅ 检索到 {len(memories)} 条历史偏好：\n"
    for i, mem in enumerate(memories[:3], 1):
        mem_type = mem.get("type", "unknown")
        content = mem.get("content", "")[:50]
        result += f"  {i}. [{mem_type}] {content}...\n"
    return result


def format_audit_result(passed: bool, feedback: str, revision_count: int = 0) -> str:
    """格式化审核结果"""
    if passed:
        return "✅ 审核通过！试题符合标准。\n"
    return f"⚠️ 审核发现问题: {feedback}\n🔄 准备第 {revision_count + 1} 次修正...\n"


def format_plan_steps(steps: List[str]) -> str:
    """格式化执行计划"""
    result = "📋 执行计划：\n"
    for i, step in enumerate(steps, 1):
        result += f"  {i}. {step}\n"
    return result


# 兼容旧接口（异步版本直接转发）
async def show_memory_card(memories: List[Dict]) -> str:
    return format_memory_summary(memories)


async def show_audit_result(passed: bool, feedback: str, revision_count: int = 0) -> str:
    return format_audit_result(passed, feedback, revision_count)


async def show_plan_steps(steps: List[str]) -> str:
    return format_plan_steps(steps)


# ================================================================
# 步骤名称常量（被 workflow_server.py 导入使用）
# ================================================================

class StepNames:
    """Step 名称常量"""
    ROUTER       = "🤔 正在思考"
    MEMORY       = "💡 记忆认知"
    PLANNER      = "📋 任务规划"
    KNOWLEDGE    = "🔍 知识检索"
    CREATOR      = "✍️ 试题生成"
    AUDITOR      = "🧐 质量审核"
    CONSOLIDATOR = "💾 经验沉淀"
    CHAT         = "💬 对话回复"


# ================================================================
# 状态消息模板
# ================================================================

class StatusMessages:
    """状态消息模板（纯文字，用于 WebSocket 步骤回调）"""

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
