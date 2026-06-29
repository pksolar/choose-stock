"""
Weibo (微博) scraper using Playwright.
Uses m.weibo.cn mobile API via page.evaluate() to inherit browser cookies.
Reference: MediaCrawler media_platform/wb/
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


@register_scraper("微博")
class WeiboScraper(AbstractScraper):
    """Scrape Weibo user timeline via m.weibo.cn mobile API."""

    platform_name = "微博"

    async def scrape(self, vstar: VStar, days_back: int = 30) -> List[Dict]:
        articles = []
        nickname = vstar.nickname

        context = await self._bm.create_context("weibo")
        try:
            page = await context.new_page()

            # Step 1: Warm cookies by visiting m.weibo.cn
            await page.goto("https://m.weibo.cn/", wait_until="domcontentloaded", timeout=30000)
            await page.wait_for_timeout(random.randint(1000, 3000))

            # Step 2: Search for user UID via evaluate
            uid = await self._search_user(page, nickname)
            if not uid:
                logger.warning("Weibo user not found: %s", nickname)
                return articles

            await page.wait_for_timeout(random.randint(500, 1500))

            # Step 3: Fetch user timeline
            articles = await self._fetch_timeline(page, uid, nickname, days_back)

        except Exception as e:
            logger.error("Weibo scraper failed for %s: %s", nickname, e)
        finally:
            await context.close()

        return articles

    async def _search_user(self, page, nickname: str) -> Optional[str]:
        """Search for Weibo user by name and return their UID."""
        try:
            result = await page.evaluate("""
                async (q) => {
                    // containerid value must include the query: 100103type=3&q=<name>
                    const cid = '100103type=3&q=' + encodeURIComponent(q);
                    const url = 'https://m.weibo.cn/api/container/getIndex?containerid='
                        + encodeURIComponent(cid) + '&page_type=searchall';
                    const resp = await fetch(url, {
                        headers: {
                            'Accept': 'application/json',
                            'X-Requested-With': 'XMLHttpRequest',
                            'Referer': 'https://m.weibo.cn/',
                        }
                    });
                    if (!resp.ok) return null;
                    const data = await resp.json();
                    if (data.ok !== 1 || !data.data || !data.data.cards) return null;

                    // Find the first user card group
                    for (const card of data.data.cards) {
                        if (!card.card_group) continue;
                        for (const item of card.card_group) {
                            if (item.user) {
                                // First result is the best match
                                return String(item.user.id);
                            }
                        }
                    }
                    return null;
                }
            """, nickname)
            return result
        except Exception as e:
            logger.debug("Weibo search failed: %s", e)
            return None

    async def _fetch_timeline(self, page, uid: str, nickname: str, days_back: int) -> List[Dict]:
        """Fetch user timeline from Weibo API."""
        articles = []
        now = datetime.now(timezone.utc)
        cutoff = now - timedelta(days=days_back)

        try:
            container_id = f"107603{uid}"

            result = await page.evaluate("""
                async (cid) => {
                    const url = 'https://m.weibo.cn/api/container/getIndex?containerid=' + cid + '&page=1';
                    const resp = await fetch(url, {
                        headers: {'Accept': 'application/json', 'X-Requested-With': 'XMLHttpRequest',
                                  'Referer': 'https://m.weibo.cn/'}
                    });
                    if (!resp.ok) return null;
                    return await resp.json();
                }
            """, container_id)

            if not result or result.get("ok") != 1:
                return articles

            cards = result.get("data", {}).get("cards", [])
            for card in cards:
                mblog = card.get("mblog")
                if not mblog:
                    continue

                # Parse created_at
                created_at = mblog.get("created_at", "")
                pub_time = self._parse_weibo_time(created_at) or now

                if pub_time < cutoff:
                    continue

                text = mblog.get("text", "")
                # Strip HTML tags
                import re
                text = re.sub(r'<[^>]+>', '', text)
                text = self._unescape_html(text)

                if not text:
                    continue

                mid = mblog.get("id", "")
                url = f"https://weibo.com/{uid}/{mid}" if mid else ""

                articles.append({
                    "title": text[:80],
                    "content": text[:5000],
                    "summary": text[:200],
                    "url": url,
                    "platform": "微博",
                    "published_at": pub_time,
                    "source_hash": self._content_hash(text[:80], text),
                })

                if len(articles) >= 30:
                    break

        except Exception as e:
            logger.debug("Weibo timeline fetch failed: %s", e)

        return articles

    @staticmethod
    def _parse_weibo_time(time_str: str) -> Optional[datetime]:
        """Parse Weibo time format."""
        if not time_str:
            return None
        import re
        now = datetime.utcnow()
        time_str = time_str.strip()

        if "刚刚" in time_str:
            return now
        if "分钟前" in time_str:
            try:
                minutes = int(re.search(r'(\d+)', time_str).group(1))
                return now - timedelta(minutes=minutes)
            except Exception:
                return now
        if "今天" in time_str:
            try:
                t = re.search(r'(\d{1,2}):(\d{2})', time_str)
                if t:
                    hour, minute = int(t.group(1)), int(t.group(2))
                    return now.replace(hour=hour, minute=minute, second=0, microsecond=0)
            except Exception:
                pass
            return now
        if "小时前" in time_str:
            try:
                hours = int(re.search(r'(\d+)', time_str).group(1))
                return now - timedelta(hours=hours)
            except Exception:
                return now
        if "昨天" in time_str:
            return now - timedelta(days=1)
        if "天前" in time_str:
            try:
                days = int(re.search(r'(\d+)', time_str).group(1))
                return now - timedelta(days=days)
            except Exception:
                return now
        # "Mon Jan 15 12:30:00 +0800 2024"
        try:
            from email.utils import parsedate_to_datetime
            return parsedate_to_datetime(time_str)
        except Exception:
            pass
        # "YYYY-MM-DD"
        for fmt in ["%Y-%m-%d", "%Y/%m/%d", "%Y年%m月%d日"]:
            try:
                return datetime.strptime(time_str, fmt)
            except ValueError:
                continue
        return now

    @staticmethod
    def _unescape_html(text: str) -> str:
        import html
        return html.unescape(text)

    @staticmethod
    def _content_hash(title: str, content: str) -> str:
        return hashlib.md5(f"{title}|{content[:500]}".encode("utf-8")).hexdigest()
