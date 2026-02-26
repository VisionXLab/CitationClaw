"""
论文被引画像智能体 - 启动脚本

运行此脚本启动Web应用:
    python start.py

然后访问: http://127.0.0.1:8000
"""

import asyncio
import webbrowser
import sys
from pathlib import Path

# 确保项目根目录在Python路径中
sys.path.insert(0, str(Path(__file__).parent))

try:
    import uvicorn
    from app.main import app
except ImportError as e:
    print("=" * 60)
    print("错误: 缺少依赖包!")
    print("=" * 60)
    print(f"详细信息: {e}")
    print("\n请先安装依赖:")
    print("  pip install -r requirements.txt")
    print("=" * 60)
    sys.exit(1)


def print_banner():
    """打印启动横幅"""
    banner = """
    ╔══════════════════════════════════════════════════════════╗
    ║                                                          ║
    ║                 论文被引画像智能体                       ║
    ║        v2.0 - 基于 FastAPI + ScraperAPI                   ║
    ║                                                          ║
    ╚══════════════════════════════════════════════════════════╝
    """
    print(banner)
    print("启动服务器中...")
    print("服务器地址: http://127.0.0.1:8000")
    print("=" * 60)


async def open_browser_delayed():
    """延迟1.5秒后打开浏览器"""
    await asyncio.sleep(1.5)
    try:
        webbrowser.open("http://127.0.0.1:8000")
        print("\n浏览器已自动打开!")
        print("如果浏览器没有自动打开,请手动访问: http://127.0.0.1:8000")
    except Exception as e:
        print(f"\n无法自动打开浏览器: {e}")
        print("请手动访问: http://127.0.0.1:8000")


def main():
    """主函数"""
    print_banner()

    # 检查必要的目录是否存在
    required_dirs = ['app', 'core', 'static', 'templates', 'data']
    missing_dirs = [d for d in required_dirs if not Path(d).exists()]

    if missing_dirs:
        print("\n警告: 以下目录缺失:")
        for d in missing_dirs:
            print(f"  - {d}/")
        print("\n请确保项目结构完整!")
        sys.exit(1)

    # 创建后台任务打开浏览器
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.create_task(open_browser_delayed())

    # 启动FastAPI服务器
    try:
        uvicorn.run(
            app,
            host="127.0.0.1",
            port=8000,
            log_level="info",
            access_log=True
        )
    except KeyboardInterrupt:
        print("\n\n服务器已停止")
        print("感谢使用!")
    except Exception as e:
        print(f"\n错误: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
