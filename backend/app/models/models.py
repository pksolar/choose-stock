"""SQLAlchemy ORM 模型定义"""
from datetime import datetime
from sqlalchemy import (
    Column, Integer, String, Float, Text, DateTime, Boolean,
    ForeignKey, Enum as SAEnum, JSON
)
from sqlalchemy.orm import relationship
from app.models.database import Base
import enum


class PlatformEnum(str, enum.Enum):
    wechat = "公众号"
    zhihu = "知乎"
    xueqiu = "雪球"
    eastmoney = "东方财富"
    tonghuashun = "同花顺"
    weibo = "微博"


class DataSourceMode(str, enum.Enum):
    auto = "auto"      # 自动抓取
    manual = "manual"  # 手动导入


class SentimentEnum(str, enum.Enum):
    positive = "positive"
    neutral = "neutral"
    negative = "negative"


class TaskStatusEnum(str, enum.Enum):
    pending = "pending"
    running = "running"
    completed = "completed"
    failed = "failed"


class VStar(Base):
    """大V 信息表"""
    __tablename__ = "vstars"

    id = Column(Integer, primary_key=True, autoincrement=True)
    nickname = Column(String(100), unique=True, nullable=False, comment="昵称")
    platform = Column(String(20), nullable=False, comment="所属平台")
    data_source_mode = Column(String(10), default="auto", comment="数据源模式: auto/manual")
    weight_coefficient = Column(Float, default=1.0, comment="权重系数")
    is_active = Column(Boolean, default=True, comment="是否启用")
    last_article_time = Column(DateTime, nullable=True, comment="上次发文时间")
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    articles = relationship("Article", back_populates="vstar", cascade="all, delete-orphan")


class Article(Base):
    """文章/内容 元数据表"""
    __tablename__ = "articles"

    id = Column(Integer, primary_key=True, autoincrement=True)
    vstar_id = Column(Integer, ForeignKey("vstars.id"), nullable=False)
    title = Column(String(500), nullable=False, comment="标题")
    content = Column(Text, nullable=True, comment="正文内容")
    summary = Column(String(1000), nullable=True, comment="摘要（取前200字）")
    url = Column(String(500), nullable=True, comment="原文链接")
    platform = Column(String(20), nullable=False)
    published_at = Column(DateTime, nullable=True, comment="发布时间")
    source_hash = Column(String(64), nullable=True, comment="内容哈希（去重用）")
    created_at = Column(DateTime, default=datetime.utcnow)

    vstar = relationship("VStar", back_populates="articles")
    mentions = relationship("StockMention", back_populates="article", cascade="all, delete-orphan")


class StockMention(Base):
    """文章中提及的股票"""
    __tablename__ = "stock_mentions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    article_id = Column(Integer, ForeignKey("articles.id"), nullable=False)
    stock_code = Column(String(10), nullable=False, comment="股票代码")
    stock_name = Column(String(50), nullable=True, comment="股票名称")
    mentioned_text = Column(Text, nullable=True, comment="提及该股票的上下文（前后50字）")
    sentiment = Column(String(10), nullable=True, comment="情感: positive/neutral/negative")
    sentiment_score = Column(Float, nullable=True, comment="情感得分 0~1")
    created_at = Column(DateTime, default=datetime.utcnow)

    article = relationship("Article", back_populates="mentions")
    analysis_results = relationship("AnalysisResult", back_populates="mention")


class AnalysisTask(Base):
    """分析任务记录"""
    __tablename__ = "analysis_tasks"

    id = Column(String(36), primary_key=True, comment="任务ID (UUID)")
    status = Column(String(20), default="pending", comment="pending/running/completed/failed")
    time_window = Column(String(10), nullable=False, comment="时间窗口: 3d/1w/1m")
    min_mention_count = Column(Integer, default=3, comment="最低提及人数")
    progress = Column(Integer, default=0, comment="进度 0~100")
    error_message = Column(Text, nullable=True)
    result_summary = Column(JSON, nullable=True, comment="结果摘要")
    created_at = Column(DateTime, default=datetime.utcnow)
    completed_at = Column(DateTime, nullable=True)

    results = relationship("AnalysisResult", back_populates="task", cascade="all, delete-orphan")


class AnalysisResult(Base):
    """分析结果明细"""
    __tablename__ = "analysis_results"

    id = Column(Integer, primary_key=True, autoincrement=True)
    task_id = Column(String(36), ForeignKey("analysis_tasks.id"), nullable=False)
    mention_id = Column(Integer, ForeignKey("stock_mentions.id"), nullable=True)
    stock_code = Column(String(10), nullable=False)
    stock_name = Column(String(50), nullable=True)
    mention_count = Column(Integer, default=0, comment="提及人数")
    total_mentions = Column(Integer, default=0, comment="总提及次数")
    positive_count = Column(Integer, default=0, comment="正向提及数")
    neutral_count = Column(Integer, default=0)
    negative_count = Column(Integer, default=0)
    hotness_score = Column(Float, default=0.0, comment="热度分数")
    first_mention_time = Column(DateTime, nullable=True, comment="首次达到阈值的时间")
    created_at = Column(DateTime, default=datetime.utcnow)

    task = relationship("AnalysisTask", back_populates="results")
    mention = relationship("StockMention", back_populates="analysis_results")


class StockInfo(Base):
    """A股股票基本信息缓存表"""
    __tablename__ = "stock_info"

    id = Column(Integer, primary_key=True, autoincrement=True)
    stock_code = Column(String(10), unique=True, nullable=False, comment="6位代码")
    stock_name = Column(String(50), nullable=False, comment="股票名称")
    market = Column(String(10), nullable=True, comment="市场: SH/SZ")
    industry = Column(String(50), nullable=True, comment="所属行业")
    created_at = Column(DateTime, default=datetime.utcnow)


class PlatformCredential(Base):
    """平台账号凭据表"""
    __tablename__ = "platform_credentials"

    id = Column(Integer, primary_key=True, autoincrement=True)
    platform = Column(String(20), unique=True, nullable=False, comment="平台名称")
    username = Column(String(100), nullable=True, comment="账号/手机号/邮箱")
    password = Column(String(200), nullable=True, comment="密码")
    cookies_json = Column(Text, nullable=True, comment="持久化 Cookie（JSON）")
    is_active = Column(Boolean, default=True, comment="是否启用")
    last_login_at = Column(DateTime, nullable=True, comment="上次登录时间")
    login_status = Column(String(20), default="unknown", comment="登录状态: unknown/success/failed")
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
