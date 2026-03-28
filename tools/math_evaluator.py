"""
数学交互与验证工具包 (tools/math_evaluator.py)
用于理科审题与命题时的科学性公式推导与计算验证。
"""
import math
import cmath

class MathEvaluatorTool:
    """提供沙箱化的 Python 数学评估验证能力，帮助 LLM 验证理科题目。"""

    def __init__(self):
        # 允许使用的安全环境上下文
        self.safe_env = {
            "math": math,
            "cmath": cmath,
            "abs": abs,
            "min": min,
            "max": max,
            "pow": pow,
            "round": round,
            "sum": sum,
        }

    def evaluate_expression(self, expression: str) -> str:
        """
        验证单个数学表达式的结果。
        使用场景：核实答案计算是否正确。
        """
        try:
            # 过滤危险关键字
            forbidden = ["__", "import", "exec", "eval", "open", "sys", "os"]
            if any(word in expression for word in forbidden):
                return "Error: 不允许的表达式语句。"

            # 使用有限的上下文执行 eval
            result = eval(expression, {"__builtins__": None}, self.safe_env)
            return f"Result: {result}"
        except Exception as e:
            return f"Evaluation Error: {str(e)}"

    def execute_python_code(self, code: str) -> str:
        """
        在安全环境中执行 Python 代码并返回 output 字典中的最终变量。
        用于通过复杂推导验证物理、数学应用题。
        示例:
        ```
        v0 = 10
        a = -9.8
        t = 2
        s = v0*t + 0.5*a*t**2
        output['s'] = s
        ```
        """
        try:
            forbidden = ["import", "exec", "open", "sys", "os"]
            if any(word in code for word in forbidden):
                return "Error: 包含不安全指令。"

            local_vars = {"output": {}}
            exec(code, {"__builtins__": None, "math": math}, local_vars)
            
            return f"Success: {local_vars.get('output', {})}"
        except Exception as e:
            return f"Execution Error: {str(e)}"
