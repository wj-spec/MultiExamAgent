"""
项目完整性测试

验证所有模块是否可以正确导入。
"""

import sys
import os

# 添加项目根目录到路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

def test_imports():
    """测试所有模块导入"""
    print("测试模块导入...")

    try:
        print("  [OK] graphs.state")
        from graphs.state import AgentState, create_initial_state
    except Exception as e:
        print(f"  [FAIL] graphs.state: {e}")
        return False

    try:
        print("  [OK] utils.memory_manager")
        from utils.memory_manager import MemoryManager, get_memory_manager
    except Exception as e:
        print(f"  [FAIL] utils.memory_manager: {e}")
        return False

    try:
        print("  [OK] tools.memory_tools")
        from tools.memory_tools import retrieve_memory, save_memory
    except Exception as e:
        print(f"  [FAIL] tools.memory_tools: {e}")
        return False

    try:
        print("  [OK] tools.retriever")
        from tools.retriever import KnowledgeBaseRetriever
    except Exception as e:
        print(f"  [FAIL] tools.retriever: {e}")
        return False

    try:
        print("  [OK] utils.prompts")
        from utils.prompts import ROUTER_PROMPT, CREATOR_PROMPT
    except Exception as e:
        print(f"  [FAIL] utils.prompts: {e}")
        return False

    try:
        print("  [OK] agents.router_agent")
        from agents.router_agent import RouterAgent, router_node
    except Exception as e:
        print(f"  [FAIL] agents.router_agent: {e}")
        return False

    try:
        print("  [OK] agents.memory_agent")
        from agents.memory_agent import MemoryCognitiveAgent, cognitive_node
    except Exception as e:
        print(f"  [FAIL] agents.memory_agent: {e}")
        return False

    try:
        print("  [OK] agents.planner_agent")
        from agents.planner_agent import PlannerAgent, planner_node
    except Exception as e:
        print(f"  [FAIL] agents.planner_agent: {e}")
        return False

    try:
        print("  [OK] agents.executor_agent")
        from agents.executor_agent import CreatorAgent, AuditorAgent
    except Exception as e:
        print(f"  [FAIL] agents.executor_agent: {e}")
        return False

    try:
        print("  [OK] agents.consolidator_agent")
        from agents.consolidator_agent import ConsolidatorAgent, consolidator_node
    except Exception as e:
        print(f"  [FAIL] agents.consolidator_agent: {e}")
        return False

    try:
        print("  [OK] graphs.workflow")
        from graphs.workflow import build_workflow, compile_workflow
    except Exception as e:
        print(f"  [FAIL] graphs.workflow: {e}")
        return False

    print("\n所有模块导入成功!")
    return True


def test_state_creation():
    """测试状态创建"""
    print("\n测试状态创建...")
    from graphs.state import create_initial_state

    state = create_initial_state("测试输入")
    print(f"  [OK] 初始状态创建成功")
    print(f"       session_id: {state['session_id']}")
    print(f"       user_input: {state['user_input']}")

    return True


def test_memory_manager():
    """测试记忆管理器"""
    print("\n测试记忆管理器...")
    from utils.memory_manager import get_memory_manager

    manager = get_memory_manager()
    stats = manager.get_statistics()
    print(f"  [OK] 记忆管理器初始化成功")
    print(f"       总记忆数: {stats['total_count']}")

    return True


def test_workflow_build():
    """测试工作流构建"""
    print("\n测试工作流构建...")
    from graphs.workflow import build_workflow

    workflow = build_workflow()
    print(f"  [OK] 工作流构建成功")

    return True


if __name__ == "__main__":
    print("=" * 50)
    print("IntelliExam-Agent 项目完整性测试")
    print("=" * 50)

    all_passed = True

    if not test_imports():
        all_passed = False

    if all_passed and not test_state_creation():
        all_passed = False

    if all_passed and not test_memory_manager():
        all_passed = False

    if all_passed and not test_workflow_build():
        all_passed = False

    print("\n" + "=" * 50)
    if all_passed:
        print("✅ 所有测试通过!")
    else:
        print("❌ 部分测试失败，请检查错误信息")
    print("=" * 50)
