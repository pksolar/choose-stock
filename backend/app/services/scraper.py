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
    We must schedule the coroutine on that same loop, not create a new one.
    """
    from app.services.browser_manager import browser_manager
    target_loop = getattr(browser_manager, '_loop', None)
    if target_loop and target_loop.is_running():
        future = asyncio.run_coroutine_threadsafe(coro, target_loop)
        return future.result(timeout=120)
    return asyncio.run(coro)


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


# ========================================================================
#  Mock data (compatible with old API, used at initialization)
# ========================================================================

MOCK_ARTICLES = [
    ("唐史主任司马迁", "雪球", "近期调研汇总：重点关注新能源与半导体",
     "最近走访了几家公司，宁德时代(300750)的产线利用率持续高位，订单饱满。另外中芯国际(688981)的先进制程有突破性进展，值得关注。贵州茅台(600519)春节动销数据超预期，消费复苏信号明显。",
     0),
    ("招财大牛猫", "公众号", "闲聊几句，聊聊最近的持仓",
     "我最近加仓了东方财富(300059)，券商里面它互联网属性最强。另外阳光电源(300274)的海外订单增长很快，逆变器毛利率回升。但要注意隆基绿能(601012)的竞争压力加大，行业内卷严重。",
     1),
    ("刘备教授", "知乎", "医药板块深度分析：创新药的机会来了？",
     "恒瑞医药(600276)的PD-1新适应症获批，创新药管线逐步兑现。同时迈瑞医疗(300760)的海外市场拓展加速，医疗新基建持续受益。不过复星医药(600196)的商誉问题需要警惕。",
     0),
    ("林奇投资笔记", "雪球", "AI算力赛道全面梳理",
     "浪潮信息(000977)的AI服务器出货量增长迅速，寒武纪(688256)的思元590性能超预期。中科曙光(603019)也值得跟踪，但估值已经不便宜。金山办公(688111)的AI应用落地速度在加快。",
     2),
    ("期货小明", "微博", "有色金属周期启动判断",
     "紫金矿业(601899)的海外矿山投产顺利，铜金价格共振。北方稀土(600111)受益于新能源车磁材需求增长。此外中国铝业(601600)的电解铝利润改善明显。",
     1),
    ("股海老船长", "东方财富", "消费白马股估值修复行情展望",
     "美的集团(000333)的海外营收占比持续提升，格力电器(000651)渠道改革初见成效。伊利股份(600887)的奶粉业务超预期，双汇发展(000895)的高股息策略具备防御价值。五粮液(000858)当前估值合理，有配置价值。",
     0),
    ("月风投资笔记", "知乎", "新能源车产业链最新跟踪",
     "宁德时代(300750)麒麟电池量产进度超预期，比亚迪(002594)的海外市场拓展迅猛。同时先导智能(300450)受益于电池厂扩产，订单能见度到2025年。天齐锂业(002466)的锂盐价格企稳。",
     2),
    ("价值发现者", "雪球", "银行股投资价值重估",
     "招商银行(600036)的零售业务护城河依然深厚，财富管理转型持续推进。宁波银行(002142)的资产质量在全行业领先，拨备覆盖率充足。工商银行(601398)的高股息率在当前低利率环境下极具吸引力。",
     1),
    ("打板高手日记", "同花顺", "短线情绪观察：AI与机器人",
     "工业富联(601138)的AI服务器代工业务量翻倍，汇川技术(300124)的机器人业务开始放量。科大讯飞(002230)的星火大模型应用场景拓展顺利，商业化提速。天孚通信(300394)的光模块800G需求旺盛。",
     0),
    ("老端投资学", "公众号", "军工板块投资机会分析",
     "中航沈飞(600760)的新机型列装加速，西部超导(688122)的高温合金订单增长。另外中国船舶(600150)的军民船业务双轮驱动，业绩拐点已经出现。",
     3),
]


def generate_mock_articles(db: Session, vstars: List[VStar]) -> List[Article]:
    """
    Generate mock article data for built-in demo VStars.
    Also generates dynamic content for additional VStars.
    """
    created = []
    now = datetime.utcnow()
    vstar_map = {(v.nickname, v.platform): v for v in vstars}
    vstar_local_cache = {}

    # 1. Process hardcoded demo VStars
    for nickname, platform, title, content, day_offset in MOCK_ARTICLES:
        vstar = vstar_map.get((nickname, platform))
        if not vstar:
            continue

        pub_time = now - timedelta(days=day_offset, hours=random.randint(0, 23))

        existing = db.query(Article).filter(
            Article.vstar_id == vstar.id,
            Article.title == title,
        ).first()
        if existing:
            continue

        source_hash = get_content_hash(title, content)
        article = Article(
            vstar_id=vstar.id,
            title=title,
            content=content,
            summary=content[:200],
            url=f"https://{platform}.example.com/article/{hashlib.md5(title.encode()).hexdigest()[:8]}",
            platform=platform,
            published_at=pub_time,
            source_hash=source_hash,
        )
        db.add(article)
        created.append(article)
        vstar_local_cache.setdefault(vstar.id, []).append({
            "title": title,
            "content": content,
            "summary": content[:200],
            "url": f"https://{platform}.example.com/article/{hashlib.md5(title.encode()).hexdigest()[:8]}",
            "platform": platform,
            "published_at": pub_time,
            "source_hash": source_hash,
        })

        if not vstar.last_article_time or pub_time > vstar.last_article_time:
            vstar.last_article_time = pub_time

    db.commit()

    # 2. Generate dynamic articles for remaining VStars
    mock_vstar_keys = set(vstar_map.keys()) & {(n, p) for n, p, _, _, _ in MOCK_ARTICLES}
    remaining_vstars = [v for v in vstars if (v.nickname, v.platform) not in mock_vstar_keys]

    for vstar in remaining_vstars:
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
            vstar_local_cache.setdefault(vstar.id, []).append(art_data)

            if not vstar.last_article_time or pub_time > vstar.last_article_time:
                vstar.last_article_time = pub_time

    if created:
        db.commit()

    # 3. Sync to local JSON files
    for vstar_id, articles_data in vstar_local_cache.items():
        vstar = db.query(VStar).filter(VStar.id == vstar_id).first()
        if vstar:
            save_articles_to_local(vstar.nickname, vstar.platform, articles_data)

    return created
