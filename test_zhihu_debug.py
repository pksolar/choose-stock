"""Step-by-step debug for Zhihu scraper."""
import sys
sys.path.insert(0, 'backend')

import asyncio

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

from app.services.browser_manager import browser_manager
from config import settings


async def debug():
    print("=" * 60)
    print("1. Check config")
    print(f"   ZHIHU_USERNAME: {settings.ZHIHU_USERNAME}")
    print(f"   ZHIHU_PASSWORD: {'***' if settings.ZHIHU_PASSWORD else 'EMPTY'}")
    print(f"   Has auth state: {browser_manager.has_auth_state('知乎')}")

    print("\n2. Starting browser...")
    await browser_manager.start()

    print("\n3. Attempting login...")
    result = await browser_manager.ensure_authenticated("知乎")
    print(f"   ensure_authenticated result: {result}")
    print(f"   Has auth state now: {browser_manager.has_auth_state('知乎')}")

    print("\n4. Creating context with auth...")
    context = await browser_manager.create_context("知乎")
    page = await context.new_page()

    print("\n5. Visiting zhihu.com...")
    await page.goto("https://www.zhihu.com/explore",
                    wait_until="domcontentloaded", timeout=30000)
    await page.wait_for_timeout(3000)

    # Check login state
    current_url = page.url
    print(f"   Current URL: {current_url}")

    # Check if logged in
    is_logged_in = await page.evaluate("""() => {
        const signinBtn = document.querySelector('a[href="/signin"]');
        const userMenu = document.querySelector('.AppHeader-profile');
        return !signinBtn || !!userMenu;
    }""")
    print(f"   Appears logged in: {is_logged_in}")

    # Check cookies
    cookies = await context.cookies()
    print(f"   Cookie count: {len(cookies)}")
    for c in cookies:
        if c['name'] in ('d_c0', 'z_c0', '_zap', 'zst_81', 'zse_ck'):
            print(f"     {c['name']}: {c['value'][:30]}...")

    print("\n6. Testing search API...")
    # Try a known real user: 半佛仙人, 张佳玮
    test_users = ["半佛仙人", "张佳玮", "李开复", "MR Dang"]
    for user in test_users:
        result = await page.evaluate("""
            async (q) => {
                const url = 'https://www.zhihu.com/api/v4/search_v3?t=people&q='
                    + encodeURIComponent(q) + '&limit=5&offset=0';
                try {
                    const resp = await fetch(url, {
                        headers: {
                            'Accept': 'application/json',
                            'x-requested-with': 'fetch',
                            'Referer': 'https://www.zhihu.com/',
                        }
                    });
                    if (!resp.ok) return {status: resp.status, statusText: resp.statusText};
                    const data = await resp.json();
                    if (data.data && data.data.length > 0) {
                        const first = data.data[0].object || {};
                        return {found: true, name: first.name, url_token: first.url_token, count: data.data.length};
                    }
                    return {found: false, count: data.paging?.totals || 0};
                } catch(e) {
                    return {error: e.message};
                }
            }
        """, user)
        print(f"   Search '{user}': {result}")

    print("\n7. Cleanup")
    await context.close()
    await browser_manager.stop()


if __name__ == '__main__':
    asyncio.run(debug())
