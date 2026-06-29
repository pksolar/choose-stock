"""Test scrapers end-to-end."""
import sys
sys.path.insert(0, 'backend')

import logging
logging.basicConfig(
    level=logging.INFO,
    format="%(levelname)-7s %(name)s | %(message)s",
)

import asyncio

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

from app.services.browser_manager import browser_manager
from app.services.scrapers.weibo_scraper import WeiboScraper
from app.services.scrapers.zhihu_scraper import ZhihuScraper
from app.models.models import VStar


async def test_weibo():
    await browser_manager.start()
    scraper = WeiboScraper(browser_manager)
    vstar = VStar(nickname="李大霄", platform="微博")
    print(f"Testing Weibo scraper for: {vstar.nickname}")
    articles = await scraper.scrape(vstar, days_back=30)
    print(f"Got {len(articles)} articles")
    for i, a in enumerate(articles[:5]):
        print(f"  [{i}] {a['published_at']} | {a['title'][:60]}...")
        print(f"      url: {a['url']}")
    await browser_manager.stop()


async def test_zhihu():
    await browser_manager.start()

    # Show auth state
    print(f"\nAuth state exists: {browser_manager.has_auth_state('知乎')}")

    # Check if z_c0 cookie is in auth state
    auth_state = browser_manager.load_auth_state("知乎")
    if auth_state:
        cookies = auth_state.get("cookies", [])
        has_z_c0 = any(c.get("name") == "z_c0" for c in cookies)
        print(f"Cookies in auth state: {len(cookies)}, has z_c0: {has_z_c0}")
        if not has_z_c0:
            print("WARNING: z_c0 cookie missing! Run 'python login_zhihu.py' first.")
    else:
        print("No auth state found. Run 'python login_zhihu.py' first.")

    # Try with a known real Zhihu user
    test_users = [
        "MR Dang",        # Your test user
        "张佳玮",         # Very famous, definitely exists
        "半佛仙人",       # Very famous
    ]

    scraper = ZhihuScraper(browser_manager)
    for nickname in test_users:
        print(f"\n--- Testing: {nickname} ---")
        vstar = VStar(nickname=nickname, platform="知乎")
        articles = await scraper.scrape(vstar, days_back=30)
        print(f"Got {len(articles)} articles")
        for i, a in enumerate(articles[:3]):
            print(f"  [{i}] {a['published_at']} | {a['title'][:60]}...")
            print(f"      url: {a['url']}")

    await browser_manager.stop()


if __name__ == '__main__':
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument('platform', nargs='?', default='weibo', choices=['weibo', 'zhihu'])
    p.add_argument('--user', default=None, help='Custom user nickname')
    args = p.parse_args()

    if args.platform == 'zhihu':
        if args.user:
            async def test_single():
                await browser_manager.start()
                print(f"Auth state exists: {browser_manager.has_auth_state('知乎')}")
                scraper = ZhihuScraper(browser_manager)
                vstar = VStar(nickname=args.user, platform="知乎")
                articles = await scraper.scrape(vstar, days_back=30)
                print(f"Got {len(articles)} articles for '{args.user}'")
                for i, a in enumerate(articles[:5]):
                    print(f"  [{i}] {a['published_at']} | {a['title'][:60]}")
                await browser_manager.stop()
            asyncio.run(test_single())
        else:
            asyncio.run(test_zhihu())
    else:
        asyncio.run(test_weibo())
