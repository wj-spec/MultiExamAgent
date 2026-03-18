# IntelliExam-Agent 项目完全指南

## 目录

1. [项目概述](#1-项目概述)
2. [核心架构](#2-核心架构)
3. [Agent 系统](#3-agent-系统)
4. [工具系统](#4-工具系统)
5. [工作流系统](#5-工作流系统)
6. [数据结构](#6-数据结构)
7. [配置与部署](#7-配置与部署)
8. [使用指南](#8-使用指南)

---

## 1. 项目概述

### 1.1 项目定位

**IntelliExam-Agent** 是一个 **AI Native 自主决策型命题专家组系统**，专为考试机构、考试院、教师等用户提供智能化的命题辅助服务。

### 1.2 核心能力

| 能力 | 描述 |
|------|------|
| **双层记忆架构** | 短期（会话上下文）+ 长期（本地JSON），支持用户偏好学习与经验检索 |
| **认知驱动需求分析** | 基于LLM推理替代槽位填充，自主判断需求完整性 |
| **反思闭环** | "命题-质检-修正"循环（最多3次），确保试题科学性 |
| **自我进化** | 成功经验自动沉淀至长期记忆，实现Agent持续学习 |
| **Tool Calling** | 全链路Function Calling，支持工具编排 |
| **ReAct推理** | Thought-Action-Observation完整推理循环 |
| **并行协作** | Multi-Agent并行执行，批量命题效率提升3倍 |
| **MCP协议** | 支持Claude Desktop/GitHub Copilot等外部调用 |

### 1.3 技术栈

```
后端框架: Python 3.10+
Agent框架: LangChain + LangGraph
前端框架: Chainlit / Streamlit
向量数据库: Chroma
持久化: 本地JSON + SQLite
协议支持: MCP (Model Context Protocol)
```

---

## 2. 核心架构

### 2.1 分层架构图

```
┌─────────────────────────────────────────────────────────────┐
│                      用户交互层                              │
│         Chainlit UI / Streamlit UI / MCP Client             │
├─────────────────────────────────────────────────────────────┤
│                      入口路由层                              │
│              Router Agent (ReAct + Tool Calling)            │
├─────────────────────────────────────────────────────────────┤
│                      业务控制层                              │
│    Memory Agent │ Planner Agent │ Consolidator Agent        │
├─────────────────────────────────────────────────────────────┤
│                      执行层                                  │
│         Creator Agent │ Auditor Agent │ Aggregator          │
├─────────────────────────────────────────────────────────────┤
│                      工具层                                  │
│    Knowledge Tools │ Question Tools │ Validation Tools      │
├─────────────────────────────────────────────────────────────┤
│                      数据层                                  │
│    Chroma DB │ BM25 Index │ Long-term Memory │ Traces       │
└─────────────────────────────────────────────────────────────┘
```

### 2.2 项目目录结构

```
exam_multi_agent/
├── agents/                      # Agent 模块
│   ├── base/                    # Agent 基类
│   │   ├── __init__.py          # ToolCallingAgent
│   │   └── react_agent.py       # ReActAgent
│   ├── tools/                   # 工具集
│   │   ├── base.py              # 工具基类与注册中心
│   │   ├── knowledge_tools.py   # 知识检索工具
│   │   ├── question_tools.py    # 试题操作工具
│   │   └── validation_tools.py  # 验证工具
│   ├── tracer/                  # 追踪器
│   │   └── agent_tracer.py      # 决策追踪
│   ├── router_agent.py          # 路由 Agent (原版)
│   ├── router_agent_v2.py       # 路由 Agent V2 (Tool Calling)
│   ├── react_router_agent.py    # ReAct Router Agent
│   ├── memory_agent.py          # 记忆认知 Agent
│   ├── planner_agent.py         # 规划 Agent (原版)
│   ├── planner_agent_v2.py      # 规划 Agent V2 (Tool Calling)
│   ├── executor_agent.py        # 执行 Agent (Creator + Auditor)
│   ├── creator_agent_v2.py      # 生成 Agent V2 (Tool Calling)
│   ├── consolidator_agent.py    # 记忆沉淀 Agent (原版)
│   ├── consolidator_agent_v2.py # 记忆沉淀 Agent V2
│   └── learning_agent.py        # 主动学习 Agent
│
├── graphs/                      # 工作流
│   ├── state.py                 # AgentState 定义
│   ├── workflow.py              # 标准工作流
│   ├── workflow_server.py       # 异步工作流服务
│   └── parallel_workflow.py     # 并行工作流
│
├── tools/                       # 核心工具
│   ├── retriever.py             # 知识库检索 (Hybrid Search)
│   └── memory_tools.py          # 记忆读写工具
│
├── mcp_servers/                 # MCP 服务
│   ├── knowledge_server.py      # 知识检索 MCP Server
│   └── agent_server.py          # Agent 能力 MCP Server
│
├── utils/                       # 工具函数
│   ├── config.py                # 配置管理
│   ├── prompts.py               # Prompt 模板
│   ├── memory_manager.py        # 记忆管理器
│   ├── conversation_manager.py  # 对话管理
│   └── ui_utils.py              # UI 工具
│
├── frontend/                    # 前端资源
│   ├── index.html
│   ├── css/style.css
│   └── js/                      # JavaScript 模块
│
├── data/                        # 数据目录
│   ├── knowledge_base/          # 知识库文件
│   ├── chroma_db/               # 向量数据库
│   ├── memory/                  # 长期记忆
│   │   └── long_term_memory.json
│   ├── conversations/           # 对话记录
│   └── traces/                  # 追踪数据
│
├── tests/                       # 测试文件
│   ├── test_tool_calling.py
│   ├── test_react_agent.py
│   └── test_e2e_integration.py
│
├── main.py                      # 主入口 (Chainlit)
├── app_streamlit.py             # Streamlit 入口
├── server.py                    # FastAPI 服务
└── requirements.txt             # 依赖列表
```

---

## 3. Agent 系统

### 3.1 Agent 分类

| Agent | 层级 | 职责 | 版本 |
|-------|------|------|------|
| **Router Agent** | 入口层 | 意图识别与路由分发 | V1 + V2 + ReAct |
| **Memory Agent** | 控制层 | 长期记忆召回、需求认知分析 | V1 |
| **Planner Agent** | 控制层 | 任务规划与分解 | V1 + V2 |
| **Creator Agent** | 执行层 | 试题生成 | V1 + V2 |
| **Auditor Agent** | 执行层 | 质量审核 | V1 |
| **Consolidator Agent** | 控制层 | 经验沉淀、记忆写入 | V1 + V2 |
| **Learning Agent** | 增强层 | 失败分析、策略优化 | V1 |

### 3.2 Agent 基类

#### ToolCallingAgent

```python
from agents.base import ToolCallingAgent

class MyAgent(ToolCallingAgent):
    @property
    def name(self) -> str:
        return "my_agent"
    
    @property
    def system_prompt(self) -> str:
        return "你是一个智能 Agent"
    
    def run(self, user_input: str) -> AgentTrace:
        # 运行 Agent，自动处理 Tool Calling
        trace = self.run_with_tools(user_input)
        return trace
```

**核心能力**：
- 自动绑定工具到 LLM
- 多轮工具调用
- 错误处理与重试
- 决策追踪

#### ReActAgent

```python
from agents.base.react_agent import ReActAgent

class MyReActAgent(ReActAgent):
    @property
    def name(self) -> str:
        return "my_react_agent"
    
    @property
    def system_prompt(self) -> str:
        return "你是一个 ReAct Agent"
```

**核心能力**：
- Thought-Action-Observation 循环
- 显式推理过程
- 可解释性强

### 3.3 Agent 工作流程

```
用户输入
    │
    ▼
┌─────────────┐
│ Router Agent│ ──── 意图识别 (proposition/grading/chat)
└─────────────┘
    │
    ▼ (proposition)
┌─────────────┐
│ Memory Agent│ ──── 召回长期记忆 + 认知分析
└─────────────┘
    │
    ├─ 需求不完整 → 追问用户
    │
    ▼ 需求完整
┌─────────────┐
│Planner Agent│ ──── 任务规划
└─────────────┘
    │
    ▼
┌─────────────┐
│Creator Agent│ ──── 试题生成
└─────────────┘
    │
    ▼
┌─────────────┐
│Auditor Agent│ ──── 质量审核
└─────────────┘
    │
    ├─ 不通过 → 返回 Creator (最多3次)
    │
    ▼ 通过
┌──────────────────┐
│Consolidator Agent│ ──── 经验沉淀
└──────────────────┘
    │
    ▼
  完成
```

---

## 4. 工具系统

### 4.1 工具基类

```python
from agents.tools.base import BaseTool, ToolParameter, ToolResult

class MyTool(BaseTool):
    def __init__(self):
        super().__init__()
        self._name = "my_tool"
        self._description = "工具描述"
        self._parameters = [
            ToolParameter(
                name="input",
                type="string",
                description="输入参数",
                required=True
            )
        ]
    
    def execute(self, input: str) -> ToolResult:
        # 执行逻辑
        return ToolResult(success=True, data={"result": "ok"})
```

### 4.2 工具注册中心

```python
from agents.tools.base import registry

# 自动注册（装饰器方式）
@register_tool
class MyTool(BaseTool):
    ...

# 手动注册
registry.register(MyTool())

# 获取工具
tool = registry.get("my_tool")

# 导出 OpenAI 格式
openai_funcs = registry.to_openai_functions()

# 导出 LangChain 格式
lc_tools = registry.to_langchain_tools()
```

### 4.3 内置工具

#### 知识检索工具 (`knowledge_tools.py`)

| 工具 | 功能 |
|------|------|
| `SearchKnowledgeTool` | 混合检索知识库 |
| `GetDocumentSummaryTool` | 获取文档摘要 |
| `ListCollectionsTool` | 列出知识库集合 |
| `AddKnowledgeTool` | 添加知识文档 |

#### 试题操作工具 (`question_tools.py`)

| 工具 | 功能 |
|------|------|
| `GenerateQuestionTool` | 生成试题模板 |
| `FormatQuestionsTool` | 格式化为 Markdown |
| `ValidateQuestionTool` | 验证试题结构 |
| `ParseQuestionRequestTool` | 解析自然语言请求 |

#### 验证工具 (`validation_tools.py`)

| 工具 | 功能 |
|------|------|
| `ValidateFormatTool` | 格式验证 |
| `CheckDifficultyTool` | 难度检查 |
| `ValidateAnswerTool` | 答案验证 |
| `CheckScientificTool` | 科学性检查 |

---

## 5. 工作流系统

### 5.1 标准工作流

```python
from graphs.workflow import run_workflow, run_workflow_stream

# 同步运行
result = run_workflow("帮我出5道代数选择题")

# 流式运行
for state in run_workflow_stream("帮我出5道代数选择题"):
    print(state["current_step"])
```

### 5.2 并行工作流

```python
from graphs.parallel_workflow import run_parallel_workflow

# 自动判断是否并行（数量>3时并行）
result = run_parallel_workflow("帮我出10道代数选择题")
```

**并行流程**：
```
知识检索
    │
    ├─────┬─────┬─────┐
    ▼     ▼     ▼     ▼
Creator1 Creator2 Creator3  (并行)
    │     │     │     │
    └─────┴─────┴─────┘
            │
            ▼
       Aggregator (聚合)
            │
            ▼
       Auditor (审核)
```

### 5.3 状态流转

工作流通过 `AgentState` 在各节点间传递状态：

```python
from graphs.state import AgentState, create_initial_state

# 创建初始状态
state = create_initial_state("用户输入", "session_id")

# 状态字段
state["intent"]           # 意图
state["extracted_params"] # 提取的参数
state["draft_questions"]  # 生成的试题
state["audit_feedback"]   # 审核反馈
state["status_messages"]  # 状态消息（前端展示）
```

---

## 6. 数据结构

### 6.1 AgentState

```python
class AgentState(TypedDict):
    # 输入输出
    user_input: str
    chat_history: List[dict]
    final_response: str
    
    # 路由状态
    intent: Literal["proposition", "grading", "chat"]
    routing_reason: str
    
    # 记忆认知层
    retrieved_long_term_memory: List[MemoryItem]
    extracted_params: ExtractedParams
    is_info_complete: bool
    missing_info: List[str]
    follow_up_question: str
    
    # 执行层
    plan_steps: List[str]
    current_step_index: int
    retrieved_knowledge: str
    
    # 生成与反思
    draft_questions: List[QuestionItem]
    audit_feedback: str
    revision_count: int
    max_revisions: int
    
    # 控制流
    should_continue: bool
    next_node: str
    error_message: Optional[str]
    
    # 元数据
    session_id: str
    timestamp: str
    status_messages: List[str]
```

### 6.2 QuestionItem

```python
class QuestionItem(TypedDict):
    id: str
    content: str              # 题目内容
    question_type: str        # choice/fill_blank/essay
    difficulty: float         # 0.0-1.0
    topic: str                # 知识点
    options: Optional[List[str]]  # 选择题选项
    answer: str               # 答案
    explanation: str          # 解析
    audit_passed: bool        # 审核是否通过
    audit_feedback: Optional[str]  # 审核反馈
```

### 6.3 长期记忆

存储位置：`data/memory/long_term_memory.json`

```json
[
    {
        "id": "mem_001",
        "timestamp": "2025-03-16T10:00:00",
        "type": "user_preference",
        "content": "用户偏好中等难度的选择题",
        "metadata": {"source": "session_abc"}
    },
    {
        "id": "mem_002",
        "timestamp": "2025-03-16T11:00:00",
        "type": "task_experience",
        "content": "成功生成代数选择题，用户满意",
        "metadata": {"rating": 5}
    }
]
```

记忆类型：
- `user_preference`: 用户偏好
- `task_experience`: 任务经验
- `feedback`: 反馈记录

---

## 7. 配置与部署

### 7.1 环境变量

创建 `.env` 文件：

```env
# LLM 配置
OPENAI_API_KEY=your_api_key
OPENAI_API_BASE=https://api.openai.com/v1
LLM_PROVIDER=openai
LLM_MODEL=gpt-4

# Embedding 配置
EMBEDDING_PROVIDER=openai
EMBEDDING_MODEL=text-embedding-3-small
```

### 7.2 配置文件

主要配置在 `utils/config.py`：

```python
from utils.config import settings, get_llm, get_embedding_config

# 获取 LLM 实例
llm = get_llm(temperature=0.7)

# 获取 Embedding 配置
embedding_config = get_embedding_config()
```

### 7.3 启动方式

**Chainlit 界面**：
```bash
chainlit run main.py
```

**Streamlit 界面**：
```bash
streamlit run app_streamlit.py
```

**FastAPI 服务**：
```bash
uvicorn server:app --reload
```

**MCP Server**：
```bash
python mcp_servers/agent_server.py
```

---

## 8. 使用指南

### 8.1 基本使用

**命题请求**：
```
用户: 帮我出5道代数选择题，难度中等
```

系统流程：
1. Router 识别意图为 `proposition`
2. Memory Agent 召回用户偏好
3. Planner 规划执行步骤
4. Creator 生成试题
5. Auditor 审核质量
6. Consolidator 沉淀经验

**追问场景**：
```
用户: 帮我出几道数学题

系统: 好的，请问题型是选择题、填空题还是解答题？
用户: 选择题

系统: 请问难度要求是什么？
用户: 中等

系统: [生成试题...]
```

### 8.2 使用 MCP Client 调用

在 Claude Desktop 或支持 MCP 的客户端中：

```json
// 调用 generate_questions 工具
{
    "topic": "代数",
    "question_type": "choice",
    "difficulty": "medium",
    "count": 5
}
```

### 8.3 编程方式调用

```python
from graphs.workflow import run_workflow

# 运行工作流
result = run_workflow(
    user_input="帮我出5道代数选择题",
    session_id="test_session",
    chat_history=[]
)

# 获取结果
questions = result.get("draft_questions", [])
for q in questions:
    print(f"题目: {q['content']}")
    print(f"答案: {q['answer']}")
```

### 8.4 使用追踪器

```python
from agents.tracer import AgentTracer

# 创建追踪器
tracer = AgentTracer()

# 开始追踪
tracer.start_trace("用户输入", "proposition")

# 记录步骤
tracer.record_step(
    agent_name="router",
    action="classify_intent",
    input_data={"query": "出题"},
    duration_ms=100
)

# 结束追踪
tracer.end_trace("最终输出", success=True)

# 查看统计
stats = tracer.get_statistics()
print(f"成功率: {stats['success_rate']}")
```

### 8.5 使用学习 Agent

```python
from agents.learning_agent import LearningAgent

agent = LearningAgent()

# 分析失败案例
failures = [
    {"user_input": "出题", "error": "题型未指定"},
    {"user_input": "生成试题", "error": "难度未指定"}
]
patterns = agent.analyze_failures(failures)

# 获取策略建议
metrics = {"pass_rate": 0.7, "avg_iterations": 3.0}
updates = agent.suggest_strategy_updates("creator", metrics)
```

---

## 附录

### A. 常见问题

**Q: 如何添加新的工具？**

```python
from agents.tools.base import BaseTool, ToolParameter, ToolResult, register_tool

@register_tool
class MyNewTool(BaseTool):
    def __init__(self):
        super().__init__()
        self._name = "my_new_tool"
        self._description = "新工具描述"
        self._parameters = [...]
    
    def execute(self, **kwargs) -> ToolResult:
        # 实现逻辑
        return ToolResult(success=True, data={})
```

**Q: 如何切换 LLM Provider？**

修改 `.env` 文件：
```env
LLM_PROVIDER=ollama
LLM_MODEL=llama2
```

**Q: 如何查看追踪数据？**

```python
from agents.tracer import get_tracer

tracer = get_tracer()
traces = tracer.list_traces()
for t in traces:
    print(f"Trace: {t['trace_id']}, Success: {t['success']}")
```

### B. 测试运行

```bash
# 运行所有测试
pytest tests/ -v

# 运行特定测试
pytest tests/test_tool_calling.py -v

# 运行端到端测试
pytest tests/test_e2e_integration.py -v
```

### C. 项目依赖

```
langchain>=0.1.0
langchain-openai>=0.0.5
langgraph>=0.0.20
chromadb>=0.4.0
chainlit>=0.7.0
streamlit>=1.30.0
fastapi>=0.109.0
uvicorn>=0.27.0
mcp>=0.9.0
```

---

*文档版本: 2.0.0*
*最后更新: 2025-03-16*
