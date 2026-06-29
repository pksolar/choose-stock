"""
内容抓取服务
支持自动抓取（requests + BeautifulSoup）和手动导入两种模式
抓取结果保存到本地 JSON 文件 + 数据库
"""
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

import requests
from bs4 import BeautifulSoup
from sqlalchemy.orm import Session

from config import settings, BASE_DIR
from app.models.models import VStar, Article, PlatformEnum

# 文章本地存储目录
ARTICLES_DATA_DIR = BASE_DIR / "data" / "articles"
os.makedirs(ARTICLES_DATA_DIR, exist_ok=True)


def get_random_ua() -> str:
    """随机获取 User-Agent"""
    return random.choice(settings.SCRAPER_USER_AGENT_POOL)


def get_content_hash(title: str, content: str) -> str:
    """计算内容哈希用于去重"""
    raw = f"{title}|{content[:500]}"
    return hashlib.md5(raw.encode("utf-8")).hexdigest()


def _random_delay():
    """随机延迟，避免被反爬"""
    delay = random.uniform(settings.SCRAPER_DELAY_MIN, settings.SCRAPER_DELAY_MAX)
    time.sleep(delay)


# ========================================================================
#  本地 JSON 文件存储
# ========================================================================

def save_articles_to_local(vstar_nickname: str, platform: str, articles: List[Dict]):
    """将文章保存到本地 JSON 文件"""
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
        # 确保日期可序列化
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
    """从本地 JSON 文件加载已保存的文章"""
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
#  微信公众号抓取（通过搜狗微信搜索）
# ========================================================================

def _scrape_wechat(vstar: VStar, days_back: int = 30) -> List[Dict]:
    """
    抓取微信公众号文章
    通过搜狗微信搜索接口 (weixin.sogou.com)
    """
    articles = []
    nickname = vstar.nickname

    try:
        # 第一步：搜索公众号/文章
        search_url = f"https://weixin.sogou.com/weixin?type=1&query={quote(nickname)}&ie=utf8"
        headers = {
            "User-Agent": get_random_ua(),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
            "Accept-Encoding": "gzip, deflate",
            "Referer": "https://weixin.sogou.com/",
            "Connection": "keep-alive",
        }

        session = requests.Session()
        session.headers.update(headers)

        # 先访问首页获取 cookie
        session.get("https://weixin.sogou.com/", timeout=15, headers=headers)
        _random_delay()

        resp = session.get(search_url, timeout=20, headers=headers)

        if resp.status_code != 200:
            # 请求失败时尝试备用方法：直接搜索文章
            return _scrape_wechat_article_search(vstar, days_back)

        soup = BeautifulSoup(resp.text, "lxml")
        # 检查是否被反爬（验证码页面）
        if "请输入验证码" in resp.text or "antispider" in resp.text.lower():
            print(f"[WARN] 搜狗微信搜索触发验证码，尝试备用抓取方案")
            articles = _scrape_wechat_article_search(vstar, days_back)
            if not articles and settings.USE_MOCK_DATA:
                return _scrape_wechat_fallback(vstar, days_back)
            return articles

        # 解析搜索结果
        items = soup.select(".news-box .news-list li") or soup.select(".txt-box") or soup.select("ul.news-list2 li")
        if not items:
            items = soup.select(".news-item") or soup.select("ul.news-list li")

        for item in items:
            try:
                title_el = item.select_one("h3 a") or item.select_one(".txt-box h3 a") or item.select_one("a")
                if not title_el:
                    continue

                title = title_el.get_text(strip=True)
                link = title_el.get("href", "")

                # 搜狗链接通常带有微信官方域名的跳转
                if "mp.weixin.qq.com" not in link and link:
                    # 可能需要跟随重定向获取真实URL
                    pass

                # 摘要
                summary_el = item.select_one(".txt-info") or item.select_one("p")
                summary = summary_el.get_text(strip=True) if summary_el else ""

                # 发布日期
                date_el = item.select_one(".s-p") or item.select_one(".s2") or item.select_one("em")
                pub_date_str = date_el.get_text(strip=True) if date_el else ""

                # 解析日期（搜狗格式通常是 "2024-01-15" 或 "1小时前" 等）
                pub_time = _parse_sogou_date(pub_date_str)

                if title and link:
                    # 获取文章真实URL（搜狗的链接是跳转链接）
                    real_url = _resolve_sogou_url(link, session) or link
                    real_url = wechat_url_convert(real_url)

                    # 尝试获取全文内容
                    content = summary
                    try:
                        content = _fetch_wechat_article_content(real_url, session)
                    except Exception:
                        pass

                    articles.append({
                        "title": title,
                        "content": content,
                        "summary": summary[:200] if summary else content[:200],
                        "url": real_url,
                        "platform": "公众号",
                        "published_at": pub_time or datetime.utcnow(),
                        "source_hash": get_content_hash(title, content),
                    })

                    if len(articles) >= 20:
                        break
            except Exception as e:
                print(f"[DEBUG] 解析微信文章条目失败: {e}")
                continue

    except Exception as e:
        print(f"[WARN] 微信公众号抓取失败 ({nickname}): {e}")
        if settings.USE_MOCK_DATA:
            return _scrape_wechat_fallback(vstar, days_back)
        return []

    return articles


def _scrape_wechat_article_search(vstar: VStar, days_back: int = 30) -> List[Dict]:
    """备用方案：通过搜狗文章搜索接口"""
    articles = []
    try:
        nickname = vstar.nickname
        search_url = f"https://weixin.sogou.com/weixin?type=2&query={quote(nickname)}&ie=utf8"
        headers = {
            "User-Agent": get_random_ua(),
            "Accept": "text/html,application/xhtml+xml",
            "Accept-Language": "zh-CN,zh;q=0.9",
        }

        session = requests.Session()
        session.get("https://weixin.sogou.com/", timeout=15, headers=headers)
        _random_delay()

        resp = session.get(search_url, timeout=20, headers=headers)
        if resp.status_code != 200 or "验证码" in resp.text:
            if settings.USE_MOCK_DATA:
                return _scrape_wechat_fallback(vstar, days_back)
            return []

        soup = BeautifulSoup(resp.text, "lxml")
        items = soup.select(".news-list li") or soup.select(".txt-box")

        for item in items:
            title_el = item.select_one("h3 a") or item.select_one("a")
            if not title_el:
                continue
            title = title_el.get_text(strip=True)
            link = title_el.get("href", "")
            link = wechat_url_convert(link)

            content = ""
            summary_el = item.select_one("p") or item.select_one(".txt-info")
            if summary_el:
                content = summary_el.get_text(strip=True)

            if title:
                articles.append({
                    "title": title,
                    "content": content,
                    "summary": content[:200],
                    "url": link,
                    "platform": "公众号",
                    "published_at": datetime.utcnow(),
                    "source_hash": get_content_hash(title, content),
                })
                if len(articles) >= 20:
                    break
    except Exception as e:
        print(f"[WARN] 备用微信搜索也失败: {e}")

    return articles


def _scrape_wechat_fallback(vstar: VStar, days_back: int = 30) -> List[Dict]:
    """
    最终备用方案：生成基于大V昵称的示例文章
    当真实抓取不可用时提供可用的演示数据
    """
    articles = []
    nickname = vstar.nickname
    now = datetime.utcnow()

    # 财经/投资类公众号的典型文章模板
    templates = [
        {
            "title": f"【{nickname}】近期市场观点汇总与持仓复盘",
            "content": (
                f"大家好，我是{nickname}。最近市场波动较大，简单聊聊我的看法。"
                f"整体来看，目前市场处于震荡分化阶段，结构性机会依然存在。"
                f"重点关注新能源板块的宁德时代(300750)、比亚迪(002594)，"
                f"以及消费板块的贵州茅台(600519)、五粮液(000858)。"
                f"半导体方向，中芯国际(688981)的先进制程进展值得持续跟踪。"
                f"整体仓位控制在6-7成，进可攻退可守。"
            ),
        },
        {
            "title": f"{nickname}：这周重点关注这几个方向",
            "content": (
                f"本周重点关注几个方向：第一，AI算力持续景气，"
                f"工业富联(601138)、中科曙光(603019)受益明显。"
                f"第二，医药板块估值处于历史底部，恒瑞医药(600276)、"
                f"迈瑞医疗(300760)具备长期配置价值。"
                f"第三，红利策略依然有效，长江电力(600900)、"
                f"中国神华(601088)等高股息标的防御性较强。"
            ),
        },
        {
            "title": f"【干货】{nickname}最新产业链调研笔记",
            "content": (
                f"最近跑了一圈调研，分享一些干货。新能源车产业链方面，"
                f"宁德时代(300750)的麒麟电池产线满产，订单能见度到明年。"
                f"阳光电源(300274)逆变器海外出货量超预期，毛利率持续改善。"
                f"光伏方面，隆基绿能(601012)的HPBC电池技术路线逐渐清晰，"
                f"但行业价格战仍在持续，需要精选个股。"
                f"消费电子方面，立讯精密(002475)的Vision Pro产线备货积极。"
            ),
        },
        {
            "title": f"{nickname}：下半年投资策略思考",
            "content": (
                f"站在年中节点，对下半年做一下策略思考。"
                f"宏观层面，美联储降息预期的反复会影响全球资本流动。"
                f"A股方面，上证指数围绕3000-3200点震荡的概率较大。"
                f"行业配置上，看好三条主线：一是科技自主可控（中芯国际688981、海光信息688041），"
                f"二是消费复苏（中国中免601888、爱尔眼科300015），"
                f"三是高端制造（汇川技术300124、先导智能300450）。"
            ),
        },
        {
            "title": f"【{nickname}】周末复盘：这周操作得失总结",
            "content": (
                f"周末了，例行复盘。这周最大的收获是对东方财富(300059)的判断，"
                f"市场情绪回暖后券商弹性确实不错。但也有失误，对科大讯飞(002230)的"
                f"回调幅度估计不足。整体来看，现在市场还是存量博弈的格局，"
                f"热点轮动很快。短期内我会继续关注AI应用和数据要素方向，"
                f"比如金山办公(688111)、用友网络(600588)这类。"
            ),
        },
        {
            "title": f"【{nickname}】聊聊最近的板块轮动",
            "content": (
                f"板块轮动方面，最近观察到几个有趣的现象。"
                f"之前强势的AI板块出现分化，纯概念炒作的票开始回调，"
                f"但业绩确定性的标的如天孚通信(300394)、中际旭创(300308)依然强势。"
                f"与此同时，底部的消费板块开始有资金试探性建仓，"
                f"贵州茅台(600519)、美的集团(000333)近期有企稳迹象。"
                f"我的策略是在两大方向均衡配置。"
            ),
        },
        {
            "title": f"{nickname}：当前最值得关注的几只票",
            "content": (
                f"今天聊聊我个人比较关注的几只票。"
                f"第一只是宁德时代(300750)，全球动力电池龙头，估值已经回到合理区间。"
                f"第二只是招商银行(600036)，零售银行龙头，高股息低估值。"
                f"第三只是紫金矿业(601899)，铜金双轮驱动，海外矿山投产。"
                f"第四只是迈瑞医疗(300760)，医疗器械龙头，国际化加速。"
                f"以上仅供参考，不构成投资建议。"
            ),
        },
    ]

    for i, tpl in enumerate(templates):
        pub_time = now - timedelta(days=i, hours=random.randint(0, 23))
        content = tpl["content"]
        title = tpl["title"]

        articles.append({
            "title": title,
            "content": content,
            "summary": content[:200],
            "url": f"https://mp.weixin.qq.com/s/{hashlib.md5(f'{nickname}_{i}'.encode()).hexdigest()[:12]}",
            "platform": "公众号",
            "published_at": pub_time,
            "source_hash": get_content_hash(title, content),
        })

    return articles


def _parse_sogou_date(date_str: str) -> Optional[datetime]:
    """解析搜狗微信搜索返回的日期字符串"""
    if not date_str:
        return None

    now = datetime.utcnow()
    date_str = date_str.strip()

    # "1小时前" / "30分钟前"
    if "分钟前" in date_str:
        try:
            minutes = int(re.search(r'(\d+)', date_str).group(1))
            return now - timedelta(minutes=minutes)
        except Exception:
            return now
    if "小时前" in date_str:
        try:
            hours = int(re.search(r'(\d+)', date_str).group(1))
            return now - timedelta(hours=hours)
        except Exception:
            return now
    if "天前" in date_str or "昨天" in date_str:
        try:
            days = int(re.search(r'(\d+)', date_str).group(1)) if "天前" in date_str else 1
            return now - timedelta(days=days)
        except Exception:
            return now - timedelta(days=1)

    # "2025-06-20" 或 "2025/06/20" 或 "2025年6月20日"
    for fmt in ["%Y-%m-%d", "%Y/%m/%d", "%Y年%m月%d日"]:
        try:
            return datetime.strptime(date_str, fmt)
        except ValueError:
            continue

    return now


def _resolve_sogou_url(sogou_url: str, session: requests.Session) -> Optional[str]:
    """解析搜狗微信的跳转链接，获取真实微信公众号文章URL"""
    try:
        if "mp.weixin.qq.com" in sogou_url:
            return sogou_url
        # 跟随重定向
        resp = session.get(sogou_url, timeout=10, allow_redirects=True, headers={
            "User-Agent": get_random_ua(),
            "Referer": "https://weixin.sogou.com/",
        })
        if resp.status_code == 200 and "mp.weixin.qq.com" in resp.url:
            return resp.url
        return sogou_url
    except Exception:
        return sogou_url


def _fetch_wechat_article_content(url: str, session: requests.Session) -> str:
    """获取微信公众号文章全文"""
    try:
        headers = {
            "User-Agent": get_random_ua(),
            "Accept": "text/html,application/xhtml+xml",
            "Accept-Language": "zh-CN,zh;q=0.9",
        }
        resp = session.get(url, timeout=15, headers=headers)
        if resp.status_code == 200:
            soup = BeautifulSoup(resp.text, "lxml")
            content_el = soup.select_one("#js_content") or soup.select_one(".rich_media_content")
            if content_el:
                # 移除不需要的元素
                for tag in content_el.select("script, style, .reward_area"):
                    tag.decompose()
                return content_el.get_text(separator="\n", strip=True)[:5000]
    except Exception as e:
        print(f"[DEBUG] 获取微信文章内容失败: {e}")
    return ""


def wechat_url_convert(url: str) -> str:
    """标准化微信文章URL"""
    if not url:
        return url
    # 去掉搜狗包装的链接参数
    if "sogou.com" in url:
        return url
    # 保留微信原始链接
    if "mp.weixin.qq.com" in url:
        # 去掉 amp; 等转义
        url = url.replace("amp;", "")
    return url


# ========================================================================
#  通用文章生成（为没有真实数据的VStar提供动态内容）
# ========================================================================

def generate_dynamic_articles(vstar: VStar, count: int = 5) -> List[Dict]:
    """
    为任意大V动态生成模拟文章
    基于真实股票数据生成看起来合理的内容，用于展示系统功能
    """
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
        # 随机选2-3只股票
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
#  主抓取入口
# ========================================================================

def fetch_articles_for_vstar(vstar: VStar, days_back: int = 30) -> List[Dict]:
    """
    为指定大V抓取时间窗口内的文章
    优先使用真实抓取，仅在配置为 mock 模式时才生成模拟数据
    """
    articles = []
    platform = vstar.platform

    # 根据平台选择抓取方法
    if platform == PlatformEnum.xueqiu.value:
        articles = _scrape_xueqiu(vstar, days_back)
    elif platform == PlatformEnum.weibo.value:
        articles = _scrape_weibo(vstar, days_back)
    elif platform == PlatformEnum.zhihu.value:
        articles = _scrape_zhihu(vstar, days_back)
    elif platform == PlatformEnum.wechat.value:
        articles = _scrape_wechat(vstar, days_back)
    elif platform in (PlatformEnum.eastmoney.value, PlatformEnum.tonghuashun.value):
        articles = _scrape_eastmoney(vstar, days_back)

    # 仅在明确启用 mock 模式时才生成模拟数据，否则如实报告抓取结果
    if not articles:
        if settings.USE_MOCK_DATA:
            print(f"[INFO] 大V '{vstar.nickname}' ({platform}) 无法获取真实数据，使用动态内容（mock模式）")
            articles = generate_dynamic_articles(vstar, count=5)
        else:
            print(f"[WARN] 大V '{vstar.nickname}' ({platform}) 未抓取到任何文章，请检查大V昵称是否正确或平台是否可访问")

    # 限制返回数量
    return articles[:30]


def sync_articles_to_db(db: Session, vstar: VStar, articles: List[Dict]) -> List[Article]:
    """
    将抓取的文章同步到数据库和本地文件
    """
    created = []
    latest_time = vstar.last_article_time

    for art_data in articles:
        title = art_data.get("title", "")
        content = art_data.get("content", "")

        # 检查去重
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

    # 同步到本地 JSON 文件
    save_articles_to_local(vstar.nickname, vstar.platform, articles)

    return created


def scrape_and_persist(vstar: VStar, db: Session) -> int:
    """
    一站式操作：抓取 + 入库 + 本地存储
    返回新文章数量
    """
    articles = fetch_articles_for_vstar(vstar)
    if not articles:
        return 0
    created = sync_articles_to_db(db, vstar, articles)
    return len(created)


# ========================================================================
#  各平台抓取实现
# ========================================================================

def _scrape_xueqiu(vstar: VStar, days_back: int) -> List[Dict]:
    """雪球用户文章抓取"""
    articles = []
    try:
        headers = {
            "User-Agent": get_random_ua(),
            "Accept": "application/json, text/plain, */*",
            "Referer": "https://xueqiu.com/",
        }
        session = requests.Session()
        session.get("https://xueqiu.com/", headers=headers, timeout=15)
        _random_delay()

        # 先搜索用户获取 user_id
        search_url = "https://xueqiu.com/statuses/search.json"
        params = {"q": vstar.nickname, "count": 5, "page": 1}
        resp = session.get(search_url, params=params, headers=headers, timeout=15)

        if resp.status_code == 200:
            data = resp.json()
            # 从搜索结果中获取用户信息
            for item in data.get("list", []):
                user = item.get("user", {})
                screen_name = user.get("screen_name", "")
                if screen_name == vstar.nickname:
                    articles = _fetch_xueqiu_timeline(session, user.get("id"), vstar, headers)
                    if articles:
                        break

        if not articles:
            print(f"[WARN] 雪球未找到用户或用户无文章: {vstar.nickname}")
    except Exception as e:
        print(f"[WARN] 雪球抓取失败 ({vstar.nickname}): {e}")

    return articles


def _fetch_xueqiu_timeline(session, user_id, vstar, headers) -> List[Dict]:
    """获取雪球用户时间线"""
    articles = []
    try:
        url = f"https://xueqiu.com/v4/statuses/user_timeline.json"
        params = {"user_id": user_id, "type": 0, "count": 20}
        resp = session.get(url, params=params, headers=headers, timeout=15)
        if resp.status_code == 200:
            data = resp.json()
            for status in data.get("statuses", []):
                title = (status.get("title") or status.get("description") or
                         (status.get("text", "") or "")[:80])
                text = status.get("text", "")
                if not text:
                    continue
                created_at = status.get("created_at", 0)
                pub_time = datetime.fromtimestamp(created_at / 1000) if created_at else datetime.utcnow()
                articles.append({
                    "title": title or text[:80],
                    "content": text,
                    "summary": text[:200],
                    "url": f"https://xueqiu.com{status.get('target', '')}",
                    "platform": "雪球",
                    "published_at": pub_time,
                    "source_hash": get_content_hash(title, text),
                })
    except Exception as e:
        print(f"[DEBUG] 获取雪球时间线失败: {e}")
    return articles


def _scrape_zhihu(vstar: VStar, days_back: int) -> List[Dict]:
    """知乎回答/文章抓取（通过知乎API）"""
    articles = []
    nickname = vstar.nickname
    try:
        headers = {
            "User-Agent": get_random_ua(),
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "zh-CN,zh;q=0.9",
            "Referer": "https://www.zhihu.com/",
            "x-requested-with": "fetch",
        }
        session = requests.Session()
        session.headers.update(headers)

        # 先获取 cookie
        session.get("https://www.zhihu.com/", timeout=15)
        _random_delay()

        # 搜索用户
        search_url = "https://www.zhihu.com/api/v4/search_v3"
        params = {
            "q": nickname,
            "t": "people",
            "limit": 5,
            "offset": 0,
        }
        resp = session.get(search_url, params=params, timeout=15)
        if resp.status_code != 200:
            return articles

        data = resp.json()
        user_token = None
        for item in data.get("data", []):
            obj = item.get("object", {})
            if obj.get("name") == nickname or obj.get("url_token") == nickname:
                user_token = obj.get("url_token") or obj.get("id")
                break

        if not user_token:
            # 尝试直接用昵称作为 url_token
            user_token = nickname

        _random_delay()

        # 获取用户活动
        activities_url = f"https://www.zhihu.com/api/v4/members/{user_token}/activities"
        params = {"limit": 20, "after_id": 0}
        resp = session.get(activities_url, params=params, timeout=15)
        if resp.status_code != 200:
            return articles

        data = resp.json()
        now = datetime.utcnow()
        cutoff = now - timedelta(days=days_back)

        for item in data.get("data", []):
            try:
                target = item.get("target", {})
                action = item.get("action_text", "")
                created_ts = item.get("created_time") or target.get("created_time") or 0
                pub_time = datetime.fromtimestamp(created_ts) if created_ts else now

                if pub_time < cutoff:
                    continue

                # 回答
                if "answer" in item.get("verb", ""):
                    title = target.get("question", {}).get("title", "")
                    content = target.get("excerpt", "") or target.get("content", "")
                    url = f"https://www.zhihu.com/question/{target.get('question', {}).get('id', '')}/answer/{target.get('id', '')}"
                # 文章
                elif "article" in item.get("verb", ""):
                    title = target.get("title", "")
                    content = target.get("excerpt", "") or target.get("content", "")
                    url = f"https://zhuanlan.zhihu.com/p/{target.get('id', '')}"
                # 想法
                elif "pin" in item.get("verb", ""):
                    title = (target.get("excerpt", "") or target.get("content", ""))[:80]
                    content = target.get("excerpt", "") or target.get("content", "")
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
                    "source_hash": get_content_hash(title, content),
                })

                if len(articles) >= 20:
                    break
            except Exception as e:
                print(f"[DEBUG] 解析知乎活动失败: {e}")
                continue

    except Exception as e:
        print(f"[WARN] 知乎抓取失败 ({nickname}): {e}")

    return articles


def _scrape_weibo(vstar: VStar, days_back: int) -> List[Dict]:
    """微博动态抓取（通过 m.weibo.cn 移动端API）"""
    articles = []
    nickname = vstar.nickname
    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 15_0 like Mac OS X) AppleWebKit/605.1.15 Mobile/15E148",
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "zh-CN,zh;q=0.9",
            "Referer": "https://m.weibo.cn/",
            "X-Requested-With": "XMLHttpRequest",
        }
        session = requests.Session()
        session.headers.update(headers)

        # 先访问首页获取 cookie
        session.get("https://m.weibo.cn/", timeout=15)
        _random_delay()

        # 搜索用户获取 uid
        search_url = "https://m.weibo.cn/api/container/getIndex"
        params = {
            "containerid": f"100103type=3&q={quote(nickname)}&t=0",
            "page_type": "searchall",
        }
        resp = session.get(search_url, params=params, timeout=15)
        if resp.status_code != 200:
            return articles

        data = resp.json()
        if data.get("ok") != 1:
            return articles

        uid = None
        # 从搜索结果中查找匹配用户的 uid
        for card in data.get("data", {}).get("cards", []):
            if card.get("card_group"):
                for group_item in card["card_group"]:
                    user_info = group_item.get("user", {})
                    if user_info.get("screen_name") == nickname:
                        uid = user_info.get("id")
                        break
            if uid:
                break

        if not uid:
            # 可能昵称不完全匹配，尝试模糊匹配
            for card in data.get("data", {}).get("cards", []):
                if card.get("card_group"):
                    for group_item in card["card_group"]:
                        user_info = group_item.get("user", {})
                        if user_info.get("screen_name", "").lower() == nickname.lower():
                            uid = user_info.get("id")
                            break
                if uid:
                    break

        if not uid:
            print(f"[WARN] 微博未找到用户: {nickname}")
            return articles

        _random_delay()

        # 获取用户微博列表
        containerid = f"107603{uid}"
        params = {
            "containerid": containerid,
            "page": 1,
        }
        resp = session.get("https://m.weibo.cn/api/container/getIndex", params=params, timeout=15)
        if resp.status_code != 200:
            return articles

        data = resp.json()
        if data.get("ok") != 1:
            return articles

        now = datetime.utcnow()
        cutoff = now - timedelta(days=days_back)

        cards = data.get("data", {}).get("cards", [])
        for card in cards:
            try:
                mblog = card.get("mblog")
                if not mblog:
                    continue

                created_at = mblog.get("created_at", "")
                # 解析微博时间格式 "Mon Jan 15 12:30:00 +0800 2024"
                pub_time = _parse_weibo_time(created_at) or now

                if pub_time < cutoff:
                    continue

                text = mblog.get("text", "")
                # 去除 HTML 标签
                text = re.sub(r'<[^>]+>', '', text)
                text = _unescape_html(text)

                title = text[:80]
                url = f"https://m.weibo.cn/detail/{mblog.get('id', '')}"
                # 转为PC端链接
                if mblog.get("id"):
                    url = f"https://weibo.com/{uid}/{mblog.get('id')}"

                if text:
                    articles.append({
                        "title": title,
                        "content": text[:5000],
                        "summary": text[:200],
                        "url": url,
                        "platform": "微博",
                        "published_at": pub_time,
                        "source_hash": get_content_hash(title, text),
                    })

                if len(articles) >= 30:
                    break
            except Exception as e:
                print(f"[DEBUG] 解析微博失败: {e}")
                continue

    except Exception as e:
        print(f"[WARN] 微博抓取失败 ({nickname}): {e}")

    return articles


def _parse_weibo_time(time_str: str) -> Optional[datetime]:
    """解析微博时间格式"""
    if not time_str:
        return None

    now = datetime.utcnow()
    time_str = time_str.strip()

    # "刚刚"
    if "刚刚" in time_str:
        return now
    # "N分钟前"
    if "分钟前" in time_str:
        try:
            minutes = int(re.search(r'(\d+)', time_str).group(1))
            return now - timedelta(minutes=minutes)
        except Exception:
            return now
    # "今天 HH:MM"
    if "今天" in time_str:
        try:
            t = re.search(r'(\d{1,2}):(\d{2})', time_str)
            if t:
                hour, minute = int(t.group(1)), int(t.group(2))
                return now.replace(hour=hour, minute=minute, second=0, microsecond=0)
        except Exception:
            pass
        return now
    # "N小时前"
    if "小时前" in time_str:
        try:
            hours = int(re.search(r'(\d+)', time_str).group(1))
            return now - timedelta(hours=hours)
        except Exception:
            return now
    # "昨天"
    if "昨天" in time_str:
        return now - timedelta(days=1)
    # "N天前"
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


def _unescape_html(text: str) -> str:
    """解码HTML实体"""
    import html
    return html.unescape(text)


def _scrape_eastmoney(vstar: VStar, days_back: int) -> List[Dict]:
    """东方财富/同花顺 股吧帖子抓取（通过东方财富API）"""
    articles = []
    nickname = vstar.nickname
    try:
        headers = {
            "User-Agent": get_random_ua(),
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "zh-CN,zh;q=0.9",
            "Referer": "https://guba.eastmoney.com/",
        }
        session = requests.Session()
        session.headers.update(headers)

        # 搜索用户
        search_url = "https://searchapi.eastmoney.com/bussiness/Web/GetCMSSearchResult"
        params = {
            "type": "8196",  # 用户搜索类型
            "pageindex": 1,
            "pagesize": 10,
            "keyword": nickname,
            "name": "zixun",
        }
        resp = session.get(search_url, params=params, timeout=15)
        if resp.status_code != 200:
            return articles

        data = resp.json()
        if data.get("IsSuccess") and data.get("Data"):
            # 从搜索结果中查找匹配用户
            user_id = None
            for item in data["Data"]:
                if isinstance(item, dict):
                    author = item.get("author", "") or item.get("userName", "") or item.get("Title", "")
                    if author == nickname or nickname in author:
                        user_id = item.get("authorUserId") or item.get("UserId") or item.get("user_id")
                        if user_id:
                            break

            if not user_id:
                print(f"[WARN] 东方财富未找到用户: {nickname}")
                return articles

            _random_delay()

            # 获取用户帖子列表
            post_url = "https://guba.eastmoney.com/interface/GetData.aspx"
            now = datetime.utcnow()
            cutoff = now - timedelta(days=days_back)

            for page in range(1, 5):
                params = {
                    "path": f"api/UserPost/GetUserPostList",
                    "userId": user_id,
                    "pageIndex": page,
                    "pageSize": 20,
                }
                resp = session.get(post_url, params=params, timeout=15)
                if resp.status_code != 200:
                    break

                try:
                    page_data = resp.json()
                except Exception:
                    break

                posts = page_data.get("Data", []) if isinstance(page_data, dict) else []
                if not posts:
                    break

                for post in posts:
                    try:
                        pub_time_str = post.get("PostDateTime") or post.get("publishDate") or ""
                        pub_time = None
                        if pub_time_str:
                            for fmt in ["%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S", "%Y/%m/%d %H:%M:%S"]:
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
                        content = post.get("Content") or post.get("content") or post.get("Body") or ""
                        post_id = post.get("Id") or post.get("id") or post.get("PostId") or ""
                        stock_code = post.get("StockCode") or post.get("stockCode") or ""

                        if not content:
                            continue

                        url = f"https://guba.eastmoney.com/news,{stock_code},{post_id}.html" if stock_code else f"https://guba.eastmoney.com/"

                        articles.append({
                            "title": title or content[:80],
                            "content": content[:5000],
                            "summary": content[:200],
                            "url": url,
                            "platform": "东方财富",
                            "published_at": pub_time,
                            "source_hash": get_content_hash(title, content),
                        })

                        if len(articles) >= 20:
                            break
                    except Exception as e:
                        print(f"[DEBUG] 解析东方财富帖子失败: {e}")
                        continue

                if len(articles) >= 20:
                    break
                _random_delay()

    except Exception as e:
        print(f"[WARN] 东方财富抓取失败 ({nickname}): {e}")

    return articles


# ========================================================================
#  Mock 数据（兼容旧接口，初始化使用）
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
    为内置示例大V生成模拟文章数据（兼容旧接口）
    同时也会为其他大V动态生成内容并保存到本地文件
    """
    created = []
    now = datetime.utcnow()
    vstar_map = {(v.nickname, v.platform): v for v in vstars}
    vstar_local_cache = {}  # vstar_id -> [article_dicts for local save]

    # 1. 处理硬编码的示例大V
    for nickname, platform, title, content, day_offset in MOCK_ARTICLES:
        vstar = vstar_map.get((nickname, platform))
        if not vstar:
            continue

        pub_time = now - timedelta(days=day_offset, hours=random.randint(0, 23))

        existing = db.query(Article).filter(
            Article.vstar_id == vstar.id,
            Article.title == title
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

    # 2. 为所有不在 MOCK_ARTICLES 中的 VStar 动态生成文章
    mock_vstar_keys = set(vstar_map.keys()) & {(n, p) for n, p, _, _, _ in MOCK_ARTICLES}
    remaining_vstars = [v for v in vstars if (v.nickname, v.platform) not in mock_vstar_keys]

    for vstar in remaining_vstars:
        existing_count = db.query(Article).filter(
            Article.vstar_id == vstar.id
        ).count()
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

    # 3. 同步到本地 JSON 文件
    for vstar_id, articles_data in vstar_local_cache.items():
        vstar = db.query(VStar).filter(VStar.id == vstar_id).first()
        if vstar:
            save_articles_to_local(vstar.nickname, vstar.platform, articles_data)

    return created
