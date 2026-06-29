"""
Xueqiu (雪球) scraper using Playwright.
Uses browser cookies to call Xueqiu JSON APIs via page.evaluate().
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


@register_scraper("雪球")
class XueqiuScraper(AbstractScraper):
    """Scrape Xueqiu user timeline via browser-authenticated API calls."""

    platform_name = "雪球"

    async def scrape(self, vstar: VStar, days_back: int = 30) -> List[Dict]:
        articles = []
        nickname = vstar.nickname

        context = await self._bm.create_context("default")
        try:
            page = await context.new_page()

            # Step 1: Visit xueqiu.com to get cookies
            await page.goto("https://xueqiu.com/", wait_until="domcontentloaded", timeout=30000)
            await page.wait_for_timeout(random.randint(2000, 4000))

            # Step 2: Search for user
            user_id = await self._search_user(page, nickname)
            if not user_id:
                logger.warning("Xueqiu user not found: %s", nickname)
                return articles

            await page.wait_for_timeout(random.randint(500, 1500))

            # Step 3: Fetch user timeline
            articles = await self._fetch_timeline(page, user_id, nickname, days_back)

        except Exception as e:
            logger.error("Xueqiu scraper failed for %s: %s", nickname, e)
        finally:
            await context.close()

        return articles

    async def _search_user(self, page, nickname: str) -> Optional[str]:
        """Search Xueqiu for user ID."""
        try:
            result = await page.evaluate("""
                async (q) => {
                    const url = 'https://xueqiu.com/statuses/search.json?q='
                        + encodeURIComponent(q) + '&count=5&page=1';
                    try {
                        const resp = await fetch(url, {
                            headers: {
                                'Accept': 'application/json',
                                'Referer': 'https://xueqiu.com/',
                                'X-Requested-With': 'XMLHttpRequest',
                            }
                        });
                        if (!resp.ok) return null;
                        const data = await resp.json();
                        if (!data.list) return null;
                        for (const item of data.list) {
                            const user = item.user || {};
                            if (user.screen_name === q) {
                                return String(user.id);
                            }
                        }
                        // Also check description match
                        for (const item of data.list) {
                            const user = item.user || {};
                            if (user.screen_name && user.screen_name.includes(q)) {
                                return String(user.id);
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
            logger.debug("Xueqiu search failed: %s", e)
            return None

    async def _fetch_timeline(self, page, user_id: str, nickname: str, days_back: int) -> List[Dict]:
        """Fetch user timeline from Xueqiu API."""
        articles = []
        now = datetime.now(timezone.utc)
        cutoff = now - timedelta(days=days_back)

        try:
            result = await page.evaluate("""
                async (uid) => {
                    const url = 'https://xueqiu.com/v4/statuses/user_timeline.json?user_id='
                        + uid + '&type=0&count=20';
                    try {
                        const resp = await fetch(url, {
                            headers: {
                                'Accept': 'application/json',
                                'Referer': 'https://xueqiu.com/',
                                'X-Requested-With': 'XMLHttpRequest',
                            }
                        });
                        if (!resp.ok) return null;
                        return await resp.json();
                    } catch(e) {
                        return null;
                    }
                }
            """, user_id)

            if not result or "statuses" not in result:
                return articles

            for status in result.get("statuses", []):
                try:
                    title = status.get("title") or status.get("description") or ""
                    text = status.get("text", "")
                    if not text:
                        continue

                    created_at = status.get("created_at", 0)
                    pub_time = (datetime.fromtimestamp(created_at / 1000)
                                if created_at else now)

                    if pub_time < cutoff:
                        continue

                    articles.append({
                        "title": title or text[:80],
                        "content": text,
                        "summary": text[:200],
                        "url": f"https://xueqiu.com{status.get('target', '')}",
                        "platform": "雪球",
                        "published_at": pub_time,
                        "source_hash": hashlib.md5(
                            f"{title}|{text[:500]}".encode("utf-8")
                        ).hexdigest(),
                    })

                    if len(articles) >= 20:
                        break

                except Exception as e:
                    logger.debug("Parse xueqiu status failed: %s", e)
                    continue

        except Exception as e:
            logger.debug("Xueqiu timeline fetch failed: %s", e)

        return articles
