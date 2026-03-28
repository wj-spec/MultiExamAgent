"""
Extraction Agent (agents/proposition/extraction_agent.py)
职责：在试卷审核确认后，提取 Markdown 中的题目并转换为结构化的试题库 JSON 数据。
"""
import json
from typing import List, Dict, Any
from utils.config import get_llm

EXTRACTION_PROMPT = """你是一个专业的教育数据结构化专家。
请将下面这份已经过最终审核的试卷内容（Markdown 格式），逐题解析为规范的 JSON 试题对象。

试题内容：
{exam_content}

你需要提取：
1. 题干 (content)
2. 试题类型 (type: 选择题/填空题/解答题)
3. 选项 (options: 仅选择题需要)
4. 解析/答案 (answer)
5. 难度系数预估 (difficulty)

请返回一个 JSON 数组，每个元素如：
[
  {
    "id": "generate_uuid",
    "content": "求函数 f(x) = x^2 的导数",
    "type": "解答题",
    "options": [],
    "answer": "f'(x) = 2x",
    "difficulty": 0.3
  }
]
直接输出 JSON 数组，不要输出 markdown 代码块或任何其他文本。
"""

class ExtractionAgent:
    """提取智能体，用于将最终试卷拆并沉淀到题库。"""

    def __init__(self):
        self.llm = get_llm(temperature=0.1)
    
    async def extract_and_save(self, exam_content: str, session_id: str) -> List[Dict[str, Any]]:
        """执行结构化提取并模拟存入数据库"""
        try:
            prompt = EXTRACTION_PROMPT.format(exam_content=exam_content)
            from langchain_core.messages import HumanMessage
            response = await self.llm.ainvoke([HumanMessage(content=prompt)])
            
            raw_result = response.content.strip()
            if raw_result.startswith("```"):
                lines = raw_result.split("\n")
                raw_result = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])
            
            questions = json.loads(raw_result)
            
            # 这里原本会调用 db.save_questions(questions)。
            # 由于当前以 JSON 演示，我们将打印日志并在未来替换为 SQLite QuestionBank 存储。
            print(f"[Extraction Agent] 成功沉淀了 {len(questions)} 道题目至题库！(Session: {session_id})")
            
            # Example: appending to a local JSON file to simulate DB persistence
            import os
            bank_file = "data/memory/question_bank.json"
            os.makedirs("data/memory", exist_ok=True)
            existing = []
            if os.path.exists(bank_file):
                with open(bank_file, 'r', encoding='utf-8') as f:
                    try:
                        existing = json.load(f)
                    except:
                        pass
            existing.extend(questions)
            with open(bank_file, 'w', encoding='utf-8') as f:
                json.dump(existing, f, ensure_ascii=False, indent=2)
                
            return questions
        except Exception as e:
            print(f"[Extraction Agent] 提取试题失败: {str(e)}")
            return []
