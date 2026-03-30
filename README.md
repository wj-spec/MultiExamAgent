# IntelliExam-Agent

<div align="center">

**自主决策型命题专家组系统**

AI Native 的智能命题辅助系统，支持多智能体协作

[![Python 3.10+](https://img.shields.io/badge/Python-3.10%2B-blue.svg)](https://www.python.org/downloads/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115%2B-009688.svg)](https://fastapi.tiangolo.com/)
[![LangGraph](https://img.shields.io/badge/LangGraph-1.0%2B-orange.svg)](https://github.com/langchain-ai/langgraph)

</div>

---

## 📖 项目简介

IntelliExam-Agent 是一个 **AI Native** 的命题辅助系统。通过多轮对话引导用户明确需求，利用双层记忆架构积累经验，并通过多智能体协作实现试题的生成、自检与修正。

### 🎯 核心特性

| 特性 | 描述 |
|------|------|
| **三栏式现代 UI** | 左侧对话管理 / 中间聊天区 / 右侧实时 Agent 状态面板 |
| **对话式交互** | 自然语言交互，过程透明可视 |
| **双层记忆架构** | 短期记忆维持会话上下文，长期记忆基于本地 JSON 持久化 |
| **反思闭环** | "命题-质检-修正" 循环机制（最多 3 次），确保试题科学性 |
| **实时状态推送** | WebSocket 驱动，实时显示每步 Agent 进度与耗时 |
| **自我进化** | 成功经验自动沉淀，实现 Agent 持续学习 |

---

## 🚀 快速开始

### 环境要求

- Python 3.10+
- OpenAI API Key（或 DeepSeek 等兼容服务）

### 安装与启动

```bash
# 克隆项目
git clone https://github.com/your-repo/IntelliExam-Agent.git
cd IntelliExam-Agent

# 安装依赖
pip install -r requirements.txt

# 配置环境变量
cp .env.example .env
# 编辑 .env，填入 API Key

# 启动服务
uvicorn server:app --host 0.0.0.0 --port 8000 --reload
```

访问 **http://localhost:8000** 即可使用。

---

## 📁 项目结构

```
IntelliExam-Agent/
├── server.py                # FastAPI 主服务
├── main.py                  # CLI 入口
├── frontend/                # 前端（HTML/CSS/JS）
├── agents/                  # Agent 模块
│   ├── router_agent.py      # 意图路由
│   ├── memory_agent.py      # 记忆认知 Agent
│   ├── planner_agent.py     # 规划 Agent
│   ├── executor_agent.py    # 执行器（生成+质检）
│   └── consolidator_agent.py # 记忆沉淀 Agent
├── graphs/                  # LangGraph 工作流
├── tools/                   # 工具模块
├── utils/                   # 工具函数
└── data/                    # 数据目录
    ├── knowledge_base/      # 知识库文件
    ├── conversations/       # 对话历史
    └── memory/              # 长期记忆
```

---

## 🎨 技术栈

| 类别 | 技术 |
|------|------|
| **后端服务** | FastAPI + Uvicorn |
| **实时通信** | WebSocket |
| **Agent 框架** | LangChain + LangGraph |
| **前端** | HTML + CSS + JavaScript |
| **向量数据库** | Chroma |
| **LLM** | OpenAI API 兼容（GPT-4o / DeepSeek） |
| **数据持久化** | SQLite + JSON |

---

## 📄 License

MIT License

<div align="center">

**⭐ 如果这个项目对你有帮助，请给一个 Star ⭐**

</div>
