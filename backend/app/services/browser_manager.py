"""
Playwright browser lifecycle manager.
Singleton that maintains one long-lived Chromium instance shared across all platform scrapers.
"""
import logging
from pathlib import Path
from typing import Optional

from playwright.async_api import async_playwright, Browser, BrowserContext, Page

from config import settings

logger = logging.getLogger(__name__)

_STEALTH_PATH = Path(__file__).resolve().parent / "stealth.min.js"


class BrowserManager:
    """Singleton manager for Playwright browser lifecycle."""

    def __init__(self):
        self._playwright = None
        self._browser: Optional[Browser] = None
        self._stealth_js: Optional[str] = None

    async def start(self):
        """Launch browser with anti-detection flags."""
        self._playwright = await async_playwright().start()

        launch_args = [
            "--disable-blink-features=AutomationControlled",
            "--disable-features=IsolateOrigins,site-per-process",
            "--no-sandbox",
            "--disable-setuid-sandbox",
            "--disable-infobars",
            "--disable-dev-shm-usage",
            "--disable-web-security",
            "--disable-features=TranslateUI",
            "--disable-ipc-flooding-protection",
        ]

        self._browser = await self._playwright.chromium.launch(
            headless=settings.PLAYWRIGHT_HEADLESS,
            args=launch_args,
        )

        if _STEALTH_PATH.exists():
            self._stealth_js = _STEALTH_PATH.read_text(encoding="utf-8")
        else:
            logger.warning("stealth.min.js not found, anti-detection disabled")

        logger.info("Playwright browser started (headless=%s)", settings.PLAYWRIGHT_HEADLESS)

    async def stop(self):
        """Close browser and stop Playwright."""
        if self._browser:
            await self._browser.close()
        if self._playwright:
            await self._playwright.stop()
        logger.info("Playwright browser stopped")

    async def create_context(self, platform: str = "default") -> BrowserContext:
        """Create a fresh browser context with anti-detection enabled."""
        viewports = {
            "weibo": {"width": 390, "height": 844},   # mobile
            "wechat": {"width": 390, "height": 844},  # mobile
        }
        vp = viewports.get(platform, {"width": 1280, "height": 800})
        is_mobile = platform in ("weibo", "wechat")

        context = await self._browser.new_context(
            viewport=vp,
            locale="zh-CN",
            timezone_id="Asia/Shanghai",
            user_agent=(
                "Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) "
                "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.0 "
                "Mobile/15E148 Safari/604.1"
                if is_mobile else
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
        )

        if self._stealth_js:
            await context.add_init_script(self._stealth_js)

        return context

    async def new_page(self, context: BrowserContext, url: str) -> Page:
        """Navigate to URL with timeout, injecting stealth.js."""
        page = await context.new_page()
        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=settings.PLAYWRIGHT_TIMEOUT)
        except Exception:
            # Some pages never fire domcontentloaded; continue anyway
            pass
        return page

    @property
    def is_ready(self) -> bool:
        return self._browser is not None and self._browser.is_connected()


browser_manager = BrowserManager()
