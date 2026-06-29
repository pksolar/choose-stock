"""Test WeiboScraper end-to-end with the datetime fix."""
import sys
sys.path.insert(0, 'backend')

import asyncio
from app.services.browser_manager import browser_manager
from app.services.scrapers.weibo_scraper import WeiboScraper
from app.models.models import VStar


async def test():
    await browser_manager.start()

    # Test 1: Search + timeline for a known real Weibo user
    scraper = WeiboScraper(browser_manager)

    # Use a well-known public figure that's guaranteed to exist on Weibo
    vstar = VStar(nickname="李大霄", platform="微博")
    print(f"Testing Weibo scraper for: {vstar.nickname}")

    articles = await scraper.scrape(vstar, days_back=30)
    print(f"Got {len(articles)} articles")

    for i, a in enumerate(articles[:5]):
        print(f"  [{i}] {a['published_at']} | {a['title'][:60]}...")
        print(f"      url: {a['url']}")

    await browser_manager.stop()


if __name__ == '__main__':
    asyncio.run(test())
