"""
规划 Agent (Planner Agent)

负责将确认的需求拆解为详细的执行计划。
"""

import json
import re
from typing import Dict, Any, Optional, List
from langchain_core.language_models import BaseChatModel
from langchain_core.output_parsers import StrOutputParser
from langchain_openai import ChatOpenAI

from graphs.state import AgentState, add_status_message
from utils.prompts import PLANNER_PROMPT
from utils.config import get_llm


class PlannerAgent:
    """
    规划 Agent

    将命题需求拆解为可执行的步骤序列。
    """

    def __init__(self, llm: Optional[BaseChatModel] = None):
        """
        初始化规划 Agent

        Args:
            llm: 语言模型实例
        """
        self.llm = llm or get_llm(temperature=0)

    def _parse_plan_result(self, response: str) -> Dict[str, Any]:
        """
        解析规划结果

        Args:
            response: LLM 返回的响应

        Returns:
            解析后的结果字典
        """
        # 尝试提取 JSON
        json_match = re.search(r'\{[\s\S]*\}', response)
        if json_match:
            try:
                result = json.loads(json_match.group())
                return {
                    "plan_steps": result.get("plan_steps", []),
                    "estimated_tasks": result.get("estimated_tasks", 1)
                }
            except json.JSONDecodeError:
                pass

        # 解析失败，使用默认计划
        return {
            "plan_steps": [
                "检索业务知识库",
                "生成试题",
                "质量审核",
                "记忆沉淀"
            ],
            "estimated_tasks": 4
        }

    def create_plan(
        self,
        topic: str,
        question_type: str,
        difficulty: str,
        count: int,
        additional_requirements: str = ""
    ) -> Dict[str, Any]:
        """
        创建执行计划

        Args:
            topic: 知识点
            question_type: 题型
            difficulty: 难度
            count: 数量
            additional_requirements: 额外要求

        Returns:
            执行计划
        """
        # 构建并执行链
        chain = PLANNER_PROMPT | self.llm | StrOutputParser()

        try:
            response = chain.invoke({
                "topic": topic,
                "question_type": question_type,
                "difficulty": difficulty,
                "count": count,
                "additional_requirements": additional_requirements or "无"
            })
            return self._parse_plan_result(response)
        except Exception as e:
            print(f"规划出错: {e}")
            # 返回默认计划
            return {
                "plan_steps": [
                    "检索业务知识库",
                    "生成试题",
                    "质量审核",
                    "记忆沉淀"
                ],
                "estimated_tasks": 4
            }

    def create_simple_plan(self, count: int) -> List[str]:
        """
        创建简单的执行计划（不调用 LLM）

        Args:
            count: 试题数量

        Returns:
            计划步骤列表
        """
        base_steps = [
            "检索业务知识库",
            f"生成 {count} 道试题",
            "质量审核",
            "记忆沉淀"
        ]
        return base_steps


def planner_node(state: AgentState) -> AgentState:
    """
    规划节点

    根据已确认的需求参数创建执行计划。

    Args:
        state: 当前状态

    Returns:
        更新后的状态
    """
    new_state = add_status_message(state, "📝 正在规划任务...")

    # 获取需求参数
    params = state["extracted_params"]

    # 创建规划 Agent
    agent = PlannerAgent()

    # 创建执行计划
    plan = agent.create_plan(
        topic=params.get("topic", ""),
        question_type=params.get("question_type", ""),
        difficulty=params.get("difficulty", ""),
        count=params.get("count", 1),
        additional_requirements=params.get("additional_requirements", "")
    )

    # 更新状态
    new_state = dict(new_state)
    new_state["plan_steps"] = plan["plan_steps"]
    new_state["current_step_index"] = 0
    new_state["next_node"] = "executor"

    # 添加状态消息
    steps_str = " -> ".join(plan["plan_steps"])
    new_state = add_status_message(new_state, f"📋 执行计划: {steps_str}")

    return new_state
