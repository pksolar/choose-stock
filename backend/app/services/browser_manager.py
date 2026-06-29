"""
Playwright browser lifecycle manager.
Singleton that maintains one long-lived Chromium instance shared across all platform scrapers.
Supports persistent authentication via storageState (cookies, localStorage, etc.).
"""
import asyncio
import json
import logging
import random
from pathlib import Path
from typing import Optional, Dict

from playwright.async_api import async_playwright, Browser, BrowserContext, Page

from config import settings

logger = logging.getLogger(__name__)

_STEALTH_PATH = Path(__file__).resolve().parent / "stealth.min.js"

# Auth state persistence directory
_AUTH_DIR = Path(settings.PLAYWRIGHT_AUTH_DIR)


class BrowserManager:
    """Singleton manager for Playwright browser lifecycle."""

    def __init__(self):
        self._playwright = None
        self._browser: Optional[Browser] = None
        self._stealth_js: Optional[str] = None
        self._loop: Optional[asyncio.AbstractEventLoop] = None

    async def start(self):
        """Launch browser with anti-detection flags."""
        self._loop = asyncio.get_running_loop()
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

    # ------------------------------------------------------------------
    # Auth state persistence
    # ------------------------------------------------------------------

    def _auth_file(self, platform: str) -> Path:
        """Get the auth state file path for a platform."""
        _AUTH_DIR.mkdir(parents=True, exist_ok=True)
        safe = platform.replace("/", "_").replace("\\", "_")
        return _AUTH_DIR / f"{safe}.json"

    def has_auth_state(self, platform: str) -> bool:
        return self._auth_file(platform).exists()

    async def save_auth_state(self, context: BrowserContext, platform: str):
        """Persist browser context cookies + storage to disk."""
        auth_path = self._auth_file(platform)
        try:
            state = await context.storage_state()
            auth_path.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
            logger.info("Auth state saved for %s (%d bytes)", platform, auth_path.stat().st_size)
        except Exception as e:
            logger.error("Failed to save auth state for %s: %s", platform, e)

    def load_auth_state(self, platform: str) -> Optional[dict]:
        """Load persisted auth state, or None if unavailable."""
        auth_path = self._auth_file(platform)
        if not auth_path.exists():
            return None
        try:
            state = json.loads(auth_path.read_text(encoding="utf-8"))
            # Validate structure: must have cookies or origins
            if "cookies" in state or "origins" in state:
                logger.info("Auth state loaded for %s (%d cookies)", platform,
                            len(state.get("cookies", [])))
                return state
        except (json.JSONDecodeError, IOError) as e:
            logger.warning("Corrupted auth state for %s: %s", platform, e)
        return None

    # ------------------------------------------------------------------
    # Context factory
    # ------------------------------------------------------------------

    async def create_context(self, platform: str = "default",
                             load_auth: bool = True) -> BrowserContext:
        """Create a fresh browser context with anti-detection.

        If load_auth is True and a persisted auth state exists, it is loaded
        into the context so the session starts pre-authenticated.
        """
        viewports = {
            "weibo": {"width": 390, "height": 844},
            "wechat": {"width": 390, "height": 844},
            "知乎": {"width": 1280, "height": 800},
            "zhihu": {"width": 1280, "height": 800},
        }
        vp = viewports.get(platform, {"width": 1280, "height": 800})
        is_mobile = platform in ("weibo", "wechat")

        storage_state = None
        if load_auth:
            storage_state = self.load_auth_state(platform)

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
            storage_state=storage_state,
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
            pass
        return page

    # ------------------------------------------------------------------
    # Platform login helpers
    # ------------------------------------------------------------------

    async def login_zhihu(self, username: str, password: str) -> bool:
        """Log into Zhihu and persist auth state. Returns True on success."""
        # Remove stale auth state first
        auth_file = self._auth_file("知乎")
        if auth_file.exists():
            auth_file.unlink()

        context = await self.create_context("知乎", load_auth=False)
        try:
            page = await context.new_page()

            # Navigate to signin page
            await page.goto("https://www.zhihu.com/signin",
                            wait_until="networkidle", timeout=45000)
            await page.wait_for_timeout(3000)

            # Check if already on signin page or redirected
            current_url = page.url
            logger.info("Zhihu login: current URL = %s", current_url)

            # If we're not on signin page, maybe already logged in? Check.
            if "signin" not in current_url:
                cookies = await context.cookies()
                z_c0 = [c for c in cookies if c['name'] == 'z_c0']
                if z_c0:
                    logger.info("Already logged in (z_c0 present)")
                    await self.save_auth_state(context, "知乎")
                    await context.close()
                    return True

            # 1. Switch to password login tab
            switch_selectors = [
                "text=密码登录",
                "text=密码登入",
                "text=使用密码登录",
                "div[class*='SignFlow-tab']:has-text('密码')",
                "div[class*='signFlow'] a:has-text('密码')",
                ".SignFlow-tab:not(.SignFlow-tab--active)",
            ]
            switched = False
            for sel in switch_selectors:
                try:
                    btn = page.locator(sel).first
                    if await btn.count() > 0:
                        await btn.click()
                        await page.wait_for_timeout(1500)
                        switched = True
                        logger.info("Zhihu login: switched to password tab via '%s'", sel)
                        break
                except Exception:
                    continue

            if not switched:
                logger.info("Zhihu login: no tab switch needed or found")

            # 2. Fill phone/email
            phone_selectors = [
                "input[name='username']",
                "input[name='phoneNo']",
                "input[type='text']",
                ".SignFlow-account input",
                "input[placeholder*='手机']",
                "input[placeholder*='邮箱']",
            ]
            filled_phone = False
            for sel in phone_selectors:
                try:
                    inp = page.locator(sel).first
                    if await inp.count() > 0 and await inp.is_visible():
                        await inp.click()
                        await page.wait_for_timeout(300)
                        await inp.fill(username)
                        await page.wait_for_timeout(800)
                        filled_phone = True
                        logger.info("Zhihu login: filled phone via '%s'", sel)
                        break
                except Exception:
                    continue

            if not filled_phone:
                logger.error("Zhihu login: could not find phone input")
                await context.close()
                return False

            # 3. Fill password
            pwd_selectors = [
                "input[name='password']",
                "input[type='password']",
                ".SignFlow-password input",
                "input[placeholder*='密码']",
            ]
            filled_pwd = False
            for sel in pwd_selectors:
                try:
                    inp = page.locator(sel).first
                    if await inp.count() > 0 and await inp.is_visible():
                        await inp.click()
                        await page.wait_for_timeout(300)
                        await inp.fill(password)
                        await page.wait_for_timeout(800)
                        filled_pwd = True
                        logger.info("Zhihu login: filled password via '%s'", sel)
                        break
                except Exception:
                    continue

            if not filled_pwd:
                logger.error("Zhihu login: could not find password input")
                await context.close()
                return False

            # 4. Submit login
            submit_selectors = [
                "button[type='submit']",
                "button:has-text('登录')",
                "button:has-text('登 录')",
                ".SignFlow-submitButton",
                "button[class*='SignFlow-submit']",
                "button[class*='submit']",
            ]
            clicked = False
            for sel in submit_selectors:
                try:
                    btn = page.locator(sel).first
                    if await btn.count() > 0 and await btn.is_visible():
                        await btn.click()
                        clicked = True
                        logger.info("Zhihu login: clicked submit via '%s'", sel)
                        break
                except Exception:
                    continue

            if not clicked:
                # Try pressing Enter as fallback
                await page.keyboard.press("Enter")
                logger.info("Zhihu login: pressed Enter as fallback")

            # 5. Wait for login result
            await page.wait_for_timeout(5000)

            # Check for CAPTCHA
            page_text = await page.evaluate("() => document.body.innerText")
            if "验证码" in page_text or "请完成安全验证" in page_text:
                logger.warning("Zhihu login: CAPTCHA detected — manual intervention needed")

            # 6. Verify login by checking for z_c0 cookie
            cookies = await context.cookies()
            z_c0 = [c for c in cookies if c['name'] == 'z_c0']
            cookie_names = [c['name'] for c in cookies]

            logger.info("Zhihu login: cookies after attempt: %s", cookie_names)

            if z_c0:
                logger.info("Zhihu login successful (z_c0=%s...)", z_c0[0]['value'][:20])
                await self.save_auth_state(context, "知乎")
                await context.close()
                return True
            else:
                logger.warning("Zhihu login failed: no z_c0 cookie. Captcha or wrong credentials?")
                # Still save cookies (d_c0 etc. may help)
                await self.save_auth_state(context, "知乎")
                await context.close()
                return False

        except Exception as e:
            logger.error("Zhihu login error: %s", e)
            await context.close()
            return False

    async def login_weibo(self, username: str, password: str) -> bool:
        """Log into Weibo (m.weibo.cn) and persist auth state."""
        context = await self.create_context("weibo", load_auth=False)
        try:
            page = await context.new_page()

            await page.goto("https://passport.weibo.cn/signin/login",
                            wait_until="domcontentloaded", timeout=30000)
            await page.wait_for_timeout(random.randint(2000, 3000))

            try:
                phone_input = page.locator("input#loginName, input[name='username']").first
                await phone_input.fill(username)
                await page.wait_for_timeout(random.randint(500, 1000))

                pwd_input = page.locator("input#loginPassword, input[type='password']").first
                await pwd_input.fill(password)
                await page.wait_for_timeout(random.randint(500, 1000))

                submit_btn = page.locator("a#loginAction, button[type='submit']").first
                await submit_btn.click()
            except Exception as e:
                logger.error("Weibo form fill failed: %s", e)
                await context.close()
                return False

            await page.wait_for_timeout(5000)

            # Check if we arrived at m.weibo.cn (logged in)
            current_url = page.url
            if "passport" not in current_url:
                await self.save_auth_state(context, "weibo")
                logger.info("Weibo login successful for %s", username)
                await context.close()
                return True
            else:
                logger.warning("Weibo login may have failed — still on passport page")
                await self.save_auth_state(context, "weibo")
                await context.close()
                return False

        except Exception as e:
            logger.error("Weibo login failed: %s", e)
            await context.close()
            return False

    async def login_xueqiu(self, username: str, password: str) -> bool:
        """Log into Xueqiu and persist auth state."""
        context = await self.create_context("雪球", load_auth=False)
        try:
            page = await context.new_page()

            await page.goto("https://xueqiu.com/", wait_until="domcontentloaded", timeout=30000)
            await page.wait_for_timeout(random.randint(2000, 3000))

            # Click login button on homepage
            try:
                login_btn = page.locator("a:has-text('登录'), button:has-text('登录')").first
                if await login_btn.count() > 0:
                    await login_btn.click()
                    await page.wait_for_timeout(2000)
            except Exception:
                pass

            try:
                phone_input = page.locator("input[placeholder*='手机'], input[placeholder*='邮箱'], "
                                           "input[name='username']").first
                await phone_input.fill(username)
                await page.wait_for_timeout(random.randint(500, 1000))

                pwd_input = page.locator("input[type='password']").first
                await pwd_input.fill(password)
                await page.wait_for_timeout(random.randint(500, 1000))

                submit_btn = page.locator("button:has-text('登录'), button[type='submit']").first
                await submit_btn.click()
            except Exception as e:
                logger.error("Xueqiu form fill failed: %s", e)
                await context.close()
                return False

            await page.wait_for_timeout(5000)

            # Check login success
            logged_in = await page.evaluate("""() => {
                return !document.querySelector('a[href*="login"]');
            }""")

            if logged_in:
                await self.save_auth_state(context, "雪球")
                logger.info("Xueqiu login successful for %s", username)
                await context.close()
                return True
            else:
                await self.save_auth_state(context, "雪球")
                await context.close()
                return False

        except Exception as e:
            logger.error("Xueqiu login failed: %s", e)
            await context.close()
            return False

    # ------------------------------------------------------------------
    # Auto-login orchestration
    # ------------------------------------------------------------------

    async def ensure_authenticated(self, platform: str) -> bool:
        """Try to ensure we have valid auth for a platform.

        Returns True if auth state already exists OR if creds were found
        and login succeeded. Returns False if no credentials are configured.
        """
        if self.has_auth_state(platform):
            logger.info("Auth state already exists for %s", platform)
            return True

        # Check config for credentials
        cred_map = {
            "知乎": (settings.ZHIHU_USERNAME, settings.ZHIHU_PASSWORD),
            "weibo": (settings.WEIBO_USERNAME, settings.WEIBO_PASSWORD),
            "微博": (settings.WEIBO_USERNAME, settings.WEIBO_PASSWORD),
            "雪球": (settings.XUEQIU_USERNAME, settings.XUEQIU_PASSWORD),
        }

        username, password = cred_map.get(platform, ("", ""))
        if not username or not password:
            # Also check DB
            try:
                from app.models.database import SessionLocal
                from app.models.models import PlatformCredential
                db = SessionLocal()
                try:
                    cred = db.query(PlatformCredential).filter(
                        PlatformCredential.platform == platform,
                        PlatformCredential.is_active.is_(True),
                    ).first()
                    if cred and cred.username and cred.password:
                        username, password = cred.username, cred.password
                finally:
                    db.close()
            except Exception:
                pass

        if not username or not password:
            logger.info("No credentials configured for %s", platform)
            return False

        # Attempt login
        login_handlers = {
            "知乎": self.login_zhihu,
            "weibo": self.login_weibo,
            "微博": self.login_weibo,
            "雪球": self.login_xueqiu,
        }
        handler = login_handlers.get(platform)
        if not handler:
            logger.info("No login handler for %s", platform)
            return False

        logger.info("Attempting login for %s with user %s", platform, username)
        return await handler(username, password)

    @property
    def is_ready(self) -> bool:
        return self._browser is not None and self._browser.is_connected()


browser_manager = BrowserManager()
