"""数据库连接和会话管理"""
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base
from config import settings

# 同步引擎（用于 Celery 任务和数据库初始化）
sync_engine = create_engine(
    settings.DATABASE_URL_SYNC,
    connect_args={"check_same_thread": False} if "sqlite" in settings.DATABASE_URL_SYNC else {},
    echo=settings.DEBUG,
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=sync_engine)

Base = declarative_base()


def init_db():
    """初始化数据库，创建所有表"""
    import app.models.models  # 确保模型被导入
    Base.metadata.create_all(bind=sync_engine)


def get_db():
    """获取数据库会话（同步）"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
