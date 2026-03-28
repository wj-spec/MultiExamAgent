"""
基础对话 Agent - 处理非命题意图的用户输入

支持：
1. 通用问答
2. 互联网检索
3. 附件处理
4. 语音输入理解
"""

import re
import logging
from typing import Dict, Any, List, Optional
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import SystemMessage, HumanMessage, AIMessage

from agents.base import ToolCallingAgent, AgentTrace
from agents.tools.base import BaseTool
from utils.config import get_llm

logger = logging.getLogger(__name__)


CHAT_SYSTEM_PROMPT = """你是 IntelliExam 的智能对话助手，一个具备场景感知能力的 ReAct Agent。

## 你的能力
1. 回答各类问题，提供信息和帮助
2. 联网搜索最新信息
3. 分析用户上传的文档内容
4. 识别用户意图并引导切换到专业场景

## 场景识别与引导规则

当你判断用户有以下意图时，在回复末尾添加对应标记：

**命题/出题/生成试题意图**：
- 回复末尾添加：[SCENE_SWITCH:proposition]
- 示例内容："了解了，您需要命题服务。切换到「命题専业场景」后，思考 Planner 将自动为您规划完整任务清单。[SCENE_SWITCH:proposition]"

**审题/审卷/批改意图**：
- 回复末尾添加：[SCENE_SWITCH:review]
- 示例内容："您涉及审题需求。切换到「审题场景」后，上传试题或粘贴试卷内容， Planner 将制定全面的审核计划。[SCENE_SWITCH:review]"

**普通对话**（不加标记，正常回复）

## 工作原则
- 简洁友好，避免过度专业化
- 遇到不确定的信息，主动联网核实
- 引导场景切换时要自然自信，不要失给

## 回复格式
- 使用清晰的段落结构
- 重要信息使用加粗
- 列表使用序号或项目符号
"""


class ChatAgent(ToolCallingAgent):
    """
    基础对话 Agent

    处理通用对话需求，支持工具调用。
    """

    def __init__(
        self,
        llm: Optional[BaseChatModel] = None,
        extra_tools: list = None,
        enable_skills: bool = True,
        enable_mcp: bool = True,
    ):
        """
        初始化基础对话 Agent

        Args:
            llm: 语言模型实例
            extra_tools: 额外工具列表（由调用方提供）
            enable_skills: 是否启用 Skills 系统工具注入
            enable_mcp: 是否启用 MCP 工具注入
        """
        # 延迟导入工具，避免循环依赖
        from agents.tools.search_tools import SearchInternetTool, BrowseWebTool
        from agents.tools.attachment_tools import AnalyzeAttachmentTool
        from agents.tools.speech_tools import TextNormalizeTool
        from tools.retriever import KnowledgeSearchTool

        base_tools = [
            SearchInternetTool(),
            BrowseWebTool(),
            AnalyzeAttachmentTool(),
            TextNormalizeTool(),
            KnowledgeSearchTool(),
        ]

        # 合并额外工具
        all_tools = base_tools + (extra_tools or [])

        # 注入 Skills 工具
        if enable_skills:
            try:
                from skills.registry import get_skills_for_node
                skill_tools = get_skills_for_node("chat")
                all_tools.extend(skill_tools)
            except Exception:
                pass

        # 注入 MCP 工具
        if enable_mcp:
            try:
                from utils.mcp_client import get_mcp_tools_sync
                mcp_tools = get_mcp_tools_sync()
                all_tools.extend(mcp_tools)
            except Exception:
                pass

        super().__init__(
            llm=llm or get_llm(temperature=0.7),
            tools=all_tools,
            max_iterations=4,
            verbose=False
        )

    @property
    def name(self) -> str:
        return "chat"

    @property
    def system_prompt(self) -> str:
        return CHAT_SYSTEM_PROMPT

    def chat(
        self,
        user_input: str,
        chat_history: List[Dict] = None,
        attachments: List[Dict] = None,
        current_scene: str = "chat"
    ) -> Dict[str, Any]:
        """
        执行基础对话

        Args:
            user_input: 用户输入
            chat_history: 对话历史
            attachments: 附件列表 [{"filename": "", "content": "", "type": ""}]
            current_scene: 当前所在的场景名称

        Returns:
            {
                "response": str,
                "mode_switch": Optional[str],
                "used_tools": List[str]
            }
        """
        # 构建消息
        sys_prompt = self.system_prompt
        sys_prompt += f"\n\n【系统状态】当前用户已经处于「{current_scene}」场景。如果用户的意图正好符合当前场景（例如已经在命题场景下要求命题），请直接推进对话或安抚用户响应，**绝对不要**再输出 [SCENE_SWITCH] 标记，也**不要**在回复里建议继续切换场景。"
        messages = [SystemMessage(content=sys_prompt)]

        # 添加对话历史
        if chat_history:
            for msg in chat_history[-10:]:  # 最近10轮
                if msg.get("role") == "user":
                    messages.append(HumanMessage(
                        content=msg.get("content", "")))
                elif msg.get("role") == "assistant":
                    messages.append(AIMessage(content=msg.get("content", "")))

        # 添加附件上下文
        if attachments:
            attachment_context = self._build_attachment_context(attachments)
            full_input = f"[附件信息]\n{attachment_context}\n\n[用户问题]\n{user_input}"
        else:
            full_input = user_input

        messages.append(HumanMessage(content=full_input))

        # 执行对话（带工具调用）
        trace = self.run_with_tools(full_input)

        # 获取最终响应
        if trace.final_result:
            response = trace.final_result
        else:
            # 如果没有最终结果，直接调用 LLM
            response = self.llm.invoke(messages).content

        # 检测模式切换
        mode_switch = self._detect_mode_switch(response)

        # 清理模式切换标记
        if mode_switch:
            response = re.sub(r'\[MODE_SWITCH:\w+\]', '', response).strip()

        # 记录使用的工具
        used_tools = [d.action for d in trace.decisions if d.action]

        return {
            "response": response,
            "mode_switch": mode_switch,
            "used_tools": used_tools,
            "trace": trace.to_dict()
        }

    def _build_attachment_context(self, attachments: List[Dict]) -> str:
        """
        构建附件上下文

        Args:
            attachments: 附件列表

        Returns:
            附件上下文字符串
        """
        context_parts = []
        for i, att in enumerate(attachments, 1):
            context_parts.append(
                f"附件 {i}:\n"
                f"  文件名: {att.get('filename', 'unknown')}\n"
                f"  类型: {att.get('type', 'unknown')}\n"
                f"  内容摘要: {att.get('summary', att.get('content', '无')[:500])}"
            )
        return "\n\n".join(context_parts)

    def _detect_mode_switch(self, response: str) -> Optional[str]:
        """
        检测回复中的模式/场景切换标记
        支持旧版 [MODE_SWITCH:x] 和 v3.0 [SCENE_SWITCH:x]
        """
        # v3.0 场景标记（优先）
        m = re.search(r'\[SCENE_SWITCH:(proposition|review)\]', response)
        if m:
            return m.group(1)
        # 兼容旧版标记
        m2 = re.search(r'\[MODE_SWITCH:(\w+)\]', response)
        if m2:
            mode = m2.group(1)
            # 映射旧模式到新场景
            return {'proposition': 'proposition', 'grading': 'review', 'paper_generation': 'proposition'}.get(mode, mode)
        return None


def chat_node(state: Dict[str, Any]) -> Dict[str, Any]:
    """
    基础对话节点

    处理非命题意图的用户输入。

    Args:
        state: 当前状态

    Returns:
        更新后的状态
    """
    from graphs.state import AgentState, add_status_message

    new_state = add_status_message(state, "💬 正在生成回复...")

    # 创建 Chat Agent
    agent = ChatAgent()

    # 执行对话
    result = agent.chat(
        user_input=state["user_input"],
        chat_history=state.get("chat_history", []),
        attachments=state.get("attachments", []),
        current_scene=state.get("scene", "chat")
    )

    # 更新状态
    new_state = dict(new_state)
    new_state["final_response"] = result["response"]
    new_state["next_node"] = "end"
    new_state["should_continue"] = False

    # v3.0: 场景切换建议
    scene_hint = result.get("mode_switch")
    current_scene = state.get("scene", "chat")
    
    if scene_hint in ("proposition", "review") and scene_hint != current_scene:
        new_state["scene_switch_hint"] = scene_hint
        new_state = add_status_message(
            new_state,
            f"📍 建议切换至: {'命题' if scene_hint == 'proposition' else '审题'}场景"
        )

        # 兼容旧版字段
        new_state["mode_transition"] = "enter"
        new_state["proposition_needed"] = True
        new_state["primary_intent"] = scene_hint

    # 记录使用的工具
    if result.get("used_tools"):
        new_state = add_status_message(
            new_state,
            f"🔧 使用工具: {', '.join(result['used_tools'])}"
        )

    new_state = add_status_message(new_state, "✅ 回复完成")

    return new_state


class ChatAgentSimple:
    """
    简化版基础对话 Agent

    不使用工具调用，直接进行对话。
    适用于快速响应场景。
    """

    def __init__(self, llm: Optional[BaseChatModel] = None):
        self.llm = llm or get_llm(temperature=0.7)

    def chat(
        self,
        user_input: str,
        chat_history: List[Dict] = None
    ) -> str:
        """
        简单对话

        Args:
            user_input: 用户输入
            chat_history: 对话历史

        Returns:
            回复内容
        """
        messages = [SystemMessage(content=CHAT_SYSTEM_PROMPT)]

        if chat_history:
            for msg in chat_history[-5:]:
                if msg.get("role") == "user":
                    messages.append(HumanMessage(
                        content=msg.get("content", "")))
                elif msg.get("role") == "assistant":
                    messages.append(AIMessage(content=msg.get("content", "")))

        messages.append(HumanMessage(content=user_input))

        response = self.llm.invoke(messages)
        return response.content
