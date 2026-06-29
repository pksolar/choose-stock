"""
WeChat Official Account (微信公众号) scraper using Playwright.
Searches via Sogou WeChat search and extracts article content from mp.weixin.qq.com.
Sogou aggressively blocks bots; Playwright with stealth.js improves success rate.
"""
import hashlib
import logging
import random
import re as regex_module
from datetime import datetime, timedelta, timezone
from typing import List, Dict, Optional
from urllib.parse import quote

from app.models.models import VStar
from app.services.scrapers.base import AbstractScraper
from app.services.scrapers import register_scraper
from app.services.browser_manager import BrowserManager

logger = logging.getLogger(__name__)


@register_scraper("公众号")
class WechatScraper(AbstractScraper):
    """Scrape WeChat Official Account articles via Sogou search."""

    platform_name = "公众号"

    async def scrape(self, vstar: VStar, days_back: int = 30) -> List[Dict]:
        articles = []
        nickname = vstar.nickname

        context = await self._bm.create_context("wechat")
        try:
            page = await context.new_page()

            # Step 1: Warm cookies by visiting Sogou WeChat home
            await page.goto("https://weixin.sogou.com/", wait_until="domcontentloaded", timeout=30000)
            await page.wait_for_timeout(random.randint(1000, 3000))

            # Step 2: Search for the account/article
            search_url = f"https://weixin.sogou.com/weixin?type=1&query={quote(nickname)}&ie=utf8"
            await page.goto(search_url, wait_until="domcontentloaded", timeout=30000)
            await page.wait_for_timeout(random.randint(2000, 4000))

            # Check for CAPTCHA
            page_content = await page.content()
            if "请输入验证码" in page_content or "antispider" in page_content.lower():
                logger.warning("Sogou CAPTCHA triggered for: %s", nickname)
                return articles

            # Step 3: Parse search results
            items = await self._parse_search_results(page, nickname)
            if not items:
                # Try article search as fallback
                await page.wait_for_timeout(random.randint(1000, 2000))
                search_url2 = f"https://weixin.sogou.com/weixin?type=2&query={quote(nickname)}&ie=utf8"
                await page.goto(search_url2, wait_until="domcontentloaded", timeout=30000)
                await page.wait_for_timeout(random.randint(2000, 4000))
                page_content2 = await page.content()
                if "请输入验证码" in page_content2 or "antispider" in page_content2.lower():
                    return articles
                items = await self._parse_search_results(page, nickname)

            if not items:
                return articles

            now = datetime.now(timezone.utc)
            cutoff = now - timedelta(days=days_back)

            for item in items[:20]:
                try:
                    title = item.get("title", "")
                    link = item.get("link", "")
                    summary = item.get("summary", "")
                    pub_time = item.get("published_at", now)

                    if pub_time < cutoff:
                        continue

                    # Get full content from mp.weixin.qq.com
                    content = summary
                    if link and "mp.weixin.qq.com" in link:
                        try:
                            await page.goto(link, wait_until="domcontentloaded", timeout=20000)
                            await page.wait_for_timeout(random.randint(1000, 3000))
                            content = await page.evaluate("""
                                () => {
                                    const el = document.querySelector('#js_content')
                                        || document.querySelector('.rich_media_content');
                                    if (!el) return '';
                                    // Remove hidden elements
                                    const clone = el.cloneNode(true);
                                    const hidden = clone.querySelectorAll('[style*="display:none"], [style*="display: none"], script, style');
                                    hidden.forEach(h => h.remove());
                                    return clone.innerText || clone.textContent || '';
                                }
                            """)
                            content = content[:5000] if content else summary
                        except Exception:
                            pass

                    if title and content:
                        articles.append({
                            "title": title,
                            "content": content,
                            "summary": (summary or content)[:200],
                            "url": link,
                            "platform": "公众号",
                            "published_at": pub_time,
                            "source_hash": hashlib.md5(
                                f"{title}|{content[:500]}".encode("utf-8")
                            ).hexdigest(),
                        })

                        if len(articles) >= 10:
                            break

                except Exception as e:
                    logger.debug("Parse WeChat article failed: %s", e)
                    continue

        except Exception as e:
            logger.error("WeChat scraper failed for %s: %s", nickname, e)
        finally:
            await context.close()

        return articles

    async def _parse_search_results(self, page, nickname: str) -> List[Dict]:
        """Parse Sogou search results from the rendered page."""
        items = []

        try:
            items = await page.evaluate("""
                () => {
                    const results = [];
                    // Try multiple selectors (Sogou changes them periodically)
                    const selectors = [
                        '.news-box .news-list li',
                        'ul.news-list2 li',
                        '.news-item',
                        'ul.news-list li',
                        '.txt-box',
                    ];

                    let elements = [];
                    for (const sel of selectors) {
                        elements = document.querySelectorAll(sel);
                        if (elements.length > 0) break;
                    }

                    for (const el of elements) {
                        const titleEl = el.querySelector('h3 a') || el.querySelector('a[href*="mp.weixin.qq.com"]') || el.querySelector('a');
                        if (!titleEl) continue;

                        const title = titleEl.innerText.trim();
                        let link = titleEl.href || '';

                        // Clean Sogou redirect URL
                        if (link && !link.includes('mp.weixin.qq.com')) {
                            // Link might be a Sogou redirect
                        }

                        const summaryEl = el.querySelector('.txt-info') || el.querySelector('p') || el.querySelector('.s-p');
                        const summary = summaryEl ? summaryEl.innerText.trim() : '';

                        const dateEl = el.querySelector('.s-p') || el.querySelector('.s2') || el.querySelector('em');
                        const dateStr = dateEl ? dateEl.innerText.trim() : '';

                        if (title) {
                            results.push({ title, link, summary, dateStr });
                            if (results.length >= 20) break;
                        }
                    }
                    return results;
                }
            """)

            # Parse dates
            now = datetime.now(timezone.utc)
            for item in items:
                item["published_at"] = self._parse_sogou_date(item.get("dateStr", "")) or now

        except Exception as e:
            logger.debug("Parse Sogou results failed: %s", e)

        return items

    @staticmethod
    def _parse_sogou_date(date_str: str) -> Optional[datetime]:
        """Parse Sogou WeChat search date strings."""
        if not date_str:
            return None
        now = datetime.utcnow()
        date_str = date_str.strip()

        if "分钟前" in date_str:
            try:
                minutes = int(regex_module.search(r'(\d+)', date_str).group(1))
                return now - timedelta(minutes=minutes)
            except Exception:
                return now
        if "小时前" in date_str:
            try:
                hours = int(regex_module.search(r'(\d+)', date_str).group(1))
                return now - timedelta(hours=hours)
            except Exception:
                return now
        if "天前" in date_str:
            try:
                days = int(regex_module.search(r'(\d+)', date_str).group(1))
                return now - timedelta(days=days)
            except Exception:
                return now - timedelta(days=1)
        if "昨天" in date_str:
            return now - timedelta(days=1)

        for fmt in ["%Y-%m-%d", "%Y/%m/%d", "%Y年%m月%d日"]:
            try:
                return datetime.strptime(date_str, fmt)
            except ValueError:
                continue
        return now
