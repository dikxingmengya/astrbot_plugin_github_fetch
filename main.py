import asyncio
import os
import re
import tempfile
import time
from pathlib import Path

from playwright.async_api import async_playwright
from astrbot.api.event import filter, AstrMessageEvent, MessageEventResult
from astrbot.api.star import Context, Star, register
from astrbot.api import logger

# ---------------------------------------------------------------------------
# Regex patterns
# ---------------------------------------------------------------------------

# 匹配 GitHub 仓库页面 URL（仓库首页、Issue、PR、文件、目录、提交、Release 等）
GITHUB_URL_PATTERN = (
    r"https?://github\.com/"
    r"[a-zA-Z0-9](?:[a-zA-Z0-9\-]*[a-zA-Z0-9])?"  # owner (GitHub 用户名规则)
    r"/"
    r"[a-zA-Z0-9_.\-]+"                              # repo name
    r"(?:/[^\s]*)?"                                   # optional path
)

# 匹配 #xxxxx 格式的 issue/PR 引用
# 负向后顾 (?<!\w) 避免匹配 foo#12345
# \b 避免匹配 #12345abc
# 1-7 位数字（GitHub 目前 issue 编号上限约 7 位）
ISSUE_REF_PATTERN = r"(?<!\w)#(\d{1,7})\b"

# 每条消息最多处理的 URL 数量
MAX_URLS_PER_MESSAGE = 3

# 临时文件清理延迟（秒），确保 AstrBot 框架完成图片发送
CLEANUP_DELAY = 120.0

# ---------------------------------------------------------------------------
# Plugin class
# ---------------------------------------------------------------------------


@register(
    "astrbot_plugin_github_fetch",
    "a8568",
    "自动捕获 GitHub 页面截图。识别消息中的 GitHub 链接和 #issue 编号。",
    "1.0.0",
)
class GitHubFetchPlugin(Star):
    """AstrBot 插件：自动识别 GitHub 链接并返回页面截图。

    功能：
    1. 消息中包含 GitHub URL → 自动截图返回
    2. 消息中包含 #xxxxx → 在默认仓库中查找 Issue/PR 并截图返回
    """

    def __init__(self, context: Context):
        super().__init__(context)
        self._cleanup_tasks: list[asyncio.Task] = []

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _get_config(self) -> dict:
        """获取插件配置，未配置时返回空字典。"""
        cfg = self.context.get_config()
        return cfg if cfg else {}

    def _build_issue_url(self, issue_num: str) -> str:
        """根据 #issue 编号和 default_repo 配置构造 GitHub Issue URL。

        注意：GitHub 会自动将 /issues/N 重定向到 /pull/N（如果 N 是 PR），
        因此统一使用 /issues/ 路径即可同时支持 Issue 和 PR。
        """
        repo = self._get_config().get("default_repo", "").strip()
        if not repo:
            raise ValueError("default_repo 未在插件配置中设置")
        if "/" not in repo or repo.count("/") != 1:
            raise ValueError(
                f"default_repo 格式无效: '{repo}'。需要 owner/repo 格式。"
            )
        repo = repo.rstrip("/")
        return f"https://github.com/{repo}/issues/{issue_num}"

    async def _take_screenshot(self, url: str) -> str:
        """使用 Playwright 对指定 URL 进行截图，返回截图文件路径。

        Args:
            url: 目标 GitHub 页面 URL。

        Returns:
            截图文件的绝对路径。

        Raises:
            RuntimeError: Playwright 或 Chromium 未安装。
            各种 Playwright 异常: 页面加载失败、超时等。
        """
        config = self._get_config()
        full_page = config.get("screenshot_full_page", True)
        timeout = config.get("timeout", 30000)
        token = config.get("github_token", "")

        # 强制升级到 HTTPS
        if url.startswith("http://"):
            url = "https://" + url[7:]

        # 临时文件：系统临时目录 + 唯一文件名
        temp_dir = Path(tempfile.gettempdir())
        safe_hash = abs(hash(url))
        timestamp = int(time.time() * 1000)
        filename = f"github_screenshot_{safe_hash}_{timestamp}.png"
        filepath = str(temp_dir / filename)

        async with async_playwright() as p:
            browser = await p.chromium.launch(
                headless=True,
                args=[
                    "--disable-gpu",
                    "--no-sandbox",            # Docker/容器环境需要
                    "--disable-setuid-sandbox",
                    "--disable-dev-shm-usage",  # 避免 /dev/shm 空间不足
                ],
            )

            # 浏览器上下文配置
            context_kwargs: dict = {
                "viewport": {"width": 1280, "height": 720},
                "user_agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/120.0.0.0 Safari/537.36"
                ),
            }

            # 如果配置了 GitHub Token，通过 HTTP Header 注入认证
            if token:
                context_kwargs["extra_http_headers"] = {
                    "Authorization": f"Bearer {token}"
                }

            context = await browser.new_context(**context_kwargs)
            page = await context.new_page()

            try:
                # domcontentloaded: HTML 解析完成即可，不等待 WebSocket（GitHub 有长连接）
                await page.goto(
                    url, wait_until="domcontentloaded", timeout=timeout
                )
                # 额外等待 2 秒让图片、代码高亮等异步内容加载
                await page.wait_for_timeout(2000)
                await page.screenshot(path=filepath, full_page=full_page)
                return filepath
            except Exception:
                # 截图失败时清理可能已创建的空文件
                if os.path.exists(filepath):
                    os.remove(filepath)
                raise
            finally:
                await context.close()
                await browser.close()

    def _schedule_cleanup(self, filepath: str, delay: float = CLEANUP_DELAY):
        """安排延迟删除临时截图文件。

        使用 asyncio.create_task 在后台延迟删除文件，确保 AstrBot 框架
        完成图片的读取和发送后再清理。

        Args:
            filepath: 要删除的文件路径。
            delay: 延迟秒数，默认 120 秒。
        """

        async def _delayed_remove():
            await asyncio.sleep(delay)
            try:
                if os.path.exists(filepath):
                    os.remove(filepath)
                    logger.debug(f"[GitHubFetch] 已清理临时文件: {filepath}")
            except Exception as e:
                logger.warning(f"[GitHubFetch] 清理文件失败 {filepath}: {e}")

        task = asyncio.create_task(_delayed_remove())
        self._cleanup_tasks.append(task)
        # 清理已完成的任务，防止列表无限增长
        self._cleanup_tasks = [t for t in self._cleanup_tasks if not t.done()]

    # ------------------------------------------------------------------
    # Message handlers
    # ------------------------------------------------------------------

    @filter.regex(GITHUB_URL_PATTERN)
    async def on_github_url(self, event: AstrMessageEvent):
        """处理包含 GitHub URL 的消息，截图并返回。"""
        config = self._get_config()
        if not config.get("enable_url_fetch", True):
            return

        urls = re.findall(GITHUB_URL_PATTERN, event.message_str)
        if not urls:
            return

        # 限制每次消息处理的 URL 数量
        urls = urls[:MAX_URLS_PER_MESSAGE]

        for url in urls:
            if url.startswith("http://"):
                url = "https://" + url[7:]

            logger.info(f"[GitHubFetch] 正在截图: {url}")
            yield event.plain_result(f"🔍 正在截图 GitHub 页面...\n{url}")

            try:
                filepath = await self._take_screenshot(url)
                yield event.image_result(filepath)
                self._schedule_cleanup(filepath)
            except Exception as e:
                logger.error(f"[GitHubFetch] 截图失败 {url}: {e}")
                # 检查是否为常见安装问题
                hint = ""
                err_msg = str(e)
                if "Executable doesn't exist" in err_msg:
                    hint = "\n💡 提示: 请运行 `playwright install chromium` 安装浏览器。"
                elif "No module named 'playwright'" in err_msg:
                    hint = "\n💡 提示: 请运行 `pip install playwright` 安装依赖。"
                yield event.plain_result(
                    f"❌ 截图失败\n{url}\n错误: {type(e).__name__}: {err_msg}{hint}"
                )

    @filter.regex(ISSUE_REF_PATTERN)
    async def on_issue_ref(self, event: AstrMessageEvent):
        """处理包含 #xxxxx 的消息，在默认仓库中查找并截图。"""
        config = self._get_config()
        if not config.get("enable_issue_fetch", True):
            return

        default_repo = config.get("default_repo", "").strip()
        if not default_repo:
            return

        # 互斥处理：如果消息中已包含完整 GitHub URL，交给 URL handler 处理，
        # 避免对同一 issue 重复截图（如粘贴了完整 issue URL 的情况）
        if re.search(GITHUB_URL_PATTERN, event.message_str):
            return

        matches = re.findall(ISSUE_REF_PATTERN, event.message_str)
        if not matches:
            return

        # 去重：用户可能在一条消息中重复提及同一个 issue
        seen: set[str] = set()
        for issue_num in matches:
            if issue_num in seen:
                continue
            seen.add(issue_num)

            try:
                url = self._build_issue_url(issue_num)
            except ValueError as e:
                logger.warning(f"[GitHubFetch] 无法构造 URL: {e}")
                yield event.plain_result(
                    f"❌ 无法查询 #{issue_num}：{e}\n"
                    f"请在插件配置中设置正确的 default_repo（格式: owner/repo）"
                )
                continue

            logger.info(f"[GitHubFetch] Issue 引用 #{issue_num} -> {url}")
            yield event.plain_result(
                f"🔍 正在获取 {default_repo}#{issue_num} 的截图..."
            )

            try:
                filepath = await self._take_screenshot(url)
                yield event.image_result(filepath)
                self._schedule_cleanup(filepath)
            except Exception as e:
                logger.error(f"[GitHubFetch] 截图失败 #{issue_num}: {e}")
                err_msg = str(e)
                hint = ""
                if "Executable doesn't exist" in err_msg:
                    hint = "\n💡 提示: 请运行 `playwright install chromium` 安装浏览器。"
                elif "No module named 'playwright'" in err_msg:
                    hint = "\n💡 提示: 请运行 `pip install playwright` 安装依赖。"
                yield event.plain_result(
                    f"❌ 获取 {default_repo}#{issue_num} 失败\n"
                    f"错误: {type(e).__name__}: {err_msg}{hint}"
                )

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def initialize(self):
        """插件初始化：验证 Playwright 依赖是否已安装。"""
        try:
            from playwright.async_api import async_playwright  # noqa: F401
            logger.info("[GitHubFetch] Playwright 导入成功，插件已就绪。")
        except ImportError:
            logger.warning(
                "[GitHubFetch] ⚠ Playwright 未安装！"
                "请运行: pip install playwright && playwright install chromium"
            )

    async def terminate(self):
        """插件卸载：取消所有待清理任务。"""
        for task in self._cleanup_tasks:
            task.cancel()
        count = len(self._cleanup_tasks)
        self._cleanup_tasks.clear()
        logger.info(f"[GitHubFetch] 插件已卸载，已取消 {count} 个待清理任务。")
