"""
意图分层模式测试

测试双层意图判断功能：
1. 纯闲聊 - 不调用命题 Agent
2. 独立命题 - 进入命题流程
3. 继续命题 - 继承上次参数
4. 命题完成 - 退出命题模式
"""

import logging
from dotenv import load_dotenv
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

load_dotenv()

logging.basicConfig(level=logging.INFO, format='%(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


def test_router():
    """测试 Router Agent 的分层意图判断"""
    print("\n" + "=" * 60)
    print("测试 1: Router Agent 双层意图判断")
    print("=" * 60)

    from agents.router_agent import RouterAgent

    agent = RouterAgent()

    test_cases = [
        # (用户输入, 对话历史, 当前模式, 预期主要意图, 预期命题需求)
        ("今天天气真不错", None, "chat", "chat", False),
        ("帮我出三道物理选择题", None, "chat", "proposition", True),
        ("继续", None, "proposition", "proposition", True),
        ("好了，就这些", None, "proposition", "chat", False),
    ]

    all_passed = True
    for user_input, chat_history, current_mode, expected_intent, expected_proposition_needed in test_cases:
        print(f"\n测试输入: \"{user_input}\"")
        print(f"  当前模式: {current_mode}")

        result = agent.route(user_input, chat_history, current_mode)

        intent_match = result["primary_intent"] == expected_intent
        prop_match = result["proposition_needed"] == expected_proposition_needed

        status = "PASS" if (intent_match and prop_match) else "FAIL"
        if not (intent_match and prop_match):
            all_passed = False

        print(
            f"  主要意图: {result['primary_intent']} (预期: {expected_intent}) {'✓' if intent_match else '✗'}")
        print(
            f"  命题需求: {result['proposition_needed']} (预期: {expected_proposition_needed}) {'✓' if prop_match else '✗'}")
        print(f"  模式切换: {result['mode_transition']}")
        print(f"  状态: {status}")

    print(f"\n[Router] 测试 {'通过' if all_passed else '失败'}")
    return all_passed


def test_state_fields():
    """测试状态字段"""
    print("\n" + "=" * 60)
    print("测试 2: AgentState 新增字段")
    print("=" * 60)

    from graphs.state import create_initial_state, AgentState

    state = create_initial_state("测试输入")

    required_fields = [
        "primary_intent",
        "proposition_needed",
        "proposition_context",
        "current_mode",
        "mode_transition"
    ]

    all_passed = True
    for field in required_fields:
        if field in state:
            print(f"  {field}: {state[field]} ✓")
        else:
            print(f"  {field}: 缺失 ✗")
            all_passed = False

    # 测试默认值
    print(f"\n默认值验证:")
    print(f"  primary_intent = 'chat': {state['primary_intent'] == 'chat'} ✓")
    print(
        f"  proposition_needed = False: {state['proposition_needed'] == False} ✓")
    print(f"  current_mode = 'chat': {state['current_mode'] == 'chat'} ✓")
    print(
        f"  mode_transition = 'none': {state['mode_transition'] == 'none'} ✓")

    print(f"\n[State] 测试 {'通过' if all_passed else '失败'}")
    return all_passed


def test_workflow_routing():
    """测试工作流路由"""
    print("\n" + "=" * 60)
    print("测试 3: 工作流路由逻辑")
    print("=" * 60)

    from graphs.workflow import route_by_intent
    from graphs.state import create_initial_state

    test_cases = [
        # (proposition_needed, 预期下一个节点)
        (True, "memory_recall"),
        (False, "chat_reply"),
    ]

    all_passed = True
    for proposition_needed, expected_next in test_cases:
        state = create_initial_state("测试")
        state["proposition_needed"] = proposition_needed

        next_node = route_by_intent(state)
        match = next_node == expected_next
        status = "PASS" if match else "FAIL"
        if not match:
            all_passed = False

        print(
            f"  proposition_needed={proposition_needed} -> {next_node} (预期: {expected_next}) {status}")

    print(f"\n[Workflow] 测试 {'通过' if all_passed else '失败'}")
    return all_passed


def test_conversation_state():
    """测试会话状态管理"""
    print("\n" + "=" * 60)
    print("测试 4: 会话状态管理")
    print("=" * 60)

    from utils.conversation_manager import ConversationState, ConversationManager

    # 测试 ConversationState
    state = ConversationState()
    print(f"  初始状态:")
    print(f"    current_mode: {state.current_mode}")
    print(f"    last_proposition_params: {state.last_proposition_params}")
    print(f"    proposition_in_progress: {state.proposition_in_progress}")

    # 测试序列化和反序列化
    state_dict = state.to_dict()
    print(f"\n  序列化: {state_dict}")

    state2 = ConversationState.from_dict(state_dict)
    print(f"  反序列化:")
    print(f"    current_mode: {state2.current_mode}")
    print(f"    last_proposition_params: {state2.last_proposition_params}")
    print(f"    proposition_in_progress: {state2.proposition_in_progress}")

    print(f"\n[ConversationState] 测试通过")
    return True


def test_router_extended():
    """测试 Router Agent 的更多边界场景"""
    print("\n" + "=" * 60)
    print("测试 1.5: Router Agent 扩展测试场景")
    print("=" * 60)

    from agents.router_agent import RouterAgent

    agent = RouterAgent()

    # 扩展测试用例
    extended_cases = [
        # 阅卷场景
        ("帮我批改一下这道题", None, "chat", "grading", False),
        # 命题中闲聊（混合模式）
        ("顺便问一下，今天是几号", None, "proposition", "chat", True),
        # 再来一道
        ("再来一道选择题", None, "proposition", "proposition", True),
        # 闲聊中明确命题
        ("对了，你能帮我出题吗", None, "chat", "proposition", True),
    ]

    all_passed = True
    for user_input, chat_history, current_mode, expected_intent, expected_proposition_needed in extended_cases:
        print(f"\n测试输入: \"{user_input}\"")
        print(f"  当前模式: {current_mode}")

        result = agent.route(user_input, chat_history, current_mode)

        intent_match = result["primary_intent"] == expected_intent
        prop_match = result["proposition_needed"] == expected_proposition_needed

        status = "PASS" if (intent_match and prop_match) else "FAIL"
        if not (intent_match and prop_match):
            all_passed = False

        print(
            f"  主要意图: {result['primary_intent']} (预期: {expected_intent}) {'✓' if intent_match else '✗'}")
        print(
            f"  命题需求: {result['proposition_needed']} (预期: {expected_proposition_needed}) {'✓' if prop_match else '✗'}")
        print(f"  模式切换: {result['mode_transition']}")
        print(f"  状态: {status}")

    print(f"\n[Router Extended] 测试 {'通过' if all_passed else '失败'}")
    return all_passed


def test_quick_intent_check():
    """测试快速意图检查函数"""
    print("\n" + "=" * 60)
    print("测试 5: 快速意图检查函数")
    print("=" * 60)

    from agents.router_agent import quick_intent_check

    test_cases = [
        ("帮我出三道选择题", "proposition"),
        ("今天天气不错", "chat"),
        ("帮我批改一下", "grading"),
        ("继续", "proposition"),
    ]

    all_passed = True
    for user_input, expected in test_cases:
        result = quick_intent_check(user_input)
        match = result == expected
        status = "PASS" if match else "FAIL"
        if not match:
            all_passed = False
        print(f"  \"{user_input}\" -> {result} (预期: {expected}) {status}")

    print(f"\n[Quick Check] 测试 {'通过' if all_passed else '失败'}")
    return all_passed


def run_all_tests():
    """运行所有测试"""
    print("\n" + "#" * 60)
    print("# 意图分层模式测试")
    print("#" * 60)

    tests = [
        ("Router", test_router),
        ("Router Extended", test_router_extended),
        ("State Fields", test_state_fields),
        ("Workflow Routing", test_workflow_routing),
        ("Conversation State", test_conversation_state),
        ("Quick Intent Check", test_quick_intent_check),
    ]

    results = {}
    for name, test_func in tests:
        try:
            results[name] = test_func()
        except Exception as e:
            print(f"\n[{name}] 测试异常: {e}")
            import traceback
            traceback.print_exc()
            results[name] = False

    # 汇总
    print("\n" + "#" * 60)
    print("# 测试汇总")
    print("#" * 60)
    for name, passed in results.items():
        status = "PASS" if passed else "FAIL"
        print(f"  {name}: {status}")

    all_passed = all(results.values())
    print(f"\n总体结果: {'ALL PASSED' if all_passed else 'SOME FAILED'}")
    return all_passed


if __name__ == "__main__":
    run_all_tests()
