"""
命题 Solver Agent (agents/proposition/solver.py)

职责：按照 Planner 生成的 TodoTask 逐项执行命题任务。
每个任务执行通过 WebSocket 实时推送进度更新。

支持工具：
- knowledge_analysis: RAG 检索 + LLM 分析
- question_generate: 结构化题目生成
- difficulty_calibration: 难度系数估算
- quality_audit: 科学性+规范性审核
- answer_verify: 答案验证
- report_generate: 命题说明报告
- document_export: 文档导出（预留）

扩展支持：
- MCP 工具动态注入
- Skills 系统集成
"""

import json
import time
from datetime import datetime
from typing import Optional, Callable, Awaitable, List, Dict, Any

from services.todo_service import TodoService
from utils.config import get_llm


# ==================== 各任务类型的执行 Prompt ====================

TASK_PROMPTS = {
    "knowledge_analysis": """你是一位资深命题教研员。请根据以下需求，完成知识点分析：

需求：{user_query}
参数：{params}

请输出：
1. **考查知识点清单**（与课程标准对应，精确到二级知识点）
2. **双向细目表**（知识点 × 认知层次 × 题型配比建议）
3. **重点难点说明**（哪些知识点是高频考点，哪些是难点）
4. **命题限制说明**（哪些内容超纲，需要规避）

输出格式为 Markdown，要求专业、具体、可操作。""",

    "question_generate": """你是一位国家级命题专家。请根据规格要求生成试题：

任务规格：{description}
知识点分析参考：{context}
用户需求：{user_query}

要求：
- 严格遵循题型规范（单选/多选/填空/解答题格式）
- 选择题选项须平行，无明显干扰项错误
- 解答题设分合理，有清晰的评分标准
- 难度控制在指定水平
- 内容不超纲，情境贴近实际

请以 JSON 数组格式输出每道题：
[
  {
    "id": "Q1",
    "type": "choice|fill|essay",
    "content": "题目正文（含图表描述）",
    "options": ["A.", "B.", "C.", "D."],
    "answer": "参考答案",
    "score": 5,
    "difficulty": 0.6,
    "knowledge_point": "对应知识点",
    "cognitive_level": "记忆|理解|应用|分析|综合|创造",
    "explanation": "详细解析"
  }
]""",

    "difficulty_calibration": """你是一位教育测量专家。请对以下试题进行难度校准：

试题集合：{questions}
目标难度：{target_difficulty}

请对每道题：
1. 估算难度系数（0~1，越低越难）
2. 估算区分度（D 值）
3. 判断是否需要调整（过难/过易）
4. 给出调整建议

输出为 Markdown 表格 + 总体评估报告。""",

    "quality_audit": """你是一位严格的命题质量审核员。请对以下试题进行全面审核：

待审试题：{questions}

审核维度：
1. **科学性**：内容正确无误，无歧义
2. **规范性**：表述符合命题规范，标点正确
3. **独特性**：无重题，情境新颖
4. **答案唯一性**：正确答案唯一确定
5. **教育价值**：考查目标明确，有区分度

对每道题给出：✅通过 / ⚠️建议修改 / ❌必须修改

最后给出整体质量评分（0-100分）和修改建议清单。""",

    "answer_verify": """你是一位专业学科教师。请验证以下题目的参考答案：

待验证题目：{questions}

验证要求：
1. 逐步骤验算每道题的答案
2. 检查解题过程的逻辑性
3. 验证评分标准的合理性
4. 标注每步得分点

对于发现错误的题目，给出正确答案和详细解析。""",

    "report_generate": """你是一位命题组组长。请根据本次命题过程，生成命题说明报告：

命题任务：{user_query}
题目列表：{questions}
知识点分析：{context}

报告应包含：
1. **命题背景与目的**
2. **考查范围与课标依据**
3. **双向细目表**（表格形式）
4. **题型分布与分值设计**
5. **难度结构分析**
6. **命题说明**（各题的考查意图）
7. **使用建议**（适用年级/备考阶段）

输出为规范的 Markdown 文档。""",
}


# ==================== 命题 Solver 核心类 ====================

class PropositionSolver:
    """
    命题执行 Agent

    逐任务调用适当的工具执行命题操作，
    执行过程中通过回调实时推送状态。
    """

    def __init__(
        self,
        mcp_tools: list = None,
        skills: list = None,
    ):
        self.llm = get_llm(temperature=0.5)
        self.mcp_tools = mcp_tools or []
        self.skills = skills or []
        # 跨任务共享的执行上下文
        self._context: Dict[str, Any] = {}

    def _build_task_prompt(self, task: dict, user_query: str) -> str:
        """根据任务类型构建执行 Prompt"""
        task_type = task.get("task_type", "question_generate")
        template = TASK_PROMPTS.get(task_type, TASK_PROMPTS["question_generate"])

        return template.format(
            description=task.get("description", ""),
            user_query=user_query,
            params=json.dumps(self._context.get("params", {}), ensure_ascii=False),
            questions=json.dumps(self._context.get("questions", []), ensure_ascii=False),
            context=self._context.get("knowledge_analysis", ""),
            target_difficulty=self._context.get("target_difficulty", "中等（0.5~0.6）"),
        )

    def _build_preview_markdown(self) -> str:
        """构建当前进度的预览 Markdown"""
        parts = []
        if self._context.get("knowledge_analysis"):
            parts.append("### 📚 知识点与考纲分析\n" + self._context["knowledge_analysis"])
        
        questions = self._context.get("questions", [])
        if questions:
            parts.append(f"### 📝 试题草稿 ({len(questions)}道)\n")
            for i, q in enumerate(questions, 1):
                parts.append(f"**第 {i} 题** [{q.get('type', '')}] (分值: {q.get('score', '')}, 难度: {q.get('difficulty', '')})\n{q.get('content', '')}")
                if q.get('options'):
                    parts.append("\n".join(q['options']))
                parts.append(f"\n*答案: {q.get('answer', '')}*\n*解析: {q.get('explanation', '')}*\n---")
                
        return "\n\n".join(parts)

    async def _execute_with_rag(self, task: dict, user_query: str) -> str:
        """带 RAG 检索的任务执行（用于 knowledge_analysis）"""
        # 尝试调用 RAG 检索
        rag_context = ""
        try:
            from tools.retriever import get_retriever, VECTOR_STORE_AVAILABLE
            if VECTOR_STORE_AVAILABLE:
                retriever = get_retriever()
                docs = retriever.get_relevant_documents(user_query)
                if docs:
                    rag_context = "\n\n".join(d.page_content for d in docs[:3])
        except Exception:
            pass

        prompt = self._build_task_prompt(task, user_query)
        if rag_context:
            prompt = f"[知识库参考资料]\n{rag_context}\n\n" + prompt

        from langchain_core.messages import HumanMessage
        response = await self.llm.ainvoke([HumanMessage(content=prompt)])
        return response.content

    async def execute_task(
        self,
        task: dict,
        user_query: str,
        on_update: Optional[Callable[[dict], Awaitable[None]]] = None,
    ) -> str:
        """
        执行单个 TodoTask

        Args:
            task: TodoTask 字典
            user_query: 原始用户需求（用于上下文注入）
            on_update: 状态更新回调（推送 WebSocket 事件）

        Returns:
            Markdown 格式的执行结果
        """
        task_id = task["id"]
        task_type = task.get("task_type", "question_generate")
        start_time = time.time()

        # 标记为运行中
        TodoService.update_task_status(task_id, "running")
        if on_update:
            await on_update({
                "type": "todo_task_update",
                "task": {**task, "status": "running"},
            })

        # Phase 3: 单题微操干预支持。如果在重跑时存在评论/用户引导，作为附加指令追加。
        comments = task.get("comments", [])
        if comments:
            user_feedback = "\n".join([f"- {c.get('author', 'user')}: {c.get('content', '')}" for c in comments])
            user_query = user_query + f"\n\n[重点注意：针对当前任务的修订要求]\n{user_feedback}"

        try:
            # 根据任务类型选择执行策略
            if task_type in ("knowledge_analysis",):
                if on_update:
                    await on_update({"type": "todo_task_update", "task": {**task, "status": "running", "current_step": "检索本地题库与考点..."}})
                result = await self._execute_with_rag(task, user_query)
                self._context["knowledge_analysis"] = result[:2000]

            else:
                if on_update:
                    await on_update({"type": "todo_task_update", "task": {**task, "status": "running", "current_step": "调用模型生成内容..."}})
                prompt = self._build_task_prompt(task, user_query)
                from langchain_core.messages import HumanMessage
                response = await self.llm.ainvoke([HumanMessage(content=prompt)])
                result = response.content
                
                if on_update:
                    await on_update({"type": "todo_task_update", "task": {**task, "status": "running", "current_step": "验证数据结构与闭环逻辑..."}})

                # 如果是题目生成，尝试解析并缓存
                if task_type == "question_generate":
                    try:
                        questions = json.loads(result)
                        existing = self._context.get("questions", [])
                        self._context["questions"] = existing + (questions if isinstance(questions, list) else [])
                    except (json.JSONDecodeError, ValueError):
                        pass

            elapsed_ms = int((time.time() - start_time) * 1000)

            # 标记为完成
            updated = TodoService.update_task_status(
                task_id, "done",
                result=result,
                elapsed_ms=elapsed_ms
            )
            if on_update:
                await on_update({
                    "type": "todo_task_result",
                    "task_id": task_id,
                    "result": result,
                    "elapsed_ms": elapsed_ms,
                })
                if updated:
                    await on_update({
                        "type": "todo_task_update",
                        "task": updated,
                    })

                # 推送内容预览到前台右侧画布
                preview_markdown = self._build_preview_markdown()
                if preview_markdown:
                    await on_update({
                        "type": "content_preview",
                        "markdown": preview_markdown
                    })

            return result

        except Exception as e:
            error_msg = f"任务执行失败: {str(e)}"
            TodoService.update_task_status(task_id, "need_revision", result=error_msg)
            if on_update:
                await on_update({
                    "type": "todo_task_update",
                    "task": {**task, "status": "need_revision"},
                })
            raise

    async def execute_group(
        self,
        group: dict,
        user_query: str,
        on_update: Optional[Callable[[dict], Awaitable[None]]] = None,
    ) -> Dict[str, str]:
        """
        执行任务组（按依赖顺序）

        Args:
            group: TodoGroup 字典
            user_query: 原始用户需求
            on_update: 状态更新回调

        Returns:
            {task_id: result} 映射
        """
        from services.todo_service import TodoService

        tasks = sorted(group.get("tasks", []), key=lambda t: t.get("order", 0))
        results: Dict[str, str] = {}

        # 初始化 context
        self._context = {
            "params": {},
            "questions": [],
            "knowledge_analysis": "",
        }

        TodoService.update_group_status(group["id"], "running")

        for task in tasks:
            if task["status"] not in ("ready", "need_revision"):
                continue  # 跳过非就绪任务

            try:
                result = await self.execute_task(task, user_query, on_update=on_update)
                results[task["id"]] = result
            except Exception:
                # 单任务失败不中断整体流程
                results[task["id"]] = ""
                continue

        TodoService.update_group_status(group["id"], "done")
        return results
