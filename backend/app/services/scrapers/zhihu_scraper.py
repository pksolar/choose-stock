"""
Zhihu scraper using Playwright.
Strategy:
  1. Load persisted cookies (manual login via login_zhihu.py).
  2. Visit zhihu.com to warm cookies.
  3. Search for the user's url_token (API then HTML fallback).
  4. Fetch activities (API then HTML profile page fallback).
"""
import hashlib
import logging
import random
import re
from datetime import datetime, timedelta, timezone
from typing import List, Dict, Optional
from urllib.parse import quote

from app.models.models import VStar
from app.services.scrapers.base import AbstractScraper
from app.services.scrapers import register_scraper
from app.services.browser_manager import BrowserManager

logger = logging.getLogger(__name__)


@register_scraper("知乎")
class ZhihuScraper(AbstractScraper):

    platform_name = "知乎"

    async def scrape(self, vstar: VStar, days_back: int = 30) -> List[Dict]:
        articles = []
        nickname = vstar.nickname

        await self._bm.ensure_authenticated("知乎")

        context = await self._bm.create_context("知乎")
        try:
            page = await context.new_page()

            # Step 1: Visit zhihu.com to warm cookies & trigger anti-bot JS
            await page.goto("https://www.zhihu.com/explore",
                            wait_until="networkidle", timeout=45000)
            await page.wait_for_timeout(random.randint(4000, 6000))

            cookies = await context.cookies()
            has_z_c0 = any(c['name'] == 'z_c0' for c in cookies)
            logger.info("Zhihu auth state: z_c0=%s, total_cookies=%d", has_z_c0, len(cookies))

            # Step 2: Search for the user to get url_token
            url_token = await self._search_user(page, nickname)
            if not url_token:
                logger.warning("Zhihu user not found: %s", nickname)
                return articles

            await page.wait_for_timeout(random.randint(1000, 2000))

            # Step 3: API-based activities fetch
            articles = await self._fetch_activities_api(page, url_token, nickname, days_back)

            # Step 4: HTML fallback
            if not articles:
                logger.info("API fetch empty for %s, trying HTML scrape", nickname)
                articles = await self._scrape_activities_html(page, url_token, nickname, days_back)

        except Exception as e:
            logger.error("Zhihu scraper failed for %s: %s", nickname, e)
        else:
            await self._bm.save_auth_state(context, "知乎")
        finally:
            await context.close()

        return articles

    # ------------------------------------------------------------------
    # User search (API -> HTML fallback)
    # ------------------------------------------------------------------

    async def _search_user(self, page, nickname: str) -> Optional[str]:
        result = await self._search_user_api(page, nickname)
        if result:
            return result
        logger.info("API search failed for %s, trying HTML search page", nickname)
        return await self._search_user_html(page, nickname)

    async def _search_user_api(self, page, nickname: str) -> Optional[str]:
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
                        if (!resp.ok) return {_error: resp.status};
                        const data = await resp.json();
                        if (!data.data || !data.data.length) return {_error: 'empty'};
                        for (const item of data.data) {
                            const obj = item.object || {};
                            if (obj.name === q || obj.url_token === q)
                                return obj.url_token || obj.id || null;
                        }
                        const first = (data.data[0] || {}).object || {};
                        return first.url_token || {_error: 'no_match'};
                    } catch(e) {
                        return {_error: e.message};
                    }
                }
            """, nickname)

            if isinstance(result, str) and len(result) < 100 and not result.startswith("{"):
                logger.info("Zhihu API search: %s -> %s", nickname, result)
                return result
            logger.info("Zhihu API search '%s': %s", nickname, result)
            return None
        except Exception as e:
            logger.debug("Zhihu API search error: %s", e)
            return None

    async def _search_user_html(self, page, nickname: str) -> Optional[str]:
        try:
            search_url = f"https://www.zhihu.com/search?type=people&q={quote(nickname)}"
            await page.goto(search_url, wait_until="networkidle", timeout=30000)
            await page.wait_for_timeout(random.randint(3000, 5000))

            result = await page.evaluate("""
                (q) => {
                    const links = document.querySelectorAll('a[href*="/people/"]');
                    for (const link of links) {
                        const href = link.getAttribute('href') || '';
                        const m = href.match(/\\/people\\/([^/?]+)/);
                        if (!m) continue;
                        const token = m[1];
                        const card = link.closest('[class*="SearchResult"]')
                            || link.closest('[class*="List-item"]')
                            || link.closest('[class*="Card"]');
                        if (card && card.textContent.includes(q)) return token;
                        if (link.textContent.trim().includes(q)) return token;
                    }
                    for (const link of links) {
                        const m = (link.getAttribute('href') || '').match(/\\/people\\/([^/?]+)/);
                        if (m) return m[1];
                    }
                    return null;
                }
            """, nickname)

            if result:
                logger.info("Zhihu HTML search: %s -> %s", nickname, result)
            return result
        except Exception as e:
            logger.debug("Zhihu HTML search error: %s", e)
            return None

    # ------------------------------------------------------------------
    # API-based activities fetch
    # ------------------------------------------------------------------

    async def _fetch_activities_api(self, page, url_token: str,
                                    nickname: str, days_back: int) -> List[Dict]:
        articles = []
        now = datetime.now(timezone.utc)
        cutoff = now - timedelta(days=days_back)

        try:
            result = await page.evaluate("""
                async (token) => {
                    const url = 'https://www.zhihu.com/api/v4/members/'
                        + token + '/activities?limit=20&after_id=0';
                    try {
                        const resp = await fetch(url, {
                            headers: {
                                'Accept': 'application/json',
                                'x-requested-with': 'fetch',
                                'Referer': 'https://www.zhihu.com/',
                            }
                        });
                        if (!resp.ok) return {_error: resp.status};
                        return await resp.json();
                    } catch(e) {
                        return {_error: e.message};
                    }
                }
            """, url_token)

            if isinstance(result, dict) and "_error" in result:
                logger.info("Zhihu activities API error for %s: %s", nickname, result["_error"])
                return articles

            if not result or "data" not in result:
                logger.info("Zhihu activities API empty for %s", nickname)
                return articles

            for item in result.get("data", []):
                try:
                    target = item.get("target", {})
                    verb = item.get("verb", "")
                    created_ts = item.get("created_time") or target.get("created_time") or 0
                    pub_time = datetime.fromtimestamp(created_ts) if created_ts else now

                    if pub_time < cutoff:
                        continue

                    title, content, article_url = self._extract_activity(item, verb, target)
                    if not content:
                        continue

                    articles.append({
                        "title": title or content[:80],
                        "content": content[:5000],
                        "summary": content[:200],
                        "url": article_url,
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
            logger.debug("Zhihu activities API error: %s", e)

        return articles

    # ------------------------------------------------------------------
    # HTML-based scraping (fallback)
    # ------------------------------------------------------------------

    async def _scrape_activities_html(self, page, url_token: str,
                                      nickname: str, days_back: int) -> List[Dict]:
        articles = []
        now = datetime.now(timezone.utc)
        cutoff = now - timedelta(days=days_back)

        try:
            profile_url = f"https://www.zhihu.com/people/{url_token}"
            await page.goto(profile_url, wait_until="networkidle", timeout=30000)
            await page.wait_for_timeout(random.randint(3000, 5000))

            for _ in range(3):
                await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                await page.wait_for_timeout(random.randint(1500, 3000))

            items = await page.evaluate("""() => {
                const results = [];
                const cards = document.querySelectorAll(
                    '.List-item, .ContentItem, [data-za-detail-view-path-module="ProfileContentItem"]'
                );
                cards.forEach(card => {
                    const titleEl = card.querySelector(
                        'h2, .ContentItem-title, .QuestionItem-title, a[data-za-detail-view-element_name="Title"]'
                    );
                    const title = titleEl ? titleEl.textContent.trim() : '';
                    const contentEl = card.querySelector(
                        '.RichContent-inner, .ContentItem-content, .Post-content, [itemprop="text"]'
                    );
                    const content = contentEl ? contentEl.textContent.trim() : '';
                    const linkEl = card.querySelector(
                        'a[href*="/answer/"], a[href*="/p/"], a[href*="/pin/"]'
                    );
                    const url = linkEl ? linkEl.href : '';
                    const timeEl = card.querySelector('time, [itemprop="dateCreated"]');
                    const timeStr = timeEl
                        ? (timeEl.getAttribute('datetime') || timeEl.textContent.trim())
                        : '';
                    if (content) results.push({ title, content, url, timeStr });
                });
                return results;
            }""")

            for item in items:
                try:
                    pub_time = self._parse_zhihu_time(item.get("timeStr", "")) or now
                    if pub_time < cutoff:
                        continue
                    title = item.get("title", "")
                    content = item.get("content", "")
                    article_url = item.get("url", "")
                    if not content:
                        continue
                    articles.append({
                        "title": title or content[:80],
                        "content": content[:5000],
                        "summary": content[:200],
                        "url": article_url or profile_url,
                        "platform": "知乎",
                        "published_at": pub_time,
                        "source_hash": hashlib.md5(
                            f"{title}|{content[:500]}".encode("utf-8")
                        ).hexdigest(),
                    })
                    if len(articles) >= 20:
                        break
                except Exception as e:
                    logger.debug("Parse zhihu HTML item failed: %s", e)
                    continue
        except Exception as e:
            logger.debug("Zhihu HTML scrape error: %s", e)

        return articles

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _extract_activity(self, item: dict, verb: str, target: dict):
        title = ""
        content = ""
        url = ""

        if "answer" in verb:
            question = target.get("question", {})
            title = question.get("title", "")
            content = target.get("excerpt", "") or target.get("content", "")
            qid = question.get("id", "")
            aid = target.get("id", "")
            url = f"https://www.zhihu.com/question/{qid}/answer/{aid}" if qid and aid else ""
        elif "article" in verb:
            title = target.get("title", "")
            content = target.get("excerpt", "") or target.get("content", "")
            aid = target.get("id", "")
            url = f"https://zhuanlan.zhihu.com/p/{aid}" if aid else ""
        elif "pin" in verb:
            content = target.get("excerpt", "") or target.get("content", "")
            title = content[:80]
            pid = target.get("id", "")
            url = f"https://www.zhihu.com/pin/{pid}" if pid else ""
        elif "question" in verb:
            title = target.get("title", "")
            content = target.get("excerpt", "") or target.get("detail", "")
            qid = target.get("id", "")
            url = f"https://www.zhihu.com/question/{qid}" if qid else ""
        else:
            content = target.get("excerpt", "") or target.get("content", "")
            title = content[:80]

        return title, content, url

    @staticmethod
    def _parse_zhihu_time(time_str: str) -> Optional[datetime]:
        if not time_str:
            return None
        time_str = time_str.strip()
        now = datetime.utcnow()

        if "刚刚" in time_str:
            return now
        if "分钟前" in time_str:
            try:
                minutes = int(re.search(r'(\d+)', time_str).group(1))
                return now - timedelta(minutes=minutes)
            except Exception:
                return now
        if "小时前" in time_str:
            try:
                hours = int(re.search(r'(\d+)', time_str).group(1))
                return now - timedelta(hours=hours)
            except Exception:
                return now
        if "昨天" in time_str:
            return now - timedelta(days=1)
        if "前天" in time_str:
            return now - timedelta(days=2)
        if "天前" in time_str:
            try:
                days = int(re.search(r'(\d+)', time_str).group(1))
                return now - timedelta(days=days)
            except Exception:
                return now

        for fmt in ["%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M:%S.%f",
                    "%Y-%m-%d %H:%M:%S", "%Y-%m-%d"]:
            try:
                return datetime.strptime(time_str, fmt)
            except ValueError:
                continue

        try:
            ts = float(time_str)
            if ts > 1e12:
                ts /= 1000
            return datetime.fromtimestamp(ts)
        except (ValueError, TypeError):
            pass

        return now
