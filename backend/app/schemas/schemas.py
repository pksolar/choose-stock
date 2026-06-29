"""Pydantic 数据校验模型"""
from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel, Field


# ===== 大V 管理 =====

class VStarCreate(BaseModel):
    nickname: str = Field(..., min_length=1, max_length=100, description="昵称")
    platform: str = Field(..., description="平台: 公众号/知乎/雪球/东方财富/同花顺/微博")
    data_source_mode: str = Field(default="auto", description="auto/manual")
    weight_coefficient: float = Field(default=1.0, ge=0.1, le=5.0, description="权重系数")


class VStarUpdate(BaseModel):
    nickname: Optional[str] = None
    platform: Optional[str] = None
    data_source_mode: Optional[str] = None
    weight_coefficient: Optional[float] = None
    is_active: Optional[bool] = None


class VStarResponse(BaseModel):
    id: int
    nickname: str
    platform: str
    data_source_mode: str
    weight_coefficient: float
    is_active: bool
    last_article_time: Optional[datetime] = None
    is_stale: bool = False  # 超过7天未更新
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


# ===== 文章 =====

class ManualArticleInput(BaseModel):
    vstar_id: int
    title: str = Field(..., min_length=1)
    content: str = Field(..., min_length=1)
    url: Optional[str] = None
    published_at: Optional[datetime] = None


class ArticleResponse(BaseModel):
    id: int
    vstar_id: int
    title: str
    summary: Optional[str]
    url: Optional[str]
    platform: str
    published_at: Optional[datetime]
    created_at: datetime

    class Config:
        from_attributes = True


# ===== 分析任务 =====

class AnalysisRequest(BaseModel):
    time_window: str = Field(default="1w", description="3d/1w/1m")
    min_mention_count: int = Field(default=3, ge=2, le=20, description="最低提及人数")


class TaskStatusResponse(BaseModel):
    task_id: str
    status: str
    progress: int
    error_message: Optional[str] = None
    result_summary: Optional[dict] = None
    created_at: datetime
    completed_at: Optional[datetime] = None


# ===== 分析结果 =====

class MentionDetail(BaseModel):
    """单条提及的证据"""
    vstar_nickname: str
    vstar_platform: str
    article_title: str
    article_url: Optional[str]
    mentioned_text: str  # 上下文
    sentiment: str
    sentiment_score: float
    published_at: Optional[datetime]


class StockResultItem(BaseModel):
    """榜单中的一只股票"""
    stock_code: str
    stock_name: str
    hotness_score: float
    mention_count: int  # 提及人数
    total_mentions: int  # 总提及次数
    positive_count: int
    neutral_count: int
    negative_count: int
    first_mention_time: Optional[datetime]
    vstar_list: List[str]  # 提及该股票的大V昵称列表


class StockDetailResponse(BaseModel):
    """个股详情"""
    stock_code: str
    stock_name: str
    hotness_score: float
    mention_count: int
    total_mentions: int
    positive_count: int
    neutral_count: int
    negative_count: int
    first_mention_time: Optional[datetime]
    vstar_list: List[str]
    evidence_chain: List[MentionDetail]


# ===== K线数据 =====

class KLineItem(BaseModel):
    date: str
    open: float
    close: float
    high: float
    low: float
    volume: int


class KLineResponse(BaseModel):
    stock_code: str
    stock_name: str
    period: str  # 1m/3m
    data: List[KLineItem]
    mark_line_date: Optional[str] = None  # 绿色虚线标注日期


# ===== 通用响应 =====

class APIResponse(BaseModel):
    success: bool
    message: str = ""
    data: Optional[dict] = None
