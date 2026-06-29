"""
Zhihu (知乎) scraper using Playwright.
Uses page.evaluate() to call Zhihu API from within the browser context,
so the x-zse-96 signature is computed automatically by Zhihu's own JS.
Reference: MediaCrawler media_platform/zhihu/
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


@register_scraper("知乎")
class ZhihuScraper(AbstractScraper):
    """Scrape Zhihu user activities via browser-evaluated API calls."""

    platform_name = "知乎"

    async def scrape(self, vstar: VStar, days_back: int = 30) -> List[Dict]:
        articles = []
        nickname = vstar.nickname

        context = await self._bm.create_context("default")
        try:
            page = await context.new_page()

            # Step 1: Visit zhihu.com to get cookies (zse_ck, etc.)
            await page.goto("https://www.zhihu.com/", wait_until="domcontentloaded", timeout=30000)
            await page.wait_for_timeout(random.randint(2000, 4000))

            # Step 2: Search for the user to get url_token
            url_token = await self._search_user(page, nickname)
            if not url_token:
                logger.warning("Zhihu user not found: %s", nickname)
                return articles

            await page.wait_for_timeout(random.randint(1000, 2000))

            # Step 3: Fetch user activities
            articles = await self._fetch_activities(page, url_token, nickname, days_back)

        except Exception as e:
            logger.error("Zhihu scraper failed for %s: %s", nickname, e)
        finally:
            await context.close()

        return articles

    async def _search_user(self, page, nickname: str) -> Optional[str]:
        """Search Zhihu for user url_token."""
        try:
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
                        if (!resp.ok) return null;
                        const data = await resp.json();
                        if (!data.data) return null;
                        for (const item of data.data) {
                            const obj = item.object || {};
                            if (obj.name === q || obj.url_token === q) {
                                return obj.url_token || obj.id || null;
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
            logger.debug("Zhihu search failed: %s", e)
            return None

    async def _fetch_activities(self, page, url_token: str, nickname: str, days_back: int) -> List[Dict]:
        """Fetch user activities (answers, articles, pins)."""
        articles = []
        now = datetime.now(timezone.utc)
        cutoff = now - timedelta(days=days_back)

        try:
            result = await page.evaluate("""
                async (token) => {
                    const url = 'https://www.zhihu.com/api/v4/members/' + token + '/activities?limit=20&after_id=0';
                    try {
                        const resp = await fetch(url, {
                            headers: {
                                'Accept': 'application/json',
                                'x-requested-with': 'fetch',
                                'Referer': 'https://www.zhihu.com/',
                            }
                        });
                        if (!resp.ok) return null;
                        return await resp.json();
                    } catch(e) {
                        return null;
                    }
                }
            """, url_token)

            if not result or "data" not in result:
                return articles

            for item in result.get("data", []):
                try:
                    target = item.get("target", {})
                    verb = item.get("verb", "")
                    created_ts = item.get("created_time") or target.get("created_time") or 0
                    pub_time = datetime.fromtimestamp(created_ts) if created_ts else now

                    if pub_time < cutoff:
                        continue

                    title = ""
                    content = ""
                    url = ""

                    if "answer" in verb:
                        question = target.get("question", {})
                        title = question.get("title", "")
                        content = target.get("excerpt", "") or target.get("content", "")
                        qid = question.get("id", "")
                        aid = target.get("id", "")
                        url = f"https://www.zhihu.com/question/{qid}/answer/{aid}"
                    elif "article" in verb:
                        title = target.get("title", "")
                        content = target.get("excerpt", "") or target.get("content", "")
                        url = f"https://zhuanlan.zhihu.com/p/{target.get('id', '')}"
                    elif "pin" in verb:
                        content = target.get("excerpt", "") or target.get("content", "")
                        title = content[:80]
                        url = f"https://www.zhihu.com/pin/{target.get('id', '')}"
                    else:
                        continue

                    if not content:
                        continue

                    articles.append({
                        "title": title or content[:80],
                        "content": content[:5000],
                        "summary": content[:200],
                        "url": url,
                        "platform": "知乎",
                        "published_at": pub_time,
                        "source_hash": hashlib.md5(
                            f"{title}|{content[:500]}".encode("utf-8")
                        ).hexdigest(),
                    })

                    if len(articles) >= 20:
                        break

                except Exception as e:
                    logger.debug("Parse zhihu activity failed: %s", e)
                    continue

        except Exception as e:
            logger.debug("Zhihu activities fetch failed: %s", e)

        return articles
