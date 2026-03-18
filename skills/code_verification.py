"""
代码验证技能 (Code Verification Skill)

为理科 (数学/物理) 试题生成 Python 验证代码并在安全沙箱中执行，
确保试题的答案和选项都是正确的。

安全措施：
- 使用受限的内置函数白名单
- 禁止 import（除 math 以外）
- 限制执行时间（5秒超时）
- 限制输出长度
"""

import io
import sys
import math
import signal
import traceback
import threading
from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field
from langchain_core.tools import BaseTool


# ==================== 安全沙箱 ====================

# 白名单内置函数
SAFE_BUILTINS = {
    "abs": abs,
    "all": all,
    "any": any,
    "bin": bin,
    "bool": bool,
    "chr": chr,
    "complex": complex,
    "dict": dict,
    "divmod": divmod,
    "enumerate": enumerate,
    "filter": filter,
    "float": float,
    "format": format,
    "frozenset": frozenset,
    "hex": hex,
    "int": int,
    "isinstance": isinstance,
    "issubclass": issubclass,
    "len": len,
    "list": list,
    "map": map,
    "max": max,
    "min": min,
    "oct": oct,
    "ord": ord,
    "pow": pow,
    "print": print,
    "range": range,
    "repr": repr,
    "reversed": reversed,
    "round": round,
    "set": set,
    "slice": slice,
    "sorted": sorted,
    "str": str,
    "sum": sum,
    "tuple": tuple,
    "type": type,
    "zip": zip,
    # 数学常量
    "True": True,
    "False": False,
    "None": None,
}

# 预导入的安全模块
SAFE_MODULES = {
    "math": math,
}

# 执行超时秒数
EXECUTION_TIMEOUT = 5

# 最大输出长度
MAX_OUTPUT_LENGTH = 2000


class SandboxResult:
    """沙箱执行结果"""
    def __init__(self, success: bool, output: str, error: str = ""):
        self.success = success
        self.output = output
        self.error = error


def execute_in_sandbox(code: str) -> SandboxResult:
    """
    在安全沙箱中执行 Python 代码

    安全措施:
    - 只允许白名单内置函数
    - 只能使用 math 模块
    - 5秒超时
    - 输出长度限制

    Args:
        code: 要执行的 Python 代码

    Returns:
        SandboxResult 执行结果
    """
    # 检查危险关键字
    dangerous_patterns = [
        "__import__", "exec(", "eval(", "compile(",
        "os.", "sys.", "subprocess", "open(",
        "file(", "input(", "breakpoint", "__class__",
        "__subclasses__", "__bases__", "__globals__",
        "getattr", "setattr", "delattr",
    ]
    code_lower = code.lower()
    for pattern in dangerous_patterns:
        if pattern.lower() in code_lower:
            return SandboxResult(
                success=False,
                output="",
                error=f"安全限制：代码包含禁止的操作 '{pattern}'"
            )

    # 构建受限的全局命名空间
    restricted_globals = {
        "__builtins__": SAFE_BUILTINS,
    }
    # 添加安全模块
    restricted_globals.update(SAFE_MODULES)

    # 本地命名空间
    restricted_locals = {}

    # 捕获 stdout
    old_stdout = sys.stdout
    captured_output = io.StringIO()

    result = {"done": False, "output": "", "error": ""}

    def _run():
        try:
            sys.stdout = captured_output
            exec(code, restricted_globals, restricted_locals)
            output = captured_output.getvalue()
            if len(output) > MAX_OUTPUT_LENGTH:
                output = output[:MAX_OUTPUT_LENGTH] + "\n... [输出被截断]"
            result["output"] = output
            result["done"] = True
        except Exception as e:
            result["error"] = f"{type(e).__name__}: {str(e)}"
            result["done"] = True
        finally:
            sys.stdout = old_stdout

    # 在线程中执行（带超时）
    thread = threading.Thread(target=_run, daemon=True)
    thread.start()
    thread.join(timeout=EXECUTION_TIMEOUT)

    if not result["done"]:
        return SandboxResult(
            success=False,
            output="",
            error=f"执行超时（>{EXECUTION_TIMEOUT}秒），代码可能包含无限循环"
        )

    if result["error"]:
        return SandboxResult(
            success=False,
            output=result["output"],
            error=result["error"]
        )

    return SandboxResult(
        success=True,
        output=result["output"],
        error=""
    )


# ==================== LangChain Tool ====================

class VerifyAnswerInput(BaseModel):
    """代码验证工具的输入参数"""
    code: str = Field(
        description=(
            "用于验证试题答案的 Python 代码。"
            "代码应该计算正确答案并打印结果。"
            "只能使用 math 模块和基础内置函数。"
            "禁止使用 import、open、exec 等危险操作。"
        )
    )
    question_context: str = Field(
        default="",
        description="相关试题的上下文描述（可选）"
    )


class VerifyAnswerTool(BaseTool):
    """
    代码验证工具

    在安全沙箱中执行 Python 代码来验证试题答案。
    适用于理科（数学/物理/化学）试题的数值验证。
    """

    name: str = "verify_answer_with_code"
    description: str = (
        "在安全沙箱中执行 Python 代码来验证试题答案的正确性。"
        "用于理科试题的数值计算验证。"
        "沙箱只允许使用 math 模块和基础内置函数（abs, max, min, round, 等）。"
        "代码应该计算正确答案并用 print() 输出结果。"
        "禁止使用 import（math 已预导入）、open、exec 等操作。"
    )
    args_schema: type = VerifyAnswerInput

    def _run(self, code: str, question_context: str = "") -> str:
        """执行代码验证"""
        result = execute_in_sandbox(code)

        if result.success:
            response = f"✅ 代码执行成功\n"
            if result.output:
                response += f"输出结果:\n{result.output}"
            else:
                response += "（无输出）"
        else:
            response = f"❌ 代码执行失败\n"
            if result.error:
                response += f"错误信息: {result.error}\n"
            if result.output:
                response += f"部分输出: {result.output}"

        return response


# ==================== Skill 定义 ====================

CODE_VERIFICATION_PROMPT = """
## 代码验证技能

你拥有一个 **Python 代码验证工具** (verify_answer_with_code)。

当你审核数学、物理或化学等理科试题时，你**必须**：

1. 根据题目条件，编写一段 Python 代码来独立计算正确答案
2. 使用 `verify_answer_with_code` 工具执行代码
3. 将代码执行结果与题目给出的答案/选项进行对比
4. 如果发现答案不一致，在审核反馈中明确指出

**代码编写规则**：
- math 模块已预导入，直接使用 `math.sqrt()`, `math.pi` 等
- 使用 `print()` 输出计算结果
- 不能使用 import（math 除外）
- 不能使用 open、exec、eval 等危险函数

**示例**：
```python
# 验证：一个球从 10m 高自由落体，落地速度是多少？
g = 9.8  # 重力加速度
h = 10   # 高度
v = math.sqrt(2 * g * h)
print(f"落地速度: {v:.2f} m/s")
# 预期答案: 14.00 m/s
```
""".strip()


def get_code_verification_skill():
    """获取代码验证技能定义"""
    from skills.registry import Skill

    return Skill(
        id="code_verification",
        name="代码验证",
        description="为理科试题生成 Python 验证代码并在安全沙箱中执行，确保答案和选项的正确性",
        category="validation",
        enabled=False,  # 默认未启用
        prompt_template=CODE_VERIFICATION_PROMPT,
        tool_module="skills.code_verification",
        tool_function="get_tools",
        bind_to=["auditor"],
        version="1.0.0",
        author="IntelliExam"
    )


def get_tools() -> list:
    """获取代码验证技能的工具列表（由 SkillRegistry 动态调用）"""
    return [VerifyAnswerTool()]
