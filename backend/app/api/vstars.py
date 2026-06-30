"""大V管理 API 路由"""
from datetime import datetime, timedelta
from typing import List
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from sqlalchemy.orm import Session

from app.models.database import get_db, SessionLocal
from app.models.models import VStar, Article, PlatformEnum
from app.schemas.schemas import VStarCreate, VStarUpdate, VStarResponse, APIResponse
from app.services.scraper import scrape_and_persist

router = APIRouter(prefix="/api/vstars", tags=["大V管理"])


def _background_scrape(vstar_id: int):
    """后台抓取任务，使用独立的数据库会话"""
    db = SessionLocal()
    try:
        vstar = db.query(VStar).filter(VStar.id == vstar_id).first()
        if vstar:
            count = scrape_and_persist(vstar, db)
            print(f"[BG] 后台抓取完成: '{vstar.nickname}' 新增 {count} 篇")
    except Exception as e:
        print(f"[BG] 后台抓取失败 (vstar_id={vstar_id}): {e}")
    finally:
        db.close()


@router.get("/", response_model=List[dict])
def list_vstars(db: Session = Depends(get_db)):
    """获取大V列表"""
    vstars = db.query(VStar).order_by(VStar.created_at.desc()).all()
    result = []
    stale_threshold = datetime.utcnow() - timedelta(days=7)

    for v in vstars:
        is_stale = (
            v.last_article_time is None
            or v.last_article_time < stale_threshold
        )
        article_count = db.query(Article).filter(Article.vstar_id == v.id).count()
        latest_articles = (
            db.query(Article)
            .filter(Article.vstar_id == v.id)
            .order_by(Article.published_at.desc().nullslast())
            .limit(3)
            .all()
        )
        result.append({
            "id": v.id,
            "nickname": v.nickname,
            "platform": v.platform,
            "data_source_mode": v.data_source_mode,
            "weight_coefficient": v.weight_coefficient,
            "is_active": v.is_active,
            "last_article_time": v.last_article_time.isoformat() if v.last_article_time else None,
            "is_stale": is_stale,
            "article_count": article_count,
            "latest_articles": [
                {
                    "id": a.id,
                    "title": a.title,
                    "published_at": a.published_at.isoformat() if a.published_at else None,
                }
                for a in latest_articles
            ],
            "created_at": v.created_at.isoformat() if v.created_at else None,
            "updated_at": v.updated_at.isoformat() if v.updated_at else None,
        })

    return result


@router.post("/", response_model=VStarResponse)
def create_vstar(data: VStarCreate, background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
    """添加大V（后台自动抓取文章）"""
    # 验证平台
    valid_platforms = [p.value for p in PlatformEnum]
    if data.platform not in valid_platforms:
        raise HTTPException(status_code=400, detail=f"平台必须是: {valid_platforms}")

    # 检查昵称唯一性
    existing = db.query(VStar).filter(VStar.nickname == data.nickname).first()
    if existing:
        raise HTTPException(status_code=400, detail=f"大V '{data.nickname}' 已存在")

    vstar = VStar(
        nickname=data.nickname,
        platform=data.platform,
        data_source_mode=data.data_source_mode,
        weight_coefficient=data.weight_coefficient,
    )
    db.add(vstar)
    db.commit()
    db.refresh(vstar)

    # 后台自动抓取文章（非阻塞）
    if data.data_source_mode == "auto":
        background_tasks.add_task(_background_scrape, vstar.id)

    stale_threshold = datetime.utcnow() - timedelta(days=7)
    return VStarResponse(
        id=vstar.id,
        nickname=vstar.nickname,
        platform=vstar.platform,
        data_source_mode=vstar.data_source_mode,
        weight_coefficient=vstar.weight_coefficient,
        is_active=vstar.is_active,
        last_article_time=vstar.last_article_time,
        is_stale=vstar.last_article_time is None or vstar.last_article_time < stale_threshold,
        created_at=vstar.created_at,
        updated_at=vstar.updated_at,
    )


@router.put("/{vstar_id}", response_model=VStarResponse)
def update_vstar(vstar_id: int, data: VStarUpdate, db: Session = Depends(get_db)):
    """更新大V信息"""
    vstar = db.query(VStar).filter(VStar.id == vstar_id).first()
    if not vstar:
        raise HTTPException(status_code=404, detail="大V不存在")

    if data.nickname is not None:
        existing = db.query(VStar).filter(
            VStar.nickname == data.nickname, VStar.id != vstar_id
        ).first()
        if existing:
            raise HTTPException(status_code=400, detail="昵称已被占用")
        vstar.nickname = data.nickname
    if data.platform is not None:
        vstar.platform = data.platform
    if data.data_source_mode is not None:
        vstar.data_source_mode = data.data_source_mode
    if data.weight_coefficient is not None:
        vstar.weight_coefficient = data.weight_coefficient
    if data.is_active is not None:
        vstar.is_active = data.is_active

    db.commit()
    db.refresh(vstar)

    stale_threshold = datetime.utcnow() - timedelta(days=7)
    return VStarResponse(
        id=vstar.id,
        nickname=vstar.nickname,
        platform=vstar.platform,
        data_source_mode=vstar.data_source_mode,
        weight_coefficient=vstar.weight_coefficient,
        is_active=vstar.is_active,
        last_article_time=vstar.last_article_time,
        is_stale=vstar.last_article_time is None or vstar.last_article_time < stale_threshold,
        created_at=vstar.created_at,
        updated_at=vstar.updated_at,
    )


@router.delete("/{vstar_id}")
def delete_vstar(vstar_id: int, db: Session = Depends(get_db)):
    """删除大V"""
    vstar = db.query(VStar).filter(VStar.id == vstar_id).first()
    if not vstar:
        raise HTTPException(status_code=404, detail="大V不存在")
    db.delete(vstar)
    db.commit()
    return {"success": True, "message": f"已删除大V: {vstar.nickname}"}


@router.post("/{vstar_id}/refresh")
def refresh_vstar(vstar_id: int, background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
    """手动刷新指定大V的文章数据（后台抓取+入库+本地存储）"""
    vstar = db.query(VStar).filter(VStar.id == vstar_id).first()
    if not vstar:
        raise HTTPException(status_code=404, detail="大V不存在")

    background_tasks.add_task(_background_scrape, vstar.id)
    article_count = db.query(Article).filter(Article.vstar_id == vstar.id).count()

    return {
        "success": True,
        "message": f"刷新任务已启动，将在后台进行",
        "total_articles": article_count,
        "last_article_time": vstar.last_article_time.isoformat() if vstar.last_article_time else None,
    }


@router.get("/{vstar_id}/articles")
def get_vstar_articles(vstar_id: int, db: Session = Depends(get_db)):
    """获取指定大V的所有文章"""
    vstar = db.query(VStar).filter(VStar.id == vstar_id).first()
    if not vstar:
        raise HTTPException(status_code=404, detail="大V不存在")

    articles = (
        db.query(Article)
        .filter(Article.vstar_id == vstar_id)
        .order_by(Article.published_at.desc().nullslast())
        .all()
    )
    return {
        "vstar": {"id": vstar.id, "nickname": vstar.nickname, "platform": vstar.platform},
        "total": len(articles),
        "articles": [
            {
                "id": a.id,
                "title": a.title,
                "summary": a.summary,
                "content": a.content,
                "url": a.url,
                "published_at": a.published_at.isoformat() if a.published_at else None,
                "created_at": a.created_at.isoformat() if a.created_at else None,
            }
            for a in articles
        ],
    }


@router.get("/platforms")
def get_platforms():
    """获取可用平台列表"""
    return [{"value": p.value, "label": p.value} for p in PlatformEnum]
