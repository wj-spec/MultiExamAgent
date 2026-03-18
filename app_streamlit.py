"""
IntelliExam-Agent 前端应用

基于 Streamlit 构建的对话式 UI，展示 Agent 思维过程的可视化面板。
"""

import streamlit as st
from datetime import datetime
import os
import sys

# 添加项目根目录到路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from graphs.state import create_initial_state, add_chat_message
from graphs.workflow import run_workflow, run_workflow_stream, visualize_workflow
from utils.memory_manager import get_memory_manager
from tools.retriever import get_retriever, VECTOR_STORE_AVAILABLE
from utils.config import settings


# 页面配置
st.set_page_config(
    page_title="IntelliExam-Agent",
    page_icon="📚",
    layout="wide",
    initial_sidebar_state="expanded"
)

# 自定义 CSS
st.markdown("""
<style>
    .stChatMessage {
        padding: 1rem;
        border-radius: 0.5rem;
        margin-bottom: 0.5rem;
    }
    .status-message {
        padding: 0.5rem 1rem;
        border-radius: 0.25rem;
        margin: 0.25rem 0;
        background-color: #f0f2f6;
        font-size: 0.9rem;
    }
    .question-card {
        border: 1px solid #e0e0e0;
        border-radius: 0.5rem;
        padding: 1rem;
        margin: 1rem 0;
        background-color: #fafafa;
    }
    .memory-item {
        padding: 0.5rem;
        border-left: 3px solid #4CAF50;
        background-color: #f9f9f9;
        margin: 0.5rem 0;
    }
</style>
""", unsafe_allow_html=True)


def init_session_state():
    """初始化会话状态"""
    if "chat_history" not in st.session_state:
        st.session_state.chat_history = []
    if "session_id" not in st.session_state:
        st.session_state.session_id = datetime.now().strftime("%Y%m%d_%H%M%S")
    if "messages" not in st.session_state:
        st.session_state.messages = []


def render_sidebar():
    """渲染侧边栏"""
    with st.sidebar:
        st.title("📚 IntelliExam-Agent")
        st.markdown("---")

        # 知识库管理
        st.subheader("📁 知识库管理")
        if VECTOR_STORE_AVAILABLE:
            uploaded_file = st.file_uploader(
                "上传文档 (PDF/DOCX)",
                type=["pdf", "docx"],
                help="上传教材或参考资料，系统会自动向量化存储"
            )
            if uploaded_file and st.button("向量化存储"):
                with st.spinner("正在处理文档..."):
                    # 保存临时文件
                    temp_path = os.path.join("data", "knowledge_base", uploaded_file.name)
                    os.makedirs(os.path.dirname(temp_path), exist_ok=True)
                    with open(temp_path, "wb") as f:
                        f.write(uploaded_file.getbuffer())

                    # 添加到向量库
                    retriever = get_retriever()
                    success = retriever.add_documents(temp_path)

                    if success:
                        st.success(f"文档 '{uploaded_file.name}' 已添加到知识库")
                    else:
                        st.error("文档处理失败")

            # 显示知识库统计
            retriever = get_retriever()
            stats = retriever.get_stats()
            st.info(f"知识库文档数: {stats.get('document_count', 0)}")
        else:
            st.warning("知识库功能需要安装额外依赖")

        st.markdown("---")

        # 记忆库查看
        st.subheader("🧠 记忆库")
        if st.button("查看我的记忆"):
            st.session_state.show_memories = True

        if st.session_state.get("show_memories", False):
            manager = get_memory_manager()
            memories = manager.get_all_memories(limit=20)

            st.markdown(f"**共 {len(memories)} 条记忆**")

            for mem in memories[:10]:
                with st.expander(f"[{mem.get('type', 'unknown')}] {mem.get('timestamp', '')[:10]}"):
                    st.markdown(mem.get("content", ""))

        st.markdown("---")

        # 模型配置
        st.subheader("⚙️ 配置")

        # 从配置文件获取默认模型，并设置可选模型列表
        default_model = settings.default_model
        model_options = ["qwen3.5-flash", "qwen3.5-turbo", "gpt-4o-mini", "gpt-4o", "deepseek-chat"]

        # 确保默认模型在选项列表中
        if default_model not in model_options:
            model_options.insert(0, default_model)

        # 获取默认模型的索引
        default_index = model_options.index(default_model) if default_model in model_options else 0

        model = st.selectbox(
            "选择模型",
            model_options,
            index=default_index
        )
        st.session_state.model = model

        # 清除对话
        if st.button("清除对话"):
            st.session_state.chat_history = []
            st.session_state.messages = []
            st.rerun()


def render_chat_history():
    """渲染对话历史"""
    for message in st.session_state.messages:
        with st.chat_message(message["role"]):
            st.markdown(message["content"])

            # 如果有状态消息，展示
            if "status_messages" in message:
                with st.expander("查看思考过程", expanded=False):
                    for status in message["status_messages"]:
                        st.markdown(f"<div class='status-message'>{status}</div>",
                                    unsafe_allow_html=True)


def process_user_input(user_input: str):
    """处理用户输入"""
    # 添加用户消息
    st.session_state.messages.append({
        "role": "user",
        "content": user_input
    })

    # 显示用户消息
    with st.chat_message("user"):
        st.markdown(user_input)

    # 处理并显示助手响应
    with st.chat_message("assistant"):
        with st.status("正在思考...", expanded=True) as status:
            # 运行工作流
            result = run_workflow(
                user_input=user_input,
                session_id=st.session_state.session_id,
                chat_history=st.session_state.chat_history
            )

            # 显示状态消息
            for status_msg in result.get("status_messages", []):
                st.write(status_msg)

            status.update(label="处理完成", state="complete")

        # 显示最终响应
        st.markdown(result.get("final_response", "抱歉，我无法处理您的请求。"))

        # 更新会话状态
        st.session_state.messages.append({
            "role": "assistant",
            "content": result.get("final_response", ""),
            "status_messages": result.get("status_messages", [])
        })

        # 更新对话历史
        st.session_state.chat_history.append({
            "role": "user",
            "content": user_input,
            "timestamp": datetime.now().isoformat()
        })
        st.session_state.chat_history.append({
            "role": "assistant",
            "content": result.get("final_response", ""),
            "timestamp": datetime.now().isoformat()
        })


def main():
    """主函数"""
    init_session_state()
    render_sidebar()

    # 主区域标题
    st.title("🎯 智能命题助手")
    st.markdown("通过自然语言对话，让 AI 帮助您生成高质量的试题。")

    # 显示工作流图（可选）
    with st.expander("📊 查看系统架构"):
        st.markdown(visualize_workflow())

    st.markdown("---")

    # 渲染对话历史
    render_chat_history()

    # 用户输入
    if user_input := st.chat_input("输入您的命题需求..."):
        process_user_input(user_input)


if __name__ == "__main__":
    main()
