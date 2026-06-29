"""
EastMoney (东方财富) / TongHuaShun (同花顺) scraper using Playwright.
Uses browser cookies to call EastMoney Guba APIs via page.evaluate().
"""
import hashlib
import logging
import random
from datetime import datetime, timedelta, timezone
from typing import List, Dict, Optional

from app.models.models import VStar
from app.services.scrapers.base import AbstractScraper
from app.services.scrapers import register_scraper
from app.services.browser_manager import BrowserManager

logger = logging.getLogger(__name__)


@register_scraper("东方财富")
class EastmoneyScraper(AbstractScraper):
    """Scrape EastMoney Guba user posts via browser-authenticated API calls."""

    platform_name = "东方财富"

    async def scrape(self, vstar: VStar, days_back: int = 30) -> List[Dict]:
        articles = []
        nickname = vstar.nickname

        context = await self._bm.create_context("default")
        try:
            page = await context.new_page()

            # Step 1: Visit guba.eastmoney.com to get cookies
            await page.goto("https://guba.eastmoney.com/", wait_until="domcontentloaded", timeout=30000)
            await page.wait_for_timeout(random.randint(2000, 4000))

            # Step 2: Search for user
            user_id = await self._search_user(page, nickname)
            if not user_id:
                logger.warning("EastMoney user not found: %s", nickname)
                return articles

            await page.wait_for_timeout(random.randint(500, 1500))

            # Step 3: Fetch user posts
            articles = await self._fetch_posts(page, user_id, nickname, days_back)

        except Exception as e:
            logger.error("EastMoney scraper failed for %s: %s", nickname, e)
        else:
            await self._bm.save_auth_state(context, "东方财富")
        finally:
            await context.close()

        return articles

    async def _search_user(self, page, nickname: str) -> Optional[str]:
        """Search EastMoney for user ID."""
        try:
            result = await page.evaluate("""
                async (q) => {
                    const url = 'https://searchapi.eastmoney.com/bussiness/Web/GetCMSSearchResult';
                    const params = new URLSearchParams({
                        type: '8196',
                        pageindex: '1',
                        pagesize: '10',
                        keyword: q,
                        name: 'zixun',
                    });
                    try {
                        const resp = await fetch(url + '?' + params.toString(), {
                            headers: {
                                'Accept': 'application/json',
                                'Referer': 'https://guba.eastmoney.com/',
                            }
                        });
                        if (!resp.ok) return null;
                        const data = await resp.json();
                        if (!data.IsSuccess || !data.Data) return null;

                        // Data might be string JSON
                        const items = typeof data.Data === 'string'
                            ? JSON.parse(data.Data)
                            : data.Data;

                        for (const item of items) {
                            const author = item.author || item.userName || item.Title || '';
                            if (author === q || author.includes(q)) {
                                return String(item.authorUserId || item.UserId || item.user_id || '');
                            }
                        }
                    } catch(e) {
                        return null;
                    }
                    return null;
                }
            """, nickname)
            return result
        except Exception as e:
            logger.debug("EastMoney search failed: %s", e)
            return None

    async def _fetch_posts(self, page, user_id: str, nickname: str, days_back: int) -> List[Dict]:
        """Fetch user posts from EastMoney Guba API."""
        articles = []
        now = datetime.now(timezone.utc)
        cutoff = now - timedelta(days=days_back)

        try:
            for pagenum in range(1, 4):
                result = await page.evaluate("""
                    async ({uid, page}) => {
                        const url = 'https://guba.eastmoney.com/interface/GetData.aspx';
                        const params = new URLSearchParams({
                            path: 'api/UserPost/GetUserPostList',
                            userId: uid,
                            pageIndex: String(page),
                            pageSize: '20',
                        });
                        try {
                            const resp = await fetch(url + '?' + params.toString(), {
                                headers: {
                                    'Accept': 'application/json',
                                    'Referer': 'https://guba.eastmoney.com/',
                                }
                            });
                            if (!resp.ok) return null;
                            return await resp.json();
                        } catch(e) {
                            return null;
                        }
                    }
                """, {"uid": user_id, "page": pagenum})

                if not result:
                    break

                posts = result.get("Data", []) if isinstance(result, dict) else []
                if not posts:
                    break

                for post in posts:
                    try:
                        pub_time_str = (
                            post.get("PostDateTime") or
                            post.get("publishDate") or ""
                        )
                        pub_time = None
                        if pub_time_str:
                            for fmt in ["%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S",
                                        "%Y/%m/%d %H:%M:%S"]:
                                try:
                                    pub_time = datetime.strptime(pub_time_str, fmt)
                                    break
                                except ValueError:
                                    continue
                        if not pub_time:
                            pub_time = now

                        if pub_time < cutoff:
                            continue

                        title = post.get("Title") or post.get("title") or ""
                        content = (
                            post.get("Content") or
                            post.get("content") or
                            post.get("Body") or ""
                        )
                        post_id = (
                            post.get("Id") or post.get("id") or
                            post.get("PostId") or ""
                        )
                        stock_code = (
                            post.get("StockCode") or
                            post.get("stockCode") or ""
                        )

                        if not content:
                            continue

                        url = (
                            f"https://guba.eastmoney.com/news,{stock_code},{post_id}.html"
                            if stock_code else "https://guba.eastmoney.com/"
                        )

                        articles.append({
                            "title": title or content[:80],
                            "content": content[:5000],
                            "summary": content[:200],
                            "url": url,
                            "platform": "东方财富",
                            "published_at": pub_time,
                            "source_hash": hashlib.md5(
                                f"{title}|{content[:500]}".encode("utf-8")
                            ).hexdigest(),
                        })

                        if len(articles) >= 20:
                            break

                    except Exception as e:
                        logger.debug("Parse EastMoney post failed: %s", e)
                        continue

                if len(articles) >= 20:
                    break

                await page.wait_for_timeout(random.randint(500, 1500))

        except Exception as e:
            logger.debug("EastMoney posts fetch failed: %s", e)

        return articles


# Also register for 同花顺 (same scraper, different platform name)
@register_scraper("同花顺")
class TonghuashunScraper(EastmoneyScraper):
    """Same as EastmoneyScraper since the API is similar."""
    platform_name = "同花顺"
