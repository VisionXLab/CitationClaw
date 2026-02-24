import asyncio
from playwright.async_api import async_playwright, Browser, Page
from typing import Optional, Callable


class BrowserController:
    def __init__(self, on_url_captured: Callable[[str], None]):
        """
        浏览器控制器,用于自动化打开浏览器并监听URL

        Args:
            on_url_captured: URL捕获回调函数,当检测到cites=参数时调用
        """
        self.playwright = None
        self.browser: Optional[Browser] = None
        self.page: Optional[Page] = None
        self.on_url_captured = on_url_captured
        self.is_monitoring = False

    async def start(self):
        """启动浏览器并导航到Google Scholar"""
        try:
            # 启动Playwright
            self.playwright = await async_playwright().start()

            # 启动浏览器(非无头模式,用户可见)
            self.browser = await self.playwright.chromium.launch(
                headless=False,
                args=[
                    '--start-maximized',  # 最大化窗口
                    '--disable-blink-features=AutomationControlled'  # 隐藏自动化特征
                ]
            )

            # 创建浏览器上下文
            context = await self.browser.new_context(
                viewport=None,  # 使用全屏
                locale='zh-CN',
                user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
            )

            # 创建新页面
            self.page = await context.new_page()

            # 导航到Google Scholar
            await self.page.goto('https://scholar.google.com.hk/')

            # 启动URL监听
            self.is_monitoring = True
            asyncio.create_task(self._monitor_url())

            return True
        except Exception as e:
            print(f"浏览器启动失败: {e}")
            return False

    async def _monitor_url(self):
        """
        监听URL变化,检测cites=参数

        采用轮询策略,每秒检查一次当前URL
        """
        while self.is_monitoring and self.page:
            try:
                # 获取当前URL
                current_url = self.page.url

                # 检测cites=参数
                if 'cites=' in current_url and 'scholar.google' in current_url:
                    print(f"检测到引用列表URL: {current_url}")

                    # 停止监听
                    self.is_monitoring = False

                    # 调用回调函数
                    await self.on_url_captured(current_url)

                    # 关闭浏览器
                    await self.stop()
                    break

                # 等待1秒后继续检查
                await asyncio.sleep(1)

            except Exception as e:
                print(f"URL监听错误: {e}")
                break

    async def stop(self):
        """关闭浏览器"""
        try:
            self.is_monitoring = False

            if self.page:
                await self.page.close()
                self.page = None

            if self.browser:
                await self.browser.close()
                self.browser = None

            if self.playwright:
                await self.playwright.stop()
                self.playwright = None

            print("浏览器已关闭")
        except Exception as e:
            print(f"关闭浏览器时出错: {e}")

    async def is_running(self) -> bool:
        """检查浏览器是否正在运行"""
        return self.browser is not None and self.is_monitoring
