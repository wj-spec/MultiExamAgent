"""
启动脚本 (main.py)

提供命令行入口来运行 IntelliExam-Agent 服务。
前端：自定义 HTML/CSS/JS + FastAPI + WebSocket（已替换旧 Chainlit 方案）
"""

import argparse
import sys
import os

# 添加项目根目录到路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def run_server(host: str = "0.0.0.0", port: int = 8000, reload: bool = True):
    """启动 FastAPI + WebSocket 服务（推荐）"""
    import uvicorn
    print("🚀 IntelliExam-Agent 启动中...")
    print(f"📍 访问地址: http://localhost:{port}")
    print("📖 按 Ctrl+C 停止服务\n")
    uvicorn.run(
        "server:app",
        host=host,
        port=port,
        reload=reload,
        log_level="info"
    )


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
  python main.py web          # 启动 FastAPI 服务（默认，推荐）
  python main.py web --port 9000        # 指定端口
  python main.py web --no-reload        # 生产模式（不自动重载）
  python main.py cli          # 命令行交互模式

直接启动（等价于 python main.py web）:
  uvicorn server:app --host 0.0.0.0 --port 8000 --reload
        """
    )
    subparsers = parser.add_subparsers(dest="command")

    # web 子命令
    web_parser = subparsers.add_parser("web", help="启动 FastAPI Web 服务（推荐）")
    web_parser.add_argument("--host", default="0.0.0.0", help="监听地址（默认 0.0.0.0）")
    web_parser.add_argument("--port", type=int, default=8000, help="端口号（默认 8000）")
    web_parser.add_argument("--no-reload", dest="reload", action="store_false",
                            default=True, help="关闭自动重载（生产环境）")

    # cli 子命令
    subparsers.add_parser("cli", help="命令行交互模式")

    args = parser.parse_args()

    if args.command == "web" or args.command is None:
        host = getattr(args, "host", "0.0.0.0")
        port = getattr(args, "port", 8000)
        reload = getattr(args, "reload", True)
        run_server(host=host, port=port, reload=reload)
    elif args.command == "cli":
        run_cli()
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
