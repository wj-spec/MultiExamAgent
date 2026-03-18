"""
启动脚本

提供简单的命令行入口来运行和测试项目。
支持 Chainlit 和 Streamlit 两种前端模式。
"""

import argparse
import sys
import os

# 添加项目根目录到路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def run_chainlit():
    """启动 Chainlit 应用（推荐）"""
    import subprocess
    print("🚀 启动 Chainlit 服务...")
    print("📍 访问地址: http://localhost:8000")
    print("📖 按 Ctrl+C 停止服务\n")
    subprocess.run([
        sys.executable, "-m", "chainlit", "run", "app.py",
        "-w",  # 自动重载
        "--port", "8000"
    ])


def run_streamlit():
    """启动 Streamlit 应用（备选）"""
    import subprocess
    print("🚀 启动 Streamlit 服务...")
    print("📍 访问地址: http://localhost:8501")
    print("📖 按 Ctrl+C 停止服务\n")
    subprocess.run([
        sys.executable, "-m", "streamlit", "run", "app_streamlit.py",
        "--server.port", "8501",
        "--server.address", "localhost"
    ])




def run_cli():
    """运行命令行交互模式"""
    print("=" * 50)
    print("IntelliExam-Agent 命令行模式")
    print("=" * 50)
    print("输入 'quit' 或 'exit' 退出\n")

    from graphs.workflow import run_workflow
    from graphs.state import create_initial_state

    chat_history = []

    while True:
        try:
            user_input = input("\n用户: ").strip()
            if not user_input:
                continue
            if user_input.lower() in ['quit', 'exit', '退出']:
                print("再见!")
                break

            print("\n助手: ", end="")
            result = run_workflow(user_input, chat_history=chat_history)

            # 显示状态消息
            for msg in result.get("status_messages", []):
                print(f"  [{msg}]")

            print(f"\n{result.get('final_response', '抱歉，无法处理您的请求。')}")

            # 更新对话历史
            chat_history.append({"role": "user", "content": user_input})
            chat_history.append(
                {"role": "assistant", "content": result.get("final_response", "")})

        except KeyboardInterrupt:
            print("\n\n再见!")
            break
        except Exception as e:
            print(f"\n错误: {e}")


def main():
    """主函数"""
    parser = argparse.ArgumentParser(
        description="IntelliExam-Agent 启动脚本",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  python main.py web        # 启动 Chainlit 前端（推荐）
  python main.py streamlit  # 启动 Streamlit 前端（备选）
  python main.py cli        # 命令行交互模式
  python main.py test       # 运行测试
        """
    )
    parser.add_argument(
        "command",
        choices=["web", "streamlit", "cli"],
        help="运行模式: web=Chainlit界面(推荐), streamlit=Streamlit界面, cli=命令行模式"
    )

    args = parser.parse_args()

    if args.command == "web":
        run_chainlit()
    elif args.command == "streamlit":
        run_streamlit()
    elif args.command == "cli":
        run_cli()


if __name__ == "__main__":
    main()
