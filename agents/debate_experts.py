import json
from typing import List, Dict, Any, Tuple
from utils.config import get_llm

class DomainExpert:
    """学科专家：负责审查知识点、计算逻辑、科学性"""
    
    def __init__(self):
        self.llm = get_llm(temperature=0.2)
        
    def review(self, questions: List[dict], topic: str) -> str:
        prompt = f"""你是严谨的学科专家。请审查以下生成的关于【{topic}】的试题。
你的任务是**仅**从科学性、知识点准确性、计算逻辑角度找错。
如果发现错误，请明确指出错误在哪一题、是什么具体错误。
如果完全没有知识性错误，请回复："未发现学科知识错误。"

试题内容：
{json.dumps(questions, ensure_ascii=False, indent=2)}
"""
        response = self.llm.invoke(prompt)
        return response.content


class FormatExaminer:
    """格式考官：负责审查格式、排版、选项规范"""
    
    def __init__(self):
        self.llm = get_llm(temperature=0.1)
        
    def review(self, questions: List[dict]) -> str:
        prompt = f"""你是严格的试卷格式审查官。请审查以下生成的试题。
你的任务是**仅**从排版规范、Markdown 格式、选项编排（如 ABCD 顺序、是否存在明显格式崩坏）角度找错。
如果发现格式错误，请明确指出。
如果没有格式错误，请回复："未发现格式排版错误。"

试题内容：
{json.dumps(questions, ensure_ascii=False, indent=2)}
"""
        response = self.llm.invoke(prompt)
        return response.content


class MetaReviewer:
    """主理人：汇总专家意见，决定是否通过，并给出最终修改建议"""
    
    def __init__(self):
        self.llm = get_llm(temperature=0.1)
        
    def conclude(self, questions: List[dict], domain_feedback: str, format_feedback: str) -> Tuple[bool, str]:
        prompt = f"""你是命题专家组的主理人。
你收到了学科专家和格式考官对同一批试题的反馈意见。
你需要综合这两份报告，决定试题是否达标。

【学科专家意见】：
{domain_feedback}

【格式考官意见】：
{format_feedback}

请判断：
1. 如果双方都认为没有错误（如"未发现..."），则结论为通过。
2. 如果有任何一方指出明确错误，则结论为不通过，并综合归纳出需要 Creator 修改的清晰指令。

请以 JSON 格式输出评估结果，必须包含 "passed" (布尔值) 和 "feedback" (字符串)。
示例：{{"passed": false, "feedback": "第2题选项排版错误，且知识点缺少..."}}
"""
        response = self.llm.invoke(prompt)
        content = response.content.strip()
        
        # 简单解析 JSON (预防大模型带 markdown tag)
        if content.startswith("```json"):
            content = content[7:]
        if content.endswith("```"):
            content = content[:-3]
            
        try:
            result = json.loads(content.strip())
            return result.get("passed", False), result.get("feedback", "解析评价结果失败。")
        except:
            # Fallback
            passed = "未发现" in domain_feedback and "未发现" in format_feedback
            return passed, f"综合意见：学科反馈({domain_feedback})；格式反馈({format_feedback})"
