"""
Content scraping orchestrator.
Dispatches to Playwright-based platform scrapers, with mock data fallback.
"""
import asyncio
import hashlib
import json
import os
import random
import re
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Dict, Optional
from urllib.parse import quote

from sqlalchemy.orm import Session

from config import settings, BASE_DIR
from app.models.models import VStar, Article

# Article local storage directory
ARTICLES_DATA_DIR = BASE_DIR / "data" / "articles"
os.makedirs(ARTICLES_DATA_DIR, exist_ok=True)


# ========================================================================
#  Utilities
# ========================================================================

def get_random_ua() -> str:
    """Return a random User-Agent from the configured pool."""
    return random.choice(settings.SCRAPER_USER_AGENT_POOL)


def get_content_hash(title: str, content: str) -> str:
    """Compute content hash for deduplication."""
    raw = f"{title}|{content[:500]}"
    return hashlib.md5(raw.encode("utf-8")).hexdigest()


def _random_delay():
    """Random delay to avoid triggering anti-scraping."""
    delay = random.uniform(settings.SCRAPER_DELAY_MIN, settings.SCRAPER_DELAY_MAX)
    time.sleep(delay)


def wechat_url_convert(url: str) -> str:
    """Normalize WeChat article URL."""
    if not url:
        return url
    if "mp.weixin.qq.com" in url:
        url = url.replace("amp;", "")
    return url


# ========================================================================
#  Local JSON file storage
# ========================================================================

def save_articles_to_local(vstar_nickname: str, platform: str, articles: List[Dict]):
    """Save articles to local JSON file keyed by VStar nickname."""
    safe_name = re.sub(r'[^\w\-]', '_', vstar_nickname)
    file_path = ARTICLES_DATA_DIR / f"{safe_name}_{platform}.json"

    existing = []
    if file_path.exists():
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                existing = json.load(f)
        except (json.JSONDecodeError, IOError):
            existing = []

    existing_urls = {a.get("url") for a in existing}
    existing_titles = {a.get("title") for a in existing}

    new_count = 0
    for art in articles:
        if art.get("url") in existing_urls or art.get("title") in existing_titles:
            continue
        pub_time = art.get("published_at")
        if isinstance(pub_time, datetime):
            art["published_at"] = pub_time.isoformat()
        elif pub_time is None:
            art["published_at"] = datetime.utcnow().isoformat()
        existing.append(art)
        new_count += 1

    with open(file_path, "w", encoding="utf-8") as f:
        json.dump(existing, f, ensure_ascii=False, indent=2)

    return new_count


def load_articles_from_local(vstar_nickname: str, platform: str) -> List[Dict]:
    """Load previously saved articles from local JSON."""
    safe_name = re.sub(r'[^\w\-]', '_', vstar_nickname)
    file_path = ARTICLES_DATA_DIR / f"{safe_name}_{platform}.json"
    if not file_path.exists():
        return []
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError):
        return []


# ========================================================================
#  Data sync helpers
# ========================================================================

def sync_articles_to_db(db: Session, vstar: VStar, articles: List[Dict]) -> List[Article]:
    """Sync scraped articles to database and local files."""
    created = []
    latest_time = vstar.last_article_time

    for art_data in articles:
        title = art_data.get("title", "")
        content = art_data.get("content", "")

        source_hash = art_data.get("source_hash") or get_content_hash(title, content)
        existing = db.query(Article).filter(
            Article.vstar_id == vstar.id,
            Article.source_hash == source_hash,
        ).first()
        if existing:
            continue

        pub_time = art_data.get("published_at")
        if isinstance(pub_time, str):
            try:
                pub_time = datetime.fromisoformat(pub_time)
            except ValueError:
                pub_time = datetime.utcnow()
        elif pub_time is None:
            pub_time = datetime.utcnow()

        article = Article(
            vstar_id=vstar.id,
            title=title[:500],
            content=content,
            summary=(content or "")[:200],
            url=art_data.get("url", ""),
            platform=art_data.get("platform", vstar.platform),
            published_at=pub_time,
            source_hash=source_hash,
        )
        db.add(article)
        created.append(article)

        if not latest_time or pub_time > latest_time:
            latest_time = pub_time

    if created:
        vstar.last_article_time = latest_time
        db.commit()

    save_articles_to_local(vstar.nickname, vstar.platform, articles)

    return created


def scrape_and_persist(vstar: VStar, db: Session) -> int:
    """One-stop: scrape + persist to DB + local files. Returns new article count."""
    articles = fetch_articles_for_vstar(vstar)
    if not articles:
        return 0
    created = sync_articles_to_db(db, vstar, articles)
    return len(created)


# ========================================================================
#  Main dispatch: fetch articles for a VStar
# ========================================================================

def fetch_articles_for_vstar(vstar: VStar, days_back: int = 30) -> List[Dict]:
    """
    Fetch articles for a VStar.
    Tries Playwright-based scrapers first, falls back to mock data.
    """
    platform = vstar.platform

    # 1. Try Playwright-based scraper
    try:
        from app.services.scrapers import get_scraper
        from app.services.browser_manager import browser_manager

        if browser_manager.is_ready:
            scraper = get_scraper(platform, browser_manager)
            if scraper is not None:
                articles = _run_async(scraper.scrape(vstar, days_back))
                if articles:
                    print(f"[OK] Playwright scraper ({platform}): {len(articles)} articles for '{vstar.nickname}'")
                    return articles[:30]
                else:
                    print(f"[WARN] Playwright scraper ({platform}) returned 0 articles for '{vstar.nickname}'")
                    if platform in ("知乎", "雪球"):
                        print(f"      提示: {platform} 可能需要登录凭据才能抓取内容")
                        print(f"      配置方法: 在 .env 中设置 {platform.upper()}_USERNAME 和 {platform.upper()}_PASSWORD")
                        print(f"      或通过 API: POST /api/credentials 配置账号密码后调用 POST /api/credentials/{platform}/login")
        else:
            print(f"[WARN] Browser not ready, skipping Playwright scraper for '{vstar.nickname}'")
    except Exception as e:
        print(f"[WARN] Playwright scraper failed ({platform}): {e}")
        if "login" in str(e).lower() or "credential" in str(e).lower():
            print(f"      提示: {platform} 可能需要登录凭据，请通过 /api/credentials 配置")

    # 2. Fall back to mock data if configured
    if settings.USE_MOCK_DATA:
        print(f"[INFO] Using mock data for '{vstar.nickname}' ({platform})")
        return generate_dynamic_articles(vstar, count=5)

    print(f"[WARN] No data for '{vstar.nickname}' ({platform}) — set USE_MOCK_DATA=true for demo mode")
    return []


def _run_async(coro):
    """Bridge async Playwright code to synchronous callers.

    Playwright browser objects are bound to the event loop they were created in.
    We schedule the coroutine on that same loop via run_coroutine_threadsafe.
    There is NO asyncio.run() fallback — Playwright objects bound to another
    loop cannot be used from a new loop.
    """
    from app.services.browser_manager import browser_manager
    target_loop = getattr(browser_manager, '_loop', None)

    if not target_loop or not target_loop.is_running():
        print("[WARN] Browser event loop is not running — cannot execute async operation")
        return []

    if not browser_manager.is_ready:
        print("[WARN] Browser is not ready — cannot execute async operation")
        return []

    try:
        future = asyncio.run_coroutine_threadsafe(coro, target_loop)
        return future.result(timeout=30)
    except asyncio.TimeoutError:
        print("[WARN] Async operation timed out after 30s — browser may be stuck")
        return []
    except asyncio.CancelledError:
        print("[WARN] Async operation was cancelled")
        return []
    except Exception as e:
        print(f"[WARN] Async operation failed: {e}")
        return []


# ========================================================================
#  Dynamic article generation (mock data)
# ========================================================================

def generate_dynamic_articles(vstar: VStar, count: int = 5) -> List[Dict]:
    """Generate plausible-looking mock articles for any VStar."""
    nickname = vstar.nickname
    platform = vstar.platform
    now = datetime.utcnow()

    stocks_pool = [
        ("300750", "宁德时代", "新能源电池"),
        ("600519", "贵州茅台", "白酒龙头"),
        ("000858", "五粮液", "高端白酒"),
        ("601012", "隆基绿能", "光伏"),
        ("300274", "阳光电源", "逆变器"),
        ("688981", "中芯国际", "芯片制造"),
        ("002594", "比亚迪", "新能源车"),
        ("300059", "东方财富", "互联网券商"),
        ("601138", "工业富联", "AI服务器"),
        ("600036", "招商银行", "零售银行"),
        ("000333", "美的集团", "家电"),
        ("600276", "恒瑞医药", "创新药"),
        ("601899", "紫金矿业", "有色金属"),
        ("688111", "金山办公", "AI应用"),
        ("601318", "中国平安", "保险"),
    ]

    themes = [
        "市场复盘", "板块轮动分析", "个股深度研究", "行业趋势判断",
        "财报点评", "估值分析", "产业链调研", "投资策略思考",
        "热点解读", "技术面分析",
    ]

    templates = [
        "{title_prefix}沪深两市震荡分化，结构性机会凸显。{stock1}({code1})受益于行业景气度提升，业绩有望超预期。{stock2}({code2})的估值已经回到合理区间，具备中长线配置价值。",
        "{title_prefix}关于{stock1}({code1})，我认为市场存在预期差。一方面产能释放超预期，另一方面下游需求持续旺盛。同时{stock2}({code2})也值得关注，技术壁垒深厚。",
        "{title_prefix}简单说几句。{stock1}({code1})的海外拓展取得突破性进展，{stock2}({code2})的基本面持续改善。此外{stock3}({code3})的竞争格局也在优化。",
        "{title_prefix}从产业链角度看，{stock1}({code1})处于上游核心环节，定价能力强。{stock2}({code2})作为中游龙头，市占率持续提升。长期看好。",
        "{title_prefix}最近调研了几家公司。{stock1}({code1})的产线满产运行，{stock2}({code2})的新产品放量在即。{stock3}({code3})的估值安全边际充足。",
    ]

    articles = []
    for i in range(min(count, 10)):
        selected = random.sample(stocks_pool, random.randint(2, 3))
        stock1, stock2 = selected[0], selected[1]
        stock3 = selected[2] if len(selected) > 2 else None

        theme = random.choice(themes)
        title_prefix = f"【{nickname}·{theme}】"

        tpl = random.choice(templates)
        content = tpl.format(
            title_prefix=title_prefix,
            stock1=stock1[1], code1=stock1[0],
            stock2=stock2[1], code2=stock2[0],
            stock3=stock3[1] if stock3 else "贵州茅台",
            code3=stock3[0] if stock3 else "600519",
        )

        title = f"{nickname}：{theme} — {stock1[1]}与{stock2[1]}的投资机会"
        pub_time = now - timedelta(days=random.randint(0, 6), hours=random.randint(0, 23))

        articles.append({
            "title": title,
            "content": content,
            "summary": content[:200],
            "url": f"https://{platform}.example.com/article/{hashlib.md5(title.encode()).hexdigest()[:10]}",
            "platform": platform,
            "published_at": pub_time,
            "source_hash": get_content_hash(title, content),
        })

    return articles


def generate_mock_articles(db: Session, vstars: List[VStar]) -> List[Article]:
    """Generate mock article data for demo VStars."""
    created = []
    now = datetime.utcnow()

    for vstar in vstars:
        existing_count = db.query(Article).filter(Article.vstar_id == vstar.id).count()
        if existing_count > 0:
            continue

        dyn_articles = generate_dynamic_articles(vstar, count=5)
        for art_data in dyn_articles:
            pub_time = art_data.get("published_at")
            if isinstance(pub_time, str):
                try:
                    pub_time = datetime.fromisoformat(pub_time)
                except ValueError:
                    pub_time = now
            elif pub_time is None:
                pub_time = now

            article = Article(
                vstar_id=vstar.id,
                title=art_data["title"],
                content=art_data["content"],
                summary=art_data["content"][:200],
                url=art_data["url"],
                platform=art_data["platform"],
                published_at=pub_time,
                source_hash=art_data["source_hash"],
            )
            db.add(article)
            created.append(article)

            if not vstar.last_article_time or pub_time > vstar.last_article_time:
                vstar.last_article_time = pub_time

        save_articles_to_local(vstar.nickname, vstar.platform, dyn_articles)

    if created:
        db.commit()

    return created
