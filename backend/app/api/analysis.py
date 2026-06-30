"""分析任务 API 路由"""
import json
from datetime import datetime
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
from sqlalchemy import desc

from app.models.database import get_db
from app.models.models import AnalysisTask, AnalysisResult, StockMention, Article, VStar
from app.schemas.schemas import (
    AnalysisRequest, TaskStatusResponse, StockResultItem,
    StockDetailResponse, MentionDetail, APIResponse, ManualArticleInput,
)
from app.celery_tasks.tasks import start_analysis_async
from app.services.scraper import load_articles_from_local, ARTICLES_DATA_DIR

router = APIRouter(prefix="/api/analysis", tags=["分析任务"])


@router.post("/start", response_model=TaskStatusResponse)
def start_analysis(req: AnalysisRequest, db: Session = Depends(get_db)):
    """启动分析任务（异步）"""
    # 验证时间窗口
    valid_windows = ["3d", "1w", "1m"]
    if req.time_window not in valid_windows:
        raise HTTPException(status_code=400, detail=f"时间窗口必须是: {valid_windows}")

    # 启动异步任务（自动选择 Celery 或线程模式）
    task_id = start_analysis_async(req.time_window, req.min_mention_count)

    return TaskStatusResponse(
        task_id=task_id,
        status="pending",
        progress=0,
        created_at=datetime.utcnow(),
    )


@router.get("/task/{task_id}", response_model=TaskStatusResponse)
def get_task_status(task_id: str, db: Session = Depends(get_db)):
    """查询任务状态"""
    task = db.query(AnalysisTask).filter(AnalysisTask.id == task_id).first()

    if not task:
        return TaskStatusResponse(
            task_id=task_id,
            status="unknown",
            progress=0,
            error_message="任务不存在",
            created_at=datetime.utcnow(),
        )

    return TaskStatusResponse(
        task_id=task.id,
        status=task.status,
        progress=task.progress or 0,
        error_message=task.error_message,
        result_summary=task.result_summary,
        created_at=task.created_at,
        completed_at=task.completed_at,
    )


@router.get("/results/{task_id}", response_model=List[StockResultItem])
def get_analysis_results(task_id: str, db: Session = Depends(get_db)):
    """获取分析结果榜单"""
    from app.services.analyzer import parse_time_window

    task = db.query(AnalysisTask).filter(AnalysisTask.id == task_id).first()
    if not task:
        return []

    results = (
        db.query(AnalysisResult)
        .filter(AnalysisResult.task_id == task_id)
        .order_by(desc(AnalysisResult.hotness_score))
        .all()
    )

    if not results:
        return []

    # Compute cutoff from the task's time window
    cutoff = task.created_at - parse_time_window(task.time_window) if task.created_at else datetime.utcnow()

    # Collect all article_ids via mentions for the relevant stocks
    stock_codes = [r.stock_code for r in results]
    mentions = (
        db.query(StockMention)
        .join(Article)
        .filter(
            StockMention.stock_code.in_(stock_codes),
            Article.published_at >= cutoff,
        )
        .all()
    )

    # Build article_id -> vstar lookup (single batch)
    article_ids = list({m.article_id for m in mentions})
    articles_map = {}
    if article_ids:
        articles = (
            db.query(Article)
            .filter(Article.id.in_(article_ids))
            .all()
        )
        vstar_ids = list({a.vstar_id for a in articles})
        vstars_map = {}
        if vstar_ids:
            vstars = db.query(VStar).filter(VStar.id.in_(vstar_ids)).all()
            vstars_map = {v.id: v for v in vstars}
        articles_map = {a.id: a for a in articles}

    # Group mentions by stock_code
    mention_vstars = {}
    for m in mentions:
        article = articles_map.get(m.article_id)
        if article and article.vstar:
            mention_vstars.setdefault(m.stock_code, set()).add(article.vstar.nickname)

    output = []
    for r in results:
        vstar_list = list(mention_vstars.get(r.stock_code, set()))[:10]
        output.append(StockResultItem(
            stock_code=r.stock_code,
            stock_name=r.stock_name or "",
            hotness_score=r.hotness_score,
            mention_count=r.mention_count,
            total_mentions=r.total_mentions,
            positive_count=r.positive_count,
            neutral_count=r.neutral_count,
            negative_count=r.negative_count,
            first_mention_time=r.first_mention_time,
            vstar_list=vstar_list,
        ))

    return output


@router.get("/stock-detail/{task_id}/{stock_code}", response_model=StockDetailResponse)
def get_stock_detail(task_id: str, stock_code: str, db: Session = Depends(get_db)):
    """获取个股详情（证据链）"""
    result = (
        db.query(AnalysisResult)
        .filter(
            AnalysisResult.task_id == task_id,
            AnalysisResult.stock_code == stock_code,
        )
        .first()
    )

    if not result:
        raise HTTPException(status_code=404, detail="未找到该股票的分析结果")

    # 查找所有相关mention，并 eager-load article + vstar
    mentions = (
        db.query(StockMention)
        .filter(StockMention.stock_code == stock_code)
        .all()
    )

    article_ids = list({m.article_id for m in mentions})
    articles_map = {}
    vstars_map = {}
    if article_ids:
        articles = (
            db.query(Article)
            .filter(Article.id.in_(article_ids))
            .all()
        )
        articles_map = {a.id: a for a in articles}
        vstar_ids = list({a.vstar_id for a in articles})
        if vstar_ids:
            vstars = db.query(VStar).filter(VStar.id.in_(vstar_ids)).all()
            vstars_map = {v.id: v for v in vstars}

    evidence_chain = []
    vstar_set = set()

    for m in mentions:
        article = articles_map.get(m.article_id)
        if not article:
            continue

        vstar = vstars_map.get(article.vstar_id)
        vstar_nickname = vstar.nickname if vstar else "未知"
        vstar_platform = vstar.platform if vstar else ""

        vstar_set.add(vstar_nickname)

        evidence_chain.append(MentionDetail(
            vstar_nickname=vstar_nickname,
            vstar_platform=vstar_platform,
            article_title=article.title,
            article_url=article.url,
            mentioned_text=m.mentioned_text or article.summary or "",
            sentiment=m.sentiment or "neutral",
            sentiment_score=m.sentiment_score or 0.5,
            published_at=article.published_at,
        ))

    return StockDetailResponse(
        stock_code=result.stock_code,
        stock_name=result.stock_name or "",
        hotness_score=result.hotness_score,
        mention_count=result.mention_count,
        total_mentions=result.total_mentions,
        positive_count=result.positive_count,
        neutral_count=result.neutral_count,
        negative_count=result.negative_count,
        first_mention_time=result.first_mention_time,
        vstar_list=list(vstar_set),
        evidence_chain=evidence_chain,
    )


@router.post("/manual-article")
def submit_manual_article(data: ManualArticleInput, db: Session = Depends(get_db)):
    """手动导入文章"""
    vstar = db.query(VStar).filter(VStar.id == data.vstar_id).first()
    if not vstar:
        raise HTTPException(status_code=404, detail="大V不存在")

    article = Article(
        vstar_id=data.vstar_id,
        title=data.title,
        content=data.content,
        summary=data.content[:200] if data.content else "",
        url=data.url,
        platform=vstar.platform,
        published_at=data.published_at or datetime.utcnow(),
    )
    db.add(article)
    db.commit()
    db.refresh(article)

    return {"success": True, "article_id": article.id, "message": "文章已提交"}


@router.get("/articles/export")
def export_articles(db: Session = Depends(get_db)):
    """导出所有文章为 JSON（用于本地保存）"""
    articles = (
        db.query(Article)
        .order_by(Article.published_at.desc().nullslast())
        .all()
    )
    data = []
    for a in articles:
        vstar = db.query(VStar).filter(VStar.id == a.vstar_id).first()
        data.append({
            "id": a.id,
            "vstar_nickname": vstar.nickname if vstar else "未知",
            "vstar_platform": vstar.platform if vstar else "",
            "title": a.title,
            "content": a.content,
            "summary": a.summary,
            "url": a.url,
            "platform": a.platform,
            "published_at": a.published_at.isoformat() if a.published_at else None,
            "created_at": a.created_at.isoformat() if a.created_at else None,
        })

    return JSONResponse(content={
        "total": len(data),
        "export_time": datetime.utcnow().isoformat(),
        "articles": data,
    })


@router.get("/articles/list")
def list_all_articles(
    page: int = 1,
    page_size: int = 20,
    vstar_id: Optional[int] = None,
    platform: Optional[str] = None,
    db: Session = Depends(get_db),
):
    """分页查询所有文章"""
    q = db.query(Article)
    if vstar_id:
        q = q.filter(Article.vstar_id == vstar_id)
    if platform:
        q = q.filter(Article.platform == platform)

    total = q.count()
    articles = (
        q.order_by(Article.published_at.desc().nullslast())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )

    return {
        "total": total,
        "page": page,
        "page_size": page_size,
        "articles": [
            {
                "id": a.id,
                "vstar_id": a.vstar_id,
                "title": a.title,
                "summary": a.summary,
                "url": a.url,
                "platform": a.platform,
                "published_at": a.published_at.isoformat() if a.published_at else None,
            }
            for a in articles
        ],
    }


@router.get("/articles/local-files")
def get_local_article_files():
    """列出本地保存的文章文件"""
    files = []
    if ARTICLES_DATA_DIR.exists():
        for f in ARTICLES_DATA_DIR.glob("*.json"):
            try:
                with open(f, "r", encoding="utf-8") as fp:
                    data = json.load(fp)
                files.append({
                    "filename": f.name,
                    "article_count": len(data) if isinstance(data, list) else 0,
                    "size_bytes": f.stat().st_size,
                })
            except Exception:
                files.append({"filename": f.name, "article_count": 0, "size_bytes": f.stat().st_size})
    return {"total_files": len(files), "files": files}
