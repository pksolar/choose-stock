"""
K线数据服务
使用 akshare 获取 A 股日线数据，失败时使用模拟数据
"""
from datetime import datetime, timedelta
from typing import List, Dict, Optional
import random


class KLineService:
    """K线数据获取服务"""

    def __init__(self):
        self._akshare_available = False
        try:
            import akshare as ak
            self._akshare_available = True
        except ImportError:
            pass

    def get_kline_data(
        self, stock_code: str, period: str = "1m", mark_date: Optional[str] = None
    ) -> Dict:
        """
        获取个股K线数据
        period: 1m (1个月) / 3m (3个月)
        mark_date: 标注日期（绿色虚线），格式 YYYY-MM-DD
        """
        # 确定日期范围
        end_date = datetime.now()
        if period == "1m":
            start_date = end_date - timedelta(days=30)
        elif period == "3m":
            start_date = end_date - timedelta(days=90)
        else:
            start_date = end_date - timedelta(days=30)

        # 尝试从 akshare 获取真实数据
        if self._akshare_available:
            real_data = self._fetch_from_akshare(stock_code, start_date, end_date)
            if real_data:
                return {
                    "stock_code": stock_code,
                    "period": period,
                    "data": real_data,
                    "mark_line_date": mark_date,
                }

        # 回退到模拟数据
        mock_data = self._generate_mock_kline(stock_code, start_date, end_date, mark_date)
        return {
            "stock_code": stock_code,
            "period": period,
            "data": mock_data,
            "mark_line_date": mark_date,
        }

    def _fetch_from_akshare(self, stock_code: str, start_date: datetime, end_date: datetime) -> List[Dict]:
        """从 akshare 获取真实日线数据"""
        try:
            import akshare as ak

            # 判断市场
            if stock_code.startswith(("6", "9")):
                symbol = f"sh{stock_code}"
            else:
                symbol = f"sz{stock_code}"

            df = ak.stock_zh_a_hist(
                symbol=symbol,
                period="daily",
                start_date=start_date.strftime("%Y%m%d"),
                end_date=end_date.strftime("%Y%m%d"),
                adjust="qfq",  # 前复权
            )

            if df is None or df.empty:
                return []

            data = []
            for _, row in df.iterrows():
                data.append({
                    "date": str(row.get("日期", "")),
                    "open": float(row.get("开盘", 0)),
                    "close": float(row.get("收盘", 0)),
                    "high": float(row.get("最高", 0)),
                    "low": float(row.get("最低", 0)),
                    "volume": int(row.get("成交量", 0)),
                })
            return data

        except Exception as e:
            print(f"akshare 获取K线数据失败 ({stock_code}): {e}")
            return []

    def _generate_mock_kline(
        self, stock_code: str, start_date: datetime, end_date: datetime, mark_date: Optional[str] = None
    ) -> List[Dict]:
        """生成模拟K线数据（用于演示）"""
        data = []
        current_date = start_date
        # 基于股票代码生成不同的初始价格
        base_price = 10.0 + (hash(stock_code) % 1000) / 10.0
        price = base_price

        # 判断mark_date前后是否有趋势变化
        mark_dt = None
        if mark_date:
            try:
                mark_dt = datetime.strptime(mark_date, "%Y-%m-%d")
            except ValueError:
                pass

        while current_date <= end_date:
            # 跳过周末
            if current_date.weekday() >= 5:
                current_date += timedelta(days=1)
                continue

            # 在标注日期附近产生上涨趋势
            trend = 0
            if mark_dt:
                days_after_mark = (current_date - mark_dt).days
                if days_after_mark >= 0:
                    trend = min(days_after_mark * 0.02, 0.05)  # 逐渐上涨

            daily_change = random.gauss(trend, 0.02)  # 正态分布
            open_price = price
            close_price = price * (1 + daily_change)
            high_price = max(open_price, close_price) * (1 + abs(random.random() * 0.01))
            low_price = min(open_price, close_price) * (1 - abs(random.random() * 0.01))
            volume = random.randint(1000000, 50000000)

            data.append({
                "date": current_date.strftime("%Y-%m-%d"),
                "open": round(open_price, 2),
                "close": round(close_price, 2),
                "high": round(high_price, 2),
                "low": round(low_price, 2),
                "volume": volume,
            })

            price = close_price
            current_date += timedelta(days=1)

        return data


# 全局单例
kline_service = KLineService()
