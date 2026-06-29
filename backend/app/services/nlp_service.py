"""
NLP 服务：情感分析 + 股票代码识别
使用 SnowNLP + jieba 实现，预留大模型 API 接口
"""
import re
from typing import Tuple, Optional
from datetime import datetime, timedelta

from app.utils.stock_mapper import stock_mapper


class NLPService:
    """NLP 分析服务"""

    # 自定义正向情感词典（金融领域）
    POSITIVE_WORDS = {
        "买入", "增持", "看好", "推荐", "超预期", "大涨", "翻倍", "起飞",
        "利好", "突破", "龙头", "优质", "低估", "反转", "爆发", "主升浪",
        "成长", "价值", "业绩大增", "订单饱满", "产能释放", "技术领先",
        "受益", "景气", "上行", "放量", "加速", "超跌反弹", "底部确认",
        "配置价值", "值得关注", "强烈推荐", "重点推荐", "持续看好",
        "估值修复", "戴维斯双击", "量价齐升", "供不应求", "产能利用率高",
        "毛利率提升", "净利增长", "现金流改善", "高股息", "回购",
    }

    # 自定义负向情感词典
    NEGATIVE_WORDS = {
        "卖出", "减持", "看空", "风险", "警惕", "注意", "暴跌", "崩盘",
        "利空", "下滑", "萎缩", "亏损", "商誉", "暴雷", "踩雷", "退市",
        "高估", "泡沫", "下行", "内卷", "竞争加剧", "业绩不及预期",
        "产能过剩", "毛利率下降", "现金流紧张", "负债率", "质押风险",
        "减持套现", "财务造假", "监管", "处罚", "ST", "退市风险",
        "不推荐", "回避", "清仓", "止损", "压力", "挑战",
    }

    def __init__(self):
        self._snownlp_available = False
        try:
            from snownlp import SnowNLP
            self._snownlp_available = True
        except ImportError:
            pass

        self._jieba_available = False
        try:
            import jieba
            self._jieba_available = True
            # 使用精确模式
        except ImportError:
            pass

    def analyze_sentiment(self, text: str) -> Tuple[str, float]:
        """
        分析文本情感
        返回: (sentiment_label, score)
        sentiment_label: positive / neutral / negative
        score: 0~1，越高越正面
        """
        if not text or len(text.strip()) < 10:
            return "neutral", 0.5

        # 方法1: 基于词典的快速判断（金融领域定制）
        dict_score = self._dictionary_sentiment(text)

        # 方法2: SnowNLP 通用情感分析
        ml_score = 0.5
        if self._snownlp_available:
            try:
                from snownlp import SnowNLP
                s = SnowNLP(text)
                ml_score = s.sentiments
            except Exception:
                pass

        # 综合得分：词典权重 0.4，机器学习 0.6
        final_score = dict_score * 0.4 + ml_score * 0.6

        # 分类
        if final_score >= 0.6:
            label = "positive"
        elif final_score <= 0.4:
            label = "negative"
        else:
            label = "neutral"

        return label, round(final_score, 4)

    def _dictionary_sentiment(self, text: str) -> float:
        """基于金融情感词典的快速评分"""
        positive_count = 0
        negative_count = 0

        for word in self.POSITIVE_WORDS:
            positive_count += text.count(word)

        for word in self.NEGATIVE_WORDS:
            negative_count += text.count(word)

        total = positive_count + negative_count
        if total == 0:
            return 0.5  # 无情感词，中性

        return positive_count / total

    def detect_stocks(self, text: str) -> list:
        """
        从文本中识别 A 股股票
        返回: [(code, name, context_snippet), ...]
        """
        return stock_mapper.find_stocks_in_text(text)

    def extract_context(self, text: str, keyword: str, window: int = 50) -> str:
        """提取关键词周围的上下文文本"""
        idx = text.find(keyword)
        if idx == -1:
            return text[:window * 2]
        start = max(0, idx - window)
        end = min(len(text), idx + len(keyword) + window)
        return text[start:end]

    def is_similar_text(self, text1: str, text2: str, threshold: float = 0.9) -> bool:
        """
        判断两段文本是否高度相似（用于跨平台去重）
        使用 difflib 计算相似度
        """
        import difflib
        # 截取前500字比较
        ratio = difflib.SequenceMatcher(None, text1[:500], text2[:500]).ratio()
        return ratio >= threshold


# 全局单例
nlp_service = NLPService()
