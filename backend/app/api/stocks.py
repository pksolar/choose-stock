"""股票数据 API 路由（K线等）"""
from fastapi import APIRouter, Query, Depends
from sqlalchemy.orm import Session

from app.models.database import get_db
from app.models.models import AnalysisResult
from app.services.kline_service import kline_service
from app.utils.stock_mapper import stock_mapper
from app.schemas.schemas import KLineResponse

router = APIRouter(prefix="/api/stocks", tags=["股票数据"])


@router.get("/kline/{stock_code}", response_model=KLineResponse)
def get_kline(
    stock_code: str,
    period: str = Query("1m", description="1m/3m"),
    task_id: str = Query(None, description="分析任务ID，用于获取标记日期"),
    db: Session = Depends(get_db),
):
    """获取个股K线数据"""

    # 获取股票名称
    stock_name = stock_mapper.get_name(stock_code) or stock_code

    # 获取标记日期（首次集中提及时间）
    mark_date = None
    if task_id:
        result = (
            db.query(AnalysisResult)
            .filter(
                AnalysisResult.task_id == task_id,
                AnalysisResult.stock_code == stock_code,
            )
            .first()
        )
        if result and result.first_mention_time:
            mark_date = result.first_mention_time.strftime("%Y-%m-%d")

    kline_result = kline_service.get_kline_data(stock_code, period, mark_date)

    return KLineResponse(
        stock_code=stock_code,
        stock_name=stock_name,
        period=period,
        data=kline_result["data"],
        mark_line_date=kline_result.get("mark_line_date"),
    )


@router.get("/search")
def search_stocks(q: str = Query("", description="搜索关键词")):
    """搜索股票"""
    q = q.strip().upper()
    results = []
    for code, name in stock_mapper._code_to_name.items():
        if q in code or q in name:
            results.append({"code": code, "name": name, "market": "SH" if code.startswith(("6", "9")) else "SZ"})
            if len(results) >= 20:
                break
    return results
