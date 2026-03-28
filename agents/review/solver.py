"""
审题 Solver Agent (agents/review/solver.py)

职责：按照 Review Planner 生成的审题 TodoTask 逐项执行审核任务。
复用 Proposition Solver 的基础架构，追加审题专用工具和 Prompt。
"""

import json
import time
from typing import Optional, Callable, Awaitable, Dict, Any

from services.todo_service import TodoService
from utils.config import get_llm


# ==================== 审题任务 Prompt ============

REVIEW_TASK_PROMPTS = {
    "comprehension": """你是一位经验丰富的命题审核专家。请对以下试题/试卷进行整体阅题梳理：

试题内容：
{exam_content}

请输出：
1. **试卷结构概述**（题型、题量、总分）
2. **考查范围判断**（涉及哪些知识模块）
3. **整体印象评估**（难度印象、题量合理性、排版情况）
4. **重点关注事项**（初步发现的潜在问题）

用 Markdown 格式输出，要求简洁、专业。""",

    "student_adversarial_review": """你现在扮演一名**正在考场上做题的高中优等生**。面对以下试题，你需要抛开"这是命题专家出的题"的预设，完全以做题者的视角去尝试解答它。

试题内容：
{exam_content}

做题任务要求：
1. 逐题展示你详细的做题过程和思考链路。
2. 记录你在做题中的真实感受：
   - 是否感觉已知条件给得不够？（比如缺少某个物理量、没说明能否忽略空气阻力等）
   - 是否读完题目后产生了歧义，觉得有两种理解方式？
   - 是否在计算中得出了多个合理解答？
   - 选项中是否没有你算出来的答案，或者有两个意思相近的正确选项？
3. 如果你在任何一题中“卡壳”或发现漏洞，立即终止该题的做题并抛出 【学生质疑】 报告。

输出格式：
- 逐题做题过程录
- 学生视角的疑点报告（如果顺利解出则报告：做题顺畅，无发现条件缺失或多解问题）""",

    "syllabus_check": """你是一位熟悉国家课程标准的命题专家。请对以下试题进行课标核查：

试题内容：
{exam_content}

核查要点：
1. 每道题的知识点是否在课程标准规定范围内
2. 是否有超纲内容（标注具体题号）
3. 知识点覆盖是否与命题范围声明一致
4. 是否有偏题/怪题不符合主流命题导向

输出格式：
- 题目逐题核查表（题号 | 知识点 | 是否合规 | 说明）
- 整体课标符合度评价（百分比 + 文字）
- 需重点关注/修改的题目清单""",

    "science_check": """你是一位严格的学科专家，请对以下试题进行科学性全面审核：

试题内容：
{exam_content}

审核维度（根据学科选择）：
- **数学**：公式正确性、计算过程无误、数学符号规范
- **物理**：物理量单位、公式适用条件、实验描述准确性
- **化学**：化学方程式配平、条件标注、安全性
- **语文**：文学常识准确、引用规范
- **英语**：语言地道性、文化背景正确性

对每道题给出：
- ✅ 科学正确
- ⚠️ 存在小问题（附说明）
- ❌ 存在严重错误（附正确解析）

最后汇总：科学性评分（0-100）""",

    "difficulty_assessment": """你是一位教育测量专家。请对以下试题进行难度评估：

试题内容：
{exam_content}

评估内容：
1. 每道题的预估难度系数（0-1，越低越难）
2. 每道题的预估区分度（D 值，0-1）
3. 试卷整体难度结构分析（easy:medium:hard 比例）
4. 与目标难度的偏差说明

输出：
| 题号 | 题型 | 预估难度 | 预估区分度 | 建议调整 |
|------|------|---------|-----------|---------|
| ...  | ...  | ...     | ...       | ...     |

整体难度评价（综合难度系数 + 结构评语）""",

    "answer_verify": """你是一位严谨的学科教师，请逐题验证以下试题的参考答案：

试题内容（含答案）：
{exam_content}

验证要求：
1. 逐步骤推导每道题的答案
2. 对于计算题，展示完整计算过程
3. 标注每道题的得分点是否明确
4. 发现答案错误时给出正确答案

输出格式：
题号1：
- 验证过程：[逐步推导]
- 结论：✅ 答案正确 / ❌ 答案有误（正确答案应为...）
- 评分标准：合理 / 需细化

最终统计：正确率 X/总题数""",

    "language_review": """你是一位语言规范专家，请对以下试题的命题语言进行规范性审核：

试题内容：
{exam_content}

审核维度：
1. **表述清晰度**：题意是否明确，无歧义
2. **语言规范性**：是否符合命题语言规范（如"下列说法正确的是"vs"哪个说法是对的"）
3. **标点符号**：标点使用是否规范
4. **数字/单位格式**：中文数字/阿拉伯数字使用是否一致，单位格式是否标准
5. **选项平行性**：选择题选项是否平行，无逻辑重叠

逐题标注问题，并给出修改建议。最后给出语言规范性总体评分（0-100）。""",

    "scoring_review": """你是一位命题评分专家，请审核以下试题的评分标准：

试题内容（含评分标准）：
{exam_content}

审核要点：
1. 评分标准是否完整覆盖所有得分点
2. 评分标准是否具有操作性（评分者能明确判断得分与否）
3. 分值分配是否合理（难易与分值匹配）
4. 客观题答案是否唯一，主观题是否有合理的参考答案范围
5. 是否有"意思对即可"等不明确表述

逐题给出评分标准审核意见，并提出修改建议。""",

    "report_generate": """你是一位资深命题审核委员，请根据以上各审核阶段的结论，出具专业的审题意见书：

试题内容：
{exam_content}

审核发现摘要：
{review_summary}

审题意见书应包含：
1. **总体评价**（一段式综合性描述）
2. **优点总结**（2-3条亮点）
3. **问题清单**（分类列出必须修改、建议修改的问题）
4. **修改建议**（优先级排序）
5. **审核结论**：✅ 通过 / ⚠️ 有条件通过（需小改） / ❌ 退回修改（有重大问题）
6. **综合评分**（科学性/规范性/难度/答案各项10分 + 总分40分）

报告以正式文档格式输出（含标题、日期等格式要素）。""",
}


class ReviewSolver:
    """
    审题执行 Agent

    按照 Review Planner 生成的任务清单逐项执行审核操作。
    """

    def __init__(self, mcp_tools: list = None, skills: list = None):
        self.llm = get_llm(temperature=0.2)
        self.mcp_tools = mcp_tools or []
        self.skills = skills or []
        self._review_results: Dict[str, str] = {}   # 跨任务结果汇总
        self._exam_content: str = ""

    def _build_prompt(self, task: dict) -> str:
        task_type = task.get("task_type", "comprehension")
        template = REVIEW_TASK_PROMPTS.get(task_type, REVIEW_TASK_PROMPTS["comprehension"])

        review_summary = "\n".join(
            f"[{k}] {v[:500]}" for k, v in self._review_results.items()
        )

        return template.format(
            exam_content=self._exam_content,
            review_summary=review_summary or "（各审核阶段结果将在执行后汇总）",
            description=task.get("description", ""),
        )

    async def execute_task(
        self,
        task: dict,
        exam_content: str,
        on_update: Optional[Callable[[dict], Awaitable[None]]] = None,
    ) -> str:
        """执行单个审题任务"""
        task_id = task["id"]
        task_type = task.get("task_type", "comprehension")
        self._exam_content = exam_content
        start_time = time.time()

        TodoService.update_task_status(task_id, "running")
        if on_update:
            await on_update({"type": "todo_task_update", "task": {**task, "status": "running"}})

        try:
            prompt = self._build_prompt(task)
            from langchain_core.messages import HumanMessage
            response = await self.llm.ainvoke([HumanMessage(content=prompt)])
            result = response.content

            # 缓存结果用于后续任务上下文
            self._review_results[task_type] = result

            elapsed_ms = int((time.time() - start_time) * 1000)
            updated = TodoService.update_task_status(task_id, "done", result=result, elapsed_ms=elapsed_ms)

            if on_update:
                await on_update({"type": "todo_task_result", "task_id": task_id, "result": result, "elapsed_ms": elapsed_ms})
                if updated:
                    await on_update({"type": "todo_task_update", "task": updated})

            return result

        except Exception as e:
            error_msg = f"审核任务执行失败: {str(e)}"
            TodoService.update_task_status(task_id, "need_revision", result=error_msg)
            if on_update:
                await on_update({"type": "todo_task_update", "task": {**task, "status": "need_revision"}})
            raise

    async def execute_group(
        self,
        group: dict,
        exam_content: str,
        on_update: Optional[Callable[[dict], Awaitable[None]]] = None,
    ) -> Dict[str, str]:
        """按顺序执行整个审题任务组"""
        self._review_results = {}
        self._exam_content = exam_content
        tasks = sorted(group.get("tasks", []), key=lambda t: t.get("order", 0))
        results = {}

        TodoService.update_group_status(group["id"], "running")

        for task in tasks:
            if task["status"] not in ("ready", "need_revision"):
                continue
            try:
                result = await self.execute_task(task, exam_content, on_update=on_update)
                results[task["id"]] = result
            except Exception:
                results[task["id"]] = ""

        TodoService.update_group_status(group["id"], "done")
        return results
