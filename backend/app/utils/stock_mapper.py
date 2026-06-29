"""
A股股票代码与名称映射表
内置常用股票数据，支持从 akshare 动态加载
"""
import re
from typing import Dict, List, Tuple, Optional

# 内置常用 A 股股票映射（代码 -> 名称）
# 数据来源：沪深300 + 中证500 常用标的
BUILTIN_STOCKS: Dict[str, str] = {
    # 上证主板
    "600000": "浦发银行", "600009": "上海机场", "600010": "包钢股份",
    "600015": "华夏银行", "600016": "民生银行", "600018": "上港集团",
    "600028": "中国石化", "600029": "南方航空", "600030": "中信证券",
    "600031": "三一重工", "600036": "招商银行", "600048": "保利发展",
    "600050": "中国联通", "600085": "同仁堂", "600104": "上汽集团",
    "600111": "北方稀土", "600150": "中国船舶", "600196": "复星医药",
    "600276": "恒瑞医药", "600309": "万华化学", "600406": "国电南瑞",
    "600436": "片仔癀", "600438": "通威股份", "600519": "贵州茅台",
    "600570": "恒生电子", "600585": "海螺水泥", "600588": "用友网络",
    "600690": "海尔智家", "600809": "山西汾酒", "600837": "海通证券",
    "600887": "伊利股份", "600900": "长江电力", "600905": "三峡能源",
    "600918": "中泰证券", "600941": "中国移动", "601012": "隆基绿能",
    "601088": "中国神华", "601111": "中国国航", "601138": "工业富联",
    "601166": "兴业银行", "601211": "国泰君安", "601225": "陕西煤业",
    "601288": "农业银行", "601318": "中国平安", "601328": "交通银行",
    "601390": "中国中铁", "601398": "工商银行", "601600": "中国铝业",
    "601601": "中国太保", "601628": "中国人寿", "601668": "中国建筑",
    "601688": "华泰证券", "601728": "中国电信", "601766": "中国中车",
    "601800": "中国交建", "601818": "光大银行", "601857": "中国石油",
    "601878": "浙商证券", "601888": "中国中免", "601899": "紫金矿业",
    "601919": "中远海控", "601939": "建设银行", "601985": "中国核电",
    "601988": "中国银行", "601995": "中金公司",
    # 深证主板
    "000001": "平安银行", "000002": "万科A", "000063": "中兴通讯",
    "000100": "TCL科技", "000157": "中联重科", "000333": "美的集团",
    "000338": "潍柴动力", "000425": "徐工机械", "000538": "云南白药",
    "000568": "泸州老窖", "000596": "古井贡酒", "000625": "长安汽车",
    "000651": "格力电器", "000661": "长春高新", "000725": "京东方A",
    "000776": "广发证券", "000792": "盐湖股份", "000800": "一汽解放",
    "000858": "五粮液", "000876": "新希望", "000895": "双汇发展",
    "000938": "紫光股份", "000963": "华东医药", "000977": "浪潮信息",
    "001979": "招商蛇口",
    # 创业板
    "300015": "爱尔眼科", "300033": "同花顺", "300059": "东方财富",
    "300122": "智飞生物", "300124": "汇川技术", "300142": "沃森生物",
    "300207": "欣旺达", "300274": "阳光电源", "300316": "晶盛机电",
    "300347": "泰格医药", "300390": "天华新能", "300394": "天孚通信",
    "300413": "芒果超媒", "300418": "昆仑万维", "300433": "蓝思科技",
    "300450": "先导智能", "300498": "温氏股份", "300502": "新易盛",
    "300661": "圣邦股份", "300750": "宁德时代", "300760": "迈瑞医疗",
    "300896": "爱美客",
    # 科创板
    "688005": "容百科技", "688008": "澜起科技", "688009": "中国通号",
    "688012": "中微公司", "688036": "传音控股", "688041": "海光信息",
    "688047": "龙芯中科", "688065": "凯赛生物", "688072": "拓荆科技",
    "688088": "虹软科技", "688111": "金山办公", "688116": "天奈科技",
    "688122": "西部超导", "688126": "沪硅产业", "688180": "君实生物",
    "688185": "康希诺", "688187": "时代电气", "688188": "柏楚电子",
    "688223": "晶科能源", "688256": "寒武纪", "688271": "联影医疗",
    "688303": "大全能源", "688396": "华润微", "688472": "阿特斯",
    "688475": "萤石网络", "688536": "思瑞浦", "688556": "高测股份",
    "688561": "奇安信", "688599": "天合光能", "688772": "珠海冠宇",
    "688777": "中控技术", "688981": "中芯国际",
}


class StockMapper:
    """A股股票代码 <-> 名称 双向映射"""

    def __init__(self):
        self._code_to_name: Dict[str, str] = dict(BUILTIN_STOCKS)
        self._name_to_code: Dict[str, str] = {}
        # 构建反向映射和简称映射
        for code, name in self._code_to_name.items():
            self._name_to_code[name] = code
            # 去掉"A"后缀的简称（如"万科A" -> "万科"）
            short_name = name.rstrip("A")
            if short_name != name and short_name not in self._name_to_code:
                self._name_to_code[short_name] = code

    def load_from_akshare(self):
        """从 akshare 加载全量 A 股列表（网络可用时，10秒超时）"""
        try:
            import akshare as ak

            # 使用线程 + 超时防止网络请求卡死
            import threading
            result = [None]

            def _fetch():
                try:
                    result[0] = ak.stock_info_a_code_name()
                except Exception:
                    pass

            t = threading.Thread(target=_fetch, daemon=True)
            t.start()
            t.join(timeout=10)

            df = result[0]
            if df is None:
                print("从 akshare 加载股票列表超时，使用内置数据")
                return

            for _, row in df.iterrows():
                code = str(row.get("code", "")).strip()
                name = str(row.get("name", "")).strip()
                if code and name and len(code) == 6:
                    self._code_to_name[code] = name
                    self._name_to_code[name] = code
        except Exception as e:
            print(f"从 akshare 加载股票列表失败，使用内置数据: {e}")

    def find_stocks_in_text(self, text: str) -> List[Tuple[str, str, str]]:
        """
        在文本中查找所有 A 股股票
        返回: [(股票代码, 股票名称, 匹配到的原文片段), ...]
        """
        results = []
        seen = set()

        # 方法1: 正则匹配6位股票代码（600xxx, 000xxx, 300xxx, 688xxx）
        code_pattern = re.compile(r'\b(600|601|603|605|000|001|002|003|300|301|688|689)\d{3}\b')
        for match in code_pattern.finditer(text):
            code = match.group()
            if code in self._code_to_name and code not in seen:
                name = self._code_to_name[code]
                # 取匹配位置前后50字作为上下文
                start = max(0, match.start() - 50)
                end = min(len(text), match.end() + 50)
                snippet = text[start:end]
                results.append((code, name, snippet))
                seen.add(code)

        # 方法2: 匹配股票名称
        for name, code in self._name_to_code.items():
            if code not in seen and name in text:
                # 找到名称在文本中的位置
                idx = text.find(name)
                start = max(0, idx - 50)
                end = min(len(text), idx + len(name) + 50)
                snippet = text[start:end]
                results.append((code, self._code_to_name[code], snippet))
                seen.add(code)

        return results

    def get_name(self, code: str) -> Optional[str]:
        return self._code_to_name.get(code)

    def get_code(self, name: str) -> Optional[str]:
        return self._name_to_code.get(name)

    @property
    def stock_count(self) -> int:
        return len(self._code_to_name)


# 全局单例
stock_mapper = StockMapper()
