"""
任务调度 — 基于线程池的后台执行
"""
import uuid
import threading
from datetime import datetime

from sqlalchemy.orm import Session

from app.models.database import SessionLocal
from app.models.models import AnalysisTask, VStar
from app.services.scraper import generate_mock_articles
from app.services.analyzer import analyze_articles


def _execute_analysis_sync(task_id: str, time_window: str, min_mention_count: int):
    """在后台线程中执行分析任务"""
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
            try:
                task.progress = progress
                db.commit()
            except Exception:
                pass

        if settings.USE_MOCK_DATA:
            vstars = db.query(VStar).filter(VStar.is_active.is_(True)).all()
            if vstars:
                generate_mock_articles(db, vstars)

        update_progress(5)
        analyze_articles(db, task, progress_callback=update_progress)

    except Exception as e:
        try:
            db_local = SessionLocal()
            t = db_local.query(AnalysisTask).filter(AnalysisTask.id == task_id).first()
            if t:
                t.status = "failed"
                t.error_message = str(e)
                db_local.commit()
            db_local.close()
        except Exception:
            pass
    finally:
        db.close()


def start_analysis_async(time_window: str, min_mention_count: int) -> str:
    """启动分析任务（后台线程），返回 task_id"""
    task_id = str(uuid.uuid4())

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

    t = threading.Thread(
        target=_execute_analysis_sync,
        args=(task_id, time_window, min_mention_count),
        daemon=True,
    )
    t.start()

    return task_id


# 延迟 import 避免循环依赖
from config import settings
