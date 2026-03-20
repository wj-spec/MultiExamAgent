"""
Browser Agent - 智能网页爬取模块

集成 browser-use 库，实现智能网页浏览、截图和多模态内容提取。
支持防爬网站访问和 DOM 节点智能解析。
"""

from utils.config import get_browser_config, get_llm_config
from langchain_core.documents import Document
import os
import sys
import logging
import asyncio
from typing import List, Optional, Dict, Any
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


logger = logging.getLogger(__name__)

# browser-use 可用性检查
try:
    from browser_use import Agent as BrowserAgentSDK
    from browser_use.browser import Browser as BrowserUseBrowser
    from browser_use.browser.context import BrowserContext as BrowserUseContext
    BROWSER_USE_AVAILABLE = True
except ImportError:
    BROWSER_USE_AVAILABLE = False
    logger.warning("browser-use 未安装，Browser Agent 功能不可用")

# Playwright 可用性检查
try:
    from playwright.async_api import async_playwright, Page, Browser
    PLAYWRIGHT_AVAILABLE = True
except ImportError:
    PLAYWRIGHT_AVAILABLE = False
    logger.warning("playwright 未安装，部分 Browser Agent 功能不可用")


class BrowserAgent:
    """
    智能网页爬取 Agent

    使用 browser-use 库实现智能网页浏览，支持：
    1. 基于 LLM 的智能页面操作
    2. 页面截图和多模态内容提取
    3. 防爬网站访问
    4. DOM 节点智能解析
    """

    def __init__(
        self,
        headless: bool = None,
        timeout: int = None,
        llm_model: str = None
    ):
        """
        初始化 Browser Agent

        Args:
            headless: 是否使用无头模式
            timeout: 超时时间 (毫秒)
            llm_model: 使用的 LLM 模型
        """
        config = get_browser_config()
        self.headless = headless if headless is not None else config.get(
            "headless", True)
        self.timeout = timeout or config.get("timeout", 30000)

        llm_config = get_llm_config()
        self.llm_model = llm_model or llm_config.get(
            "default_model", "gpt-4o-mini")

        self._browser = None
        self._context = None

    async def _init_browser(self):
        """初始化浏览器"""
        if not PLAYWRIGHT_AVAILABLE:
            raise ImportError("playwright 未安装")

        if self._browser is None:
            playwright = await async_playwright().start()
            self._browser = await playwright.chromium.launch(
                headless=self.headless,
                timeout=self.timeout
            )
        return self._browser

    async def _close_browser(self):
        """关闭浏览器"""
        if self._browser:
            await self._browser.close()
            self._browser = None

    async def browse_url_async(
        self,
        url: str,
        task: str = "提取页面的主要内容",
        use_browser_use: bool = True
    ) -> List[Document]:
        """
        异步访问 URL 并提取内容

        Args:
            url: 目标 URL
            task: 要执行的任务描述
            use_browser_use: 是否使用 browser-use 智能模式

        Returns:
            Document 列表
        """
        if use_browser_use and BROWSER_USE_AVAILABLE:
            return await self._browse_with_browser_use(url, task)
        elif PLAYWRIGHT_AVAILABLE:
            return await self._browse_with_playwright(url, task)
        else:
            logger.error("无可用的浏览器后端")
            return []

    async def _browse_with_browser_use(self, url: str, task: str) -> List[Document]:
        """使用 browser-use 进行智能浏览"""
        try:
            logger.info(f"[Browser Agent] 使用 browser-use 访问: {url}")

            from langchain_openai import ChatOpenAI
            from utils.config import get_llm

            # 初始化 LLM
            llm = get_llm(model=self.llm_model, temperature=0)

            # 创建 browser-use Agent
            agent = BrowserAgentSDK(
                task=f"访问 {url} 并执行以下任务: {task}",
                llm=llm,
            )

            # 执行任务
            result = await agent.run()

            # 提取内容
            content = str(result) if result else ""

            if content:
                doc = Document(
                    page_content=f"【来源】: {url}\n【提取时间】: {datetime.now().isoformat()}\n【内容】:\n{content}",
                    metadata={
                        "source": url,
                        "type": "browser_agent",
                        "extraction_method": "browser_use",
                        "timestamp": datetime.now().isoformat()
                    }
                )
                logger.info(
                    f"[Browser Agent] browser-use 提取完成，内容长度: {len(content)}")
                return [doc]
            return []

        except Exception as e:
            logger.error(f"[Browser Agent] browser-use 执行失败: {e}")
            # 降级到 Playwright
            if PLAYWRIGHT_AVAILABLE:
                logger.info("[Browser Agent] 降级到 Playwright 模式")
                return await self._browse_with_playwright(url, task)
            return []

    async def _browse_with_playwright(self, url: str, task: str) -> List[Document]:
        """使用 Playwright 进行基础浏览"""
        try:
            logger.info(f"[Browser Agent] 使用 Playwright 访问: {url}")

            browser = await self._init_browser()
            page = await browser.new_page()

            # 设置超时
            page.set_default_timeout(self.timeout)

            # 访问页面
            await page.goto(url, wait_until="networkidle")

            # 提取主要内容
            content = await page.content()

            # 尝试提取正文内容
            main_content = await page.evaluate("""
                () => {
                    // 尝试获取主要内容区域
                    const selectors = ['article', 'main', '.content', '.post', '.article', '#content'];
                    for (const selector of selectors) {
                        const el = document.querySelector(selector);
                        if (el) return el.innerText;
                    }
                    // 降级到 body
                    return document.body.innerText;
                }
            """)

            # 获取页面标题
            title = await page.title()

            await page.close()

            if main_content:
                doc = Document(
                    page_content=f"【标题】: {title}\n【来源】: {url}\n【提取时间】: {datetime.now().isoformat()}\n【内容】:\n{main_content}",
                    metadata={
                        "source": url,
                        "title": title,
                        "type": "browser_agent",
                        "extraction_method": "playwright",
                        "timestamp": datetime.now().isoformat()
                    }
                )
                logger.info(
                    f"[Browser Agent] Playwright 提取完成，内容长度: {len(main_content)}")
                return [doc]
            return []

        except Exception as e:
            logger.error(f"[Browser Agent] Playwright 执行失败: {e}")
            return []

    async def take_screenshot_async(self, url: str, save_path: str = None) -> Optional[str]:
        """
        异步截取页面截图

        Args:
            url: 目标 URL
            save_path: 保存路径 (可选)

        Returns:
            截图文件路径或 None
        """
        if not PLAYWRIGHT_AVAILABLE:
            logger.error("playwright 未安装，无法截图")
            return None

        try:
            logger.info(f"[Browser Agent] 正在截图: {url}")

            browser = await self._init_browser()
            page = await browser.new_page()
            page.set_default_timeout(self.timeout)

            await page.goto(url, wait_until="networkidle")

            # 生成保存路径
            if not save_path:
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                save_dir = os.path.join(os.path.dirname(
                    __file__), "..", "data", "screenshots")
                os.makedirs(save_dir, exist_ok=True)
                save_path = os.path.join(
                    save_dir, f"screenshot_{timestamp}.png")

            await page.screenshot(path=save_path, full_page=True)
            await page.close()

            logger.info(f"[Browser Agent] 截图保存到: {save_path}")
            return save_path

        except Exception as e:
            logger.error(f"[Browser Agent] 截图失败: {e}")
            return None

    async def extract_content_async(
        self,
        query: str,
        urls: List[str] = None
    ) -> List[Document]:
        """
        异步基于查询提取内容

        Args:
            query: 查询描述
            urls: 可选的目标 URL 列表

        Returns:
            Document 列表
        """
        all_docs = []

        if urls:
            for url in urls:
                docs = await self.browse_url_async(url, query)
                all_docs.extend(docs)
        else:
            logger.warning("[Browser Agent] 未提供 URL，无法提取内容")

        return all_docs

    def browse_url(self, url: str, task: str = "提取页面的主要内容") -> List[Document]:
        """
        同步访问 URL 并提取内容

        Args:
            url: 目标 URL
            task: 要执行的任务描述

        Returns:
            Document 列表
        """
        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)

        return loop.run_until_complete(self.browse_url_async(url, task))

    def take_screenshot(self, url: str, save_path: str = None) -> Optional[str]:
        """
        同步截取页面截图

        Args:
            url: 目标 URL
            save_path: 保存路径

        Returns:
            截图文件路径或 None
        """
        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)

        return loop.run_until_complete(self.take_screenshot_async(url, save_path))

    def extract_content(self, query: str, urls: List[str] = None) -> List[Document]:
        """
        同步基于查询提取内容

        Args:
            query: 查询描述
            urls: 可选的目标 URL 列表

        Returns:
            Document 列表
        """
        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)

        return loop.run_until_complete(self.extract_content_async(query, urls))


# 单例模式
_browser_agent_instance = None


def get_browser_agent() -> BrowserAgent:
    """获取 Browser Agent 实例 (单例)"""
    global _browser_agent_instance
    if _browser_agent_instance is None:
        _browser_agent_instance = BrowserAgent()
    return _browser_agent_instance


if __name__ == "__main__":
    from dotenv import load_dotenv
    load_dotenv()
    logging.basicConfig(level=logging.INFO)

    print("=" * 50)
    print("测试 Browser Agent")
    print("=" * 50)

    agent = BrowserAgent()

    # 测试 Playwright 模式
    print("\n[测试] Playwright 模式访问...")
    docs = agent.browse_url(
        "https://www.baidu.com",
        "提取页面主要内容"
    )
    if docs:
        print(f"提取成功，内容长度: {len(docs[0].page_content)}")
        print(docs[0].page_content[:500])
