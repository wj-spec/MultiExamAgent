# IntelliExam-Agent

<div align="center">

**自主决策型命题专家组系统**

AI Native 的智能命题辅助系统，支持多智能体协作

[![Python 3.10+](https://img.shields.io/badge/Python-3.10%2B-blue.svg)](https://www.python.org/downloads/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115%2B-009688.svg)](https://fastapi.tiangolo.com/)
[![LangGraph](https://img.shields.io/badge/LangGraph-1.0%2B-orange.svg)](https://github.com/langchain-ai/langgraph)
[![License](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

</div>

---

## 📖 项目简介

IntelliExam-Agent 是一个 **AI Native** 的命题辅助系统。系统能够通过多轮对话引导用户明确需求，利用双层记忆架构积累经验，并通过多智能体协作实现试题的生成、自检与修正。

### 🎯 核心特性

| 特性 | 描述 |
|------|------|
| **三栏式现代 UI** | 左侧对话管理 / 中间聊天区 / 右侧实时 Agent 状态面板 |
| **对话式交互** | 摒弃传统表单，通过自然语言交互，过程透明可视 |
| **双层记忆架构** | 短期记忆维持会话上下文，长期记忆基于本地 JSON 持久化 |
| **反思闭环** | "命题-质检-修正" 循环机制（最多 3 次），确保试题科学性 |
| **实时状态推送** | WebSocket 驱动，右侧面板实时显示每步 Agent 进度与耗时 |
| **自我进化** | 成功经验自动沉淀，实现 Agent 的持续学习 |

---

## 🏗️ 系统架构

```
┌─────────────────────────────────────────────────────────────────┐
│         浏览器前端 (frontend/)   localhost:8000                  │
│  ┌────────────┐  ┌────────────────────┐  ┌────────────────────┐ │
│  │  左侧边栏  │  │     主对话区        │  │   右侧状态面板     │ │
│  │  对话管理  │  │  Markdown 消息流    │  │  Agent 步骤+耗时   │ │
│  │  历史列表  │  │  欢迎卡片 / 输入框  │  │  结果 + 下载按钮   │ │
│  └────────────┘  └────────────────────┘  └────────────────────┘ │
└──────────────────────────┬──────────────────────────────────────┘
                           │ WebSocket /ws/{sid}  REST /api/...
┌──────────────────────────▼──────────────────────────────────────┐
│                    server.py  (FastAPI)                          │
│  实时步骤回调推送  ·  对话管理 REST  ·  静态文件服务              │
└──────────────────────────┬──────────────────────────────────────┘
                           │ 直接调用
┌──────────────────────────▼──────────────────────────────────────┐
│  Python 业务层（不依赖前端框架）                                  │
│  graphs/workflow_server.py  ←  run_workflow_async_server()       │
│  agents/  tools/  utils/  data/                                  │
└─────────────────────────────────────────────────────────────────┘
```

### Agent 工作流

```
用户输入
    ↓
🧠 意图路由 → [命题 / 阅卷 / 闲聊]
    ↓（命题路径）
💡 记忆召回 → 历史经验检索
    ↓
🧠 认知分析 → 需求完整性判断
    ↓
   ┌─ 完整 ──→ 📋 任务规划 → 🔍 知识检索
   └─ 缺失 ──→ 追问用户
                    ↓
              ✍️ 试题生成 ⟳ 🧐 质量审核（最多3次）
                    ↓ 通过
              💾 经验沉淀 → 输出最终结果
```

---

## 🚀 快速开始

### 环境要求

- Python 3.10+
- OpenAI API Key（或 DeepSeek 等兼容服务）

### 安装步骤

```bash
# 1. 克隆项目
git clone https://github.com/your-repo/IntelliExam-Agent.git
cd IntelliExam-Agent

# 2. 安装依赖
pip install -r requirements.txt

# 3. 配置环境变量
cp .env.example .env
# 编辑 .env，填入 API Key
```

`.env` 关键配置：
```env
OPENAI_API_KEY=your_api_key_here
OPENAI_API_BASE=https://api.openai.com/v1
DEFAULT_MODEL=gpt-4o-mini

# 使用 DeepSeek 示例
# OPENAI_API_BASE=https://api.deepseek.com/v1
# DEFAULT_MODEL=deepseek-chat
```

### 启动服务

```bash
uvicorn server:app --host 0.0.0.0 --port 8000 --reload
```

访问 **http://localhost:8000** 即可使用完整三栏界面。

---

## 💡 使用示例

1. **点击示例卡片** — 首页提供"智能命题 / 智能命卷 / 智能审卷"三个示例，点击自动填充输入框
2. **自然语言输入** — 如 `帮我出5道高中数学导数选择题，难度中等`
3. **实时状态面板** — 右侧面板实时展示每个 Agent 步骤及其耗时
4. **下载结果** — 任务完成后点击"下载 Markdown 文件"一键导出

---

## 📁 项目结构

```
IntelliExam-Agent/
├── server.py                    # FastAPI 主服务（WebSocket + REST）
├── main.py                      # CLI / 测试启动入口
├── test_project.py              # 项目测试
├── DESIGN.md                    # 系统设计文档
├── requirements.txt             # 依赖配置
│
├── frontend/                    # 自定义前端（纯 HTML/CSS/JS）
│   ├── index.html               # 主页面（三栏布局）
│   ├── css/style.css            # Manus 风格全局样式
│   └── js/
│       ├── app.js               # WebSocket 管理 + 消息路由
│       ├── chat.js              # 消息渲染（Markdown 支持）
│       ├── sidebar.js           # 左侧对话管理
│       └── panel.js             # 右侧 Agent 状态面板
│
├── agents/                      # Agent 模块
│   ├── router_agent.py          # 意图路由
│   ├── memory_agent.py          # 记忆认知 Agent（核心）
│   ├── planner_agent.py         # 规划 Agent
│   ├── executor_agent.py        # 执行器（生成 + 质检）
│   └── consolidator_agent.py   # 记忆沉淀 Agent
│
├── graphs/                      # LangGraph 工作流
│   ├── state.py                 # AgentState 定义
│   ├── workflow.py              # 同步工作流
│   └── workflow_server.py       # 异步工作流（FastAPI 版）
│
├── tools/                       # 工具模块
│   ├── memory_tools.py          # 长期记忆读写
│   └── retriever.py             # 业务知识库检索
│
├── utils/                       # 工具函数
│   ├── config.py                # 配置管理
│   ├── conversation_manager.py  # 对话历史管理
│   ├── memory_manager.py        # JSON 记忆管理
│   ├── prompts.py               # Prompt 模板
│   └── ui_utils.py              # Step 名称常量
│
└── data/
    ├── knowledge_base/          # 业务知识库文件（PDF/DOCX）
    ├── conversations/           # 对话历史（JSON）
    └── memory/
        └── long_term_memory.json # 长期记忆存储
```

---

## 🔧 核心 API

### WebSocket 协议 `/ws/{session_id}`

| 方向 | 消息类型 | 说明 |
|------|----------|------|
| 客户端→服务端 | `message` | 发送用户消息 |
| 客户端→服务端 | `switch_conversation` | 切换/新建对话 |
| 服务端→客户端 | `agent_step` | 步骤状态更新（running/done） |
| 服务端→客户端 | `agent_params` | 任务参数（知识点/难度/数量） |
| 服务端→客户端 | `response` | 最终文本回复 |
| 服务端→客户端 | `result` | 结构化结果（含 Markdown + 题目数） |

### REST API

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/conversations` | 获取历史对话列表 |
| POST | `/api/conversations` | 新建对话 |
| GET | `/api/conversations/{id}` | 加载指定对话 |
| DELETE | `/api/conversations/{id}` | 删除指定对话 |
| DELETE | `/api/conversations` | 清除全部历史 |
| POST | `/api/upload` | 上传知识库文件 |
| GET | `/api/health` | 健康检查 |

---

## 🎨 技术栈

| 类别 | 技术 |
|------|------|
| **后端服务** | FastAPI + Uvicorn |
| **实时通信** | WebSocket（原生） |
| **Agent 框架** | LangChain + LangGraph |
| **前端** | 纯 HTML + CSS + JavaScript（无框架） |
| **Markdown 渲染** | marked.js + highlight.js + DOMPurify |
| **向量数据库** | Chroma |
| **LLM** | OpenAI API 兼容（GPT-4o / DeepSeek） |
| **数据持久化** | 本地 JSON 文件 |

---

## 📊 记忆架构

```
┌─────────────────────────────────┐
│   短期记忆（会话级）             │
│   Chat History · 上下文感知     │
└─────────────────────────────────┘
               ↓ 任务完成后沉淀
┌─────────────────────────────────┐
│   长期记忆（跨会话 JSON）        │
│   用户偏好 · 成功任务经验        │
│   关键词检索 + 时间衰减因子      │
└─────────────────────────────────┘
```

---

## 🛠️ 开发计划

- [x] 基础 Agent 架构
- [x] 双层记忆系统
- [x] 命题核心工作流（生成-审核-沉淀）
- [x] FastAPI + 自定义三栏前端
- [x] WebSocket 实时状态推送
- [x] 对话历史管理
- [ ] 阅卷功能完善
- [ ] 多学科模板
- [ ] 导出 Word/PDF
- [ ] 批量命题

---

## 📄 License

本项目采用 MIT License 开源协议。

---

<div align="center">

**⭐ 如果这个项目对你有帮助，请给一个 Star ⭐**

</div>
