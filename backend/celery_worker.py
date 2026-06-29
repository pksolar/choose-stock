"""
Celery Worker 启动入口
使用方法: celery -A celery_worker worker --loglevel=info --concurrency=4
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from app.celery_tasks.tasks import celery_app

if __name__ == "__main__":
    celery_app.start()
