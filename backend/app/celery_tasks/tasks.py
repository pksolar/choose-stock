"""
异步任务定义
- Redis 可用时：使用 Celery 分布式任务队列
- Redis 不可用时：使用线程池同步执行（开发/演示模式）
"""
import uuid
import threading
from datetime import datetime, timedelta
from sqlalchemy.orm import Session

from config import settings, REDIS_AVAILABLE
from app.models.database import SessionLocal, init_db
from app.models.models import (
    VStar, Article, AnalysisTask, AnalysisResult,
    StockMention, TaskStatusEnum
)
from app.services.scraper import generate_mock_articles, scrape_and_persist
from app.services.analyzer import analyze_articles, parse_time_window

# Celery 应用（仅在 Redis 可用时实际连接）
if REDIS_AVAILABLE:
    from celery import Celery
    celery_app = Celery(
        "vstock_radar",
        broker=settings.CELERY_BROKER_URL,
        backend=settings.CELERY_RESULT_BACKEND,
    )
    celery_app.conf.update(
        task_serializer="json",
        accept_content=["json"],
        result_serializer="json",
        timezone="Asia/Shanghai",
        enable_utc=True,
        task_track_started=True,
        task_time_limit=600,
    )
else:
    celery_app = None


def _execute_analysis_sync(task_id: str, time_window: str, min_mention_count: int):
    """同步执行分析任务（无 Redis 时的备选方案）"""
    db = SessionLocal()
    try:
        task = db.query(AnalysisTask).filter(AnalysisTask.id == task_id).first()
        if not task:
            task = AnalysisTask(
                id=task_id,
                status="running",
                time_window=time_window,
                min_mention_count=min_mention_count,
            )
            db.add(task)
            db.commit()
        else:
            task.status = "running"
            db.commit()

        def update_progress(progress: int):
            task.progress = progress
            db.commit()

        if settings.USE_MOCK_DATA:
            vstars = db.query(VStar).filter(VStar.is_active == True).all()
            if vstars:
                generate_mock_articles(db, vstars)

        update_progress(5)
        analyze_articles(db, task, progress_callback=update_progress)

    except Exception as e:
        db_local = SessionLocal()
        t = db_local.query(AnalysisTask).filter(AnalysisTask.id == task_id).first()
        if t:
            t.status = "failed"
            t.error_message = str(e)
            db_local.commit()
        db_local.close()
    finally:
        db.close()


def start_analysis_async(time_window: str, min_mention_count: int) -> str:
    """
    启动分析任务（自动选择 Celery 或线程模式）
    返回 task_id
    """
    task_id = str(uuid.uuid4())

    # 先在数据库中创建 pending 记录
    db = SessionLocal()
    task = AnalysisTask(
        id=task_id,
        status="pending",
        time_window=time_window,
        min_mention_count=min_mention_count,
    )
    db.add(task)
    db.commit()
    db.close()

    if REDIS_AVAILABLE and celery_app is not None:
        # Celery 异步模式
        _celery_run_full_analysis.delay(task_id, time_window, min_mention_count)
    else:
        # 线程同步模式
        t = threading.Thread(
            target=_execute_analysis_sync,
            args=(task_id, time_window, min_mention_count),
            daemon=True,
        )
        t.start()

    return task_id


# === Celery 任务定义（仅 Redis 可用时注册） ===

if REDIS_AVAILABLE and celery_app is not None:

    @celery_app.task(bind=True, name="run_full_analysis")
    def _celery_run_full_analysis(self, task_id: str, time_window: str, min_mention_count: int):
        """Celery 版本的分析任务"""
        db = SessionLocal()
        try:
            task = db.query(AnalysisTask).filter(AnalysisTask.id == task_id).first()
            if not task:
                task = AnalysisTask(
                    id=task_id, status="running",
                    time_window=time_window, min_mention_count=min_mention_count,
                )
                db.add(task)
                db.commit()
            else:
                task.status = "running"
                db.commit()

            def update_progress(progress: int):
                task.progress = progress
                db.commit()
                self.update_state(state="PROGRESS", meta={"progress": progress})

            if settings.USE_MOCK_DATA:
                vstars = db.query(VStar).filter(VStar.is_active == True).all()
                if vstars:
                    generate_mock_articles(db, vstars)

            update_progress(5)
            analyze_articles(db, task, progress_callback=update_progress)

            return {"task_id": task_id, "status": "completed", "result_summary": task.result_summary}

        except Exception as e:
            if task:
                task.status = "failed"
                task.error_message = str(e)
                db.commit()
            raise
        finally:
            db.close()

    @celery_app.task(name="scrape_single_vstar")
    def scrape_single_vstar(vstar_id: int):
        """为单个大V抓取最新文章"""
        db = SessionLocal()
        try:
            vstar = db.query(VStar).filter(VStar.id == vstar_id).first()
            if not vstar:
                return {"error": "vstar not found"}
            new_count = scrape_and_persist(vstar, db)
            return {"vstar_id": vstar_id, "new_articles": new_count, "status": "ok"}
        finally:
            db.close()

    @celery_app.task(name="cleanup_old_data")
    def cleanup_old_data(days: int = 90):
        """清理超过指定天数的旧数据"""
        db = SessionLocal()
        try:
            cutoff = datetime.utcnow() - timedelta(days=days)
            db.query(Article).filter(Article.created_at < cutoff).delete()
            db.query(StockMention).filter(StockMention.created_at < cutoff).delete()
            db.query(AnalysisTask).filter(AnalysisTask.created_at < cutoff).delete()
            db.commit()
            return {"deleted_before": str(cutoff)}
        finally:
            db.close()
