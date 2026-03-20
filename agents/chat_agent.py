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


CHAT_SYSTEM_PROMPT = """你是一个友善的 AI 助手，负责与用户进行自然对话。

## 你的能力
1. 回答各类问题，提供信息和帮助
2. 联网搜索最新信息
3. 分析用户上传的文档内容
4. 理解和处理用户的语音输入

## 工作原则
- 简洁友好，避免过度专业化
- 遇到不确定的信息，主动联网核实
- 如果用户提到命题/出题等需求，提示可以切换到专业模式

## 模式切换提示
当用户明确表达以下意图时，在回复末尾添加模式切换标记：
- 命题/出题需求：回复末尾添加 [MODE_SWITCH:proposition]
- 审卷/批改需求：回复末尾添加 [MODE_SWITCH:grading]
- 组卷需求：回复末尾添加 [MODE_SWITCH:paper_generation]

示例：
用户："帮我出几道数学题"
你的回复："好的！我可以帮您生成数学试题。为了提供更专业的命题服务，建议切换到专业模式。[MODE_SWITCH:proposition]"

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

    def __init__(self, llm: Optional[BaseChatModel] = None):
        """
        初始化基础对话 Agent

        Args:
            llm: 语言模型实例
        """
        # 延迟导入工具，避免循环依赖
        from agents.tools.search_tools import SearchInternetTool, BrowseWebTool
        from agents.tools.attachment_tools import AnalyzeAttachmentTool
        from agents.tools.speech_tools import TextNormalizeTool

        super().__init__(
            llm=llm or get_llm(temperature=0.7),
            tools=[
                SearchInternetTool(),
                BrowseWebTool(),
                AnalyzeAttachmentTool(),
                TextNormalizeTool(),
            ],
            max_iterations=3,
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
        attachments: List[Dict] = None
    ) -> Dict[str, Any]:
        """
        执行基础对话

        Args:
            user_input: 用户输入
            chat_history: 对话历史
            attachments: 附件列表 [{"filename": "", "content": "", "type": ""}]

        Returns:
            {
                "response": str,
                "mode_switch": Optional[str],
                "used_tools": List[str]
            }
        """
        # 构建消息
        messages = [SystemMessage(content=self.system_prompt)]

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
        检测回复中的模式切换标记

        Args:
            response: AI 回复

        Returns:
            模式名称或 None
        """
        match = re.search(r'\[MODE_SWITCH:(\w+)\]', response)
        if match:
            return match.group(1)
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
        attachments=state.get("attachments", [])
    )

    # 更新状态
    new_state = dict(new_state)
    new_state["final_response"] = result["response"]
    new_state["next_node"] = "end"
    new_state["should_continue"] = False

    # 如果检测到模式切换
    if result.get("mode_switch"):
        new_state["mode_transition"] = "enter"
        new_state["proposition_needed"] = True
        new_state["primary_intent"] = result["mode_switch"]
        new_state = add_status_message(
            new_state,
            f"🔄 检测到专业模式需求: {result['mode_switch']}"
        )

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
