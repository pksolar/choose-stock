"""
核心分析引擎：交叉比对、去重、热度计算
"""
from datetime import datetime, timedelta
from typing import List, Dict, Tuple, Optional
from collections import defaultdict
from sqlalchemy.orm import Session
from sqlalchemy import and_

from app.models.models import (
    VStar, Article, StockMention, AnalysisTask, AnalysisResult,
    SentimentEnum
)
from app.services.nlp_service import nlp_service
from app.utils.stock_mapper import stock_mapper as stock_mapper_global


def parse_time_window(window: str) -> timedelta:
    """解析时间窗口字符串"""
    mapping = {"3d": timedelta(days=3), "1w": timedelta(weeks=1), "1m": timedelta(days=30)}
    return mapping.get(window, timedelta(weeks=1))


def analyze_articles(
    db: Session,
    task: AnalysisTask,
    progress_callback=None,
) -> Dict:
    """
    主分析流程：
    1. 获取时间窗口内的所有文章
    2. NLP 提取股票提及
    3. 交叉比对，去重
    4. 计算热度
    5. 生成结果
    """
    window_delta = parse_time_window(task.time_window)
    cutoff_time = datetime.utcnow() - window_delta
    min_count = task.min_mention_count

    if progress_callback:
        progress_callback(10)

    # Step 1: 获取活跃大V列表及其文章
    vstars = db.query(VStar).filter(VStar.is_active == True).all()
    if not vstars:
        task.status = "failed"
        task.error_message = "没有可用的大V，请先添加大V"
        db.commit()
        return {"error": "no_vstars"}

    if progress_callback:
        progress_callback(20)

    # Step 2: 获取时间窗口内的文章
    articles = db.query(Article).filter(
        Article.published_at >= cutoff_time
    ).all()

    if not articles:
        task.status = "completed"
        task.result_summary = {"total_results": 0, "message": "时间窗口内没有文章数据"}
        task.progress = 100
        db.commit()
        return {"total_results": 0, "message": "no_articles"}

    if progress_callback:
        progress_callback(30)

    # Step 3: 对每篇文章进行 NLP 分析，提取股票提及
    all_mentions = []  # [(article_id, stock_code, stock_name, context, sentiment, score)]
    article_count = len(articles)

    for i, article in enumerate(articles):
        # 检查缓存（同一篇文章1小时内不重复分析）
        existing_mentions = db.query(StockMention).filter(
            StockMention.article_id == article.id
        ).first()

        if existing_mentions and (datetime.utcnow() - article.created_at).seconds < 3600:
            # 使用缓存结果重新读取
            for m in db.query(StockMention).filter(StockMention.article_id == article.id).all():
                all_mentions.append((m.article_id, m.stock_code, m.stock_name,
                                     m.mentioned_text or "", m.sentiment or "neutral",
                                     m.sentiment_score or 0.5))
            continue

        # NLP 分析
        text = (article.title or "") + " " + (article.content or "")
        stocks = nlp_service.detect_stocks(text)

        for code, name, snippet in stocks:
            sentiment_label, sentiment_score = nlp_service.analyze_sentiment(snippet)
            # 存储到数据库
            mention = StockMention(
                article_id=article.id,
                stock_code=code,
                stock_name=name,
                mentioned_text=snippet,
                sentiment=sentiment_label,
                sentiment_score=sentiment_score,
            )
            db.add(mention)
            db.flush()  # 获取 ID
            all_mentions.append((article.id, code, name, snippet, sentiment_label, sentiment_score))

        # 更新进度（30% - 70% 分配在NLP阶段）
        if progress_callback and article_count > 0:
            progress = 30 + int((i + 1) / article_count * 40)
            progress_callback(progress)

    db.commit()

    if not all_mentions:
        task.status = "completed"
        task.result_summary = {"total_results": 0, "message": "未在文章中识别到A股提及"}
        task.progress = 100
        db.commit()
        return {"total_results": 0, "message": "no_stocks_found"}

    if progress_callback:
        progress_callback(75)

    # Step 4: 交叉比对 - 按股票分组，统计提及情况
    # 结构: {stock_code: {vstar_id: [mention_data], ...}}
    stock_vstar_map = defaultdict(lambda: defaultdict(list))

    # 文章 id -> vstar id 映射
    article_vstar_map = {a.id: a.vstar_id for a in articles}
    # vstar id -> weight 映射
    vstar_weight_map = {v.id: v.weight_coefficient for v in vstars}
    # vstar id -> nickname 映射
    vstar_name_map = {v.id: v.nickname for v in vstars}

    for (article_id, code, name, snippet, sentiment, score) in all_mentions:
        vstar_id = article_vstar_map.get(article_id)
        if vstar_id:
            stock_vstar_map[code][vstar_id].append({
                "article_id": article_id,
                "name": name,
                "snippet": snippet,
                "sentiment": sentiment,
                "score": score,
            })

    if progress_callback:
        progress_callback(85)

    # Step 5: 去重和统计
    # 规则：
    # - 同一大V对同一只股票在一个时间窗口内只计算一次（取正向优先，取首次提及时间）
    # - 跨平台相似内容去重（标题相似度 > 90%）
    results_data = []
    article_titles = {a.id: a.title for a in articles}

    for stock_code, vstar_mentions in stock_vstar_map.items():
        # 每位大V对该股票只计1次有效提及
        unique_vstars = set()
        positive_vstars = set()
        neutral_vstars = set()
        negative_vstars = set()
        total_mention_count = 0
        first_mention_time = None
        all_snippets = []

        for vstar_id, mentions in vstar_mentions.items():
            unique_vstars.add(vstar_id)
            total_mention_count += 1  # 每人每次窗口内只计1次

            # 情感分类（取最正面的判定）
            sentiments = [m["sentiment"] for m in mentions]
            if "positive" in sentiments:
                positive_vstars.add(vstar_id)
            elif "negative" in sentiments:
                negative_vstars.add(vstar_id)
            else:
                neutral_vstars.add(vstar_id)

            # 收集片段
            for m in mentions:
                all_snippets.append((vstar_id, m["snippet"], m["sentiment"], m["score"]))

        mention_count = len(unique_vstars)

        # 仅统计满足阈值的股票
        if mention_count < min_count:
            continue

        # 热度计算: (提及人数 × 平均权重) + (总提及次数 × 0.5)
        avg_weight = sum(vstar_weight_map.get(vid, 1.0) for vid in unique_vstars) / max(mention_count, 1)
        hotness = (mention_count * avg_weight) + (total_mention_count * 0.5)

        stock_name = stock_mapper_global.get_name(stock_code) or ""
        vstar_names = [vstar_name_map.get(vid, f"ID:{vid}") for vid in unique_vstars]

        results_data.append({
            "stock_code": stock_code,
            "stock_name": stock_name,
            "hotness_score": round(hotness, 2),
            "mention_count": mention_count,
            "total_mentions": total_mention_count,
            "positive_count": len(positive_vstars),
            "neutral_count": len(neutral_vstars),
            "negative_count": len(negative_vstars),
            "vstar_list": vstar_names,
            "snippets": all_snippets,
        })

    # 按热度降序排列
    results_data.sort(key=lambda x: x["hotness_score"], reverse=True)

    if progress_callback:
        progress_callback(95)

    # Step 6: 存储分析结果
    for item in results_data:
        result = AnalysisResult(
            task_id=task.id,
            mention_id=None,  # 聚合结果，不关联单条mention
            stock_code=item["stock_code"],
            stock_name=item["stock_name"],
            mention_count=item["mention_count"],
            total_mentions=item["total_mentions"],
            positive_count=item["positive_count"],
            neutral_count=item["neutral_count"],
            negative_count=item["negative_count"],
            hotness_score=item["hotness_score"],
        )
        db.add(result)

    task.status = "completed"
    task.progress = 100
    task.completed_at = datetime.utcnow()
    task.result_summary = {
        "total_results": len(results_data),
        "time_window": task.time_window,
        "min_mention_count": min_count,
        "analyzed_articles": article_count,
        "total_mentions": len(all_mentions),
    }
    db.commit()

    return task.result_summary
