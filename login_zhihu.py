"""
Manual login helper for Zhihu.
Opens a visible browser, user logs in manually, then cookies are saved.
Run this once before using the zhihu scraper.

Usage:
    python login_zhihu.py
"""
import sys
sys.path.insert(0, 'backend')

import asyncio
import json
from pathlib import Path

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

from app.services.browser_manager import browser_manager


async def main():
    auth_dir = Path("backend/data/auth_states")
    auth_dir.mkdir(parents=True, exist_ok=True)
    auth_file = auth_dir / "知乎.json"

    # Remove old auth state
    if auth_file.exists():
        auth_file.unlink()

    print("=" * 60)
    print("知乎手动登录助手")
    print("=" * 60)
    print()
    print("即将打开浏览器窗口，请手动登录知乎：")
    print("  1. 在浏览器中输入手机号/邮箱和密码")
    print("  2. 如果有验证码，手动完成验证")
    print("  3. 登录成功后（页面跳转到知乎首页），回到这里按 Enter")
    print()
    print("注意：登录成功后不要关闭浏览器，先回来按 Enter！")
    print("=" * 60)
    input("按 Enter 开始...")

    # Start browser in VISIBLE mode (override headless)
    from config import settings
    old_headless = settings.PLAYWRIGHT_HEADLESS
    settings.PLAYWRIGHT_HEADLESS = False

    await browser_manager.start()

    context = await browser_manager.create_context("知乎", load_auth=False)
    page = await context.new_page()

    # Navigate to zhihu signin page
    await page.goto("https://www.zhihu.com/signin", wait_until="domcontentloaded", timeout=30000)
    print("\n浏览器已打开知乎登录页面")
    print("请手动完成登录（包括验证码），登录成功后按 Enter...")
    input()

    # Check for z_c0 cookie
    cookies = await context.cookies()
    z_c0 = [c for c in cookies if c['name'] == 'z_c0']
    cookie_names = [c['name'] for c in cookies]

    print(f"\nCookie 总数: {len(cookies)}")
    print(f"关键 Cookie: {[n for n in cookie_names if n in ('z_c0', 'd_c0', '_zap')]}")

    if z_c0:
        # Save auth state
        state = await context.storage_state()
        auth_file.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"\n✅ 登录成功！Cookie 已保存到 {auth_file}")
        print("现在可以运行 python test_scraper.py zhihu 来测试抓取了")
    else:
        print("\n❌ 未检测到 z_c0 cookie，登录可能未完成")
        print("请确认你已成功登录知乎（页面应该跳转到知乎首页）")
        # Save anyway — d_c0 might help
        state = await context.storage_state()
        auth_file.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"已保存当前 Cookie 到 {auth_file}（不含 z_c0）")

    await context.close()
    await browser_manager.stop()

    # Restore headless setting
    settings.PLAYWRIGHT_HEADLESS = old_headless


if __name__ == '__main__':
    asyncio.run(main())
