"""英文翻译模块 — 金融术语词典 + 最长匹配，离线可用，无需网络。"""
from __future__ import annotations
import json
import re as _re


# ── 金融术语词典 ──────────────────────────────────────────
_FINANCIAL_DICT_EN_ZH = {
    # ----- 央行/机构 -----
    "Federal Reserve": "美联储", "Fed": "美联储", "FOMC": "联邦公开市场委员会",
    "European Central Bank": "欧洲央行", "ECB": "欧洲央行",
    "Bank of Japan": "日本央行", "BOJ": "日本央行",
    "Bank of England": "英国央行", "BOE": "英国央行",
    "People's Bank of China": "中国人民银行", "PBOC": "中国人民银行",
    "Swiss National Bank": "瑞士央行", "Reserve Bank of Australia": "澳洲联储", "RBA": "澳洲联储",
    "Bank of Canada": "加拿大央行", "BOC": "加拿大央行",
    "IMF": "国际货币基金组织", "World Bank": "世界银行", "WTO": "世界贸易组织",
    "OPEC+": "欧佩克+", "OPEC": "欧佩克", "BIS": "国际清算银行",
    # ----- 宏观经济指标 -----
    "interest rate": "利率", "rate decision": "利率决议", "rate cut": "降息", "rate hike": "加息",
    "benchmark rate": "基准利率", "federal funds rate": "联邦基金利率",
    "monetary policy": "货币政策", "fiscal policy": "财政政策",
    "quantitative easing": "量化宽松", "quantitative tightening": "量化紧缩",
    "balance sheet": "资产负债表",
    "inflation": "通胀", "inflation rate": "通胀率", "deflation": "通缩",
    "disinflation": "通胀放缓", "stagflation": "滞胀",
    "Consumer Price Index": "消费者物价指数", "CPI": "消费者物价指数", "core CPI": "核心CPI",
    "Producer Price Index": "生产者物价指数", "PPI": "生产者物价指数",
    "PCE": "个人消费支出", "core PCE": "核心PCE",
    "Gross Domestic Product": "国内生产总值", "GDP growth": "GDP增长", "GDP": "国内生产总值",
    "recession": "经济衰退", "soft landing": "软着陆", "hard landing": "硬着陆",
    "recovery": "复苏", "slowdown": "放缓", "downturn": "下行", "expansion": "扩张",
    "contraction": "收缩",
    "unemployment rate": "失业率", "unemployment": "失业率",
    "jobless claims": "失业金申请人数", "nonfarm payrolls": "非农就业人数",
    "non-farm payrolls": "非农就业人数", "non-farm": "非农", "payroll": "就业人数",
    "retail sales": "零售销售", "consumer confidence": "消费者信心",
    "consumer sentiment": "消费者信心指数",
    "manufacturing PMI": "制造业PMI", "services PMI": "服务业PMI", "PMI": "采购经理指数",
    "trade balance": "贸易帐", "trade deficit": "贸易逆差", "trade surplus": "贸易顺差",
    "current account": "经常帐", "budget deficit": "预算赤字", "government debt": "政府债务",
    "durable goods": "耐用品订单", "factory orders": "工厂订单",
    "industrial production": "工业产出", "capacity utilization": "产能利用率",
    "housing starts": "新屋开工", "building permits": "建筑许可",
    "existing home sales": "成屋销售", "new home sales": "新屋销售",
    "pending home sales": "成屋签约销售",
    "ISM manufacturing": "ISM制造业指数", "ISM": "供应管理协会",
    "trade talks": "贸易谈判", "tariff": "关税", "sanctions": "制裁", "embargo": "禁运",
    # ----- 国债/收益率 -----
    "treasury bond": "国债", "Treasury yield": "国债收益率",
    "10-year yield": "10年期收益率", "2-year yield": "2年期收益率",
    "yield curve": "收益率曲线", "inverted yield curve": "收益率曲线倒挂",
    # ----- 市场术语 -----
    "stock market": "股市", "equity": "股票", "equities": "股票", "share": "股份", "shares": "股份",
    "bond": "债券", "bonds": "债券", "commodity": "商品", "commodities": "商品",
    "crude oil": "原油", "gold": "黄金", "silver": "白银", "copper": "铜",
    "iron ore": "铁矿石", "natural gas": "天然气",
    "wheat": "小麦", "corn": "玉米", "soybean": "大豆", "cotton": "棉花",
    "bull market": "牛市", "bear market": "熊市", "correction": "回调",
    "rally": "上涨", "selloff": "抛售", "sell-off": "抛售", "rebound": "反弹",
    "volatility": "波动率", "market cap": "市值", "market capitalization": "市值",
    "valuation": "估值", "dividend": "股息",
    "earnings report": "财报", "earnings": "财报", "revenue": "营收",
    "net income": "净利润", "profit": "利润", "EPS": "每股收益",
    "P/E ratio": "市盈率", "price-to-earnings": "市盈率",
    "bullish": "看涨", "bearish": "看跌", "long position": "多头", "short position": "空头",
    "short selling": "做空", "margin call": "追加保证金",
    "leverage": "杠杆", "liquidity": "流动性",
    "safe-haven asset": "避险资产", "safe haven": "避险", "risk-off": "避险", "risk-on": "追逐风险",
    "flight to safety": "避险买盘", "speculation": "投机",
    "hedge fund": "对冲基金", "hedge": "对冲",
    "asset purchase": "资产购买", "stimulus": "刺激", "fiscal stimulus": "财政刺激",
    "bailout": "救助",
    # ----- 货币/外汇 -----
    "U.S. Dollar Index": "美元指数", "Dollar Index": "美元指数", "DXY": "美元指数",
    "dollar": "美元", "euro": "欧元", "EUR": "欧元",
    "yen": "日元", "JPY": "日元", "Japanese yen": "日元",
    "pound": "英镑", "sterling": "英镑", "GBP": "英镑", "British pound": "英镑",
    "yuan": "人民币", "RMB": "人民币", "CNY": "人民币", "Chinese yuan": "人民币",
    "Swiss franc": "瑞郎", "CHF": "瑞郎",
    "Canadian dollar": "加元", "CAD": "加元",
    "Australian dollar": "澳元", "AUD": "澳元",
    "New Zealand dollar": "纽元", "NZD": "纽元",
    "foreign exchange": "外汇", "forex": "外汇", "exchange rate": "汇率",
    "currency": "货币", "currencies": "货币",
    "depreciation": "贬值", "appreciation": "升值", "devalue": "贬值", "revalue": "升值",
    # ----- 指数 -----
    "Dow Jones Industrial Average": "道琼斯工业平均指数", "Dow Jones": "道琼斯", "DJIA": "道琼斯工业平均指数",
    "Nasdaq Composite": "纳斯达克综合指数", "Nasdaq": "纳斯达克", "NASDAQ": "纳斯达克",
    "S&P 500": "标普500", "S&P500": "标普500", "SPX": "标普500",
    "Russell 2000": "罗素2000", "Russell": "罗素",
    "CBOE Volatility Index": "波动率指数", "VIX": "波动率指数", "fear index": "恐慌指数",
    "Hang Seng Index": "恒生指数", "Hang Seng": "恒生指数", "HSI": "恒生指数",
    "HSCEI": "国企指数", "Hang Seng Tech": "恒生科技指数", "HSTECH": "恒生科技指数",
    "Nikkei 225": "日经225指数", "Nikkei": "日经指数",
    "FTSE 100": "富时100指数", "FTSE": "富时指数",
    "DAX": "德国DAX指数", "CAC 40": "法国CAC40指数",
    "Shanghai Composite": "上证综指", "Shenzhen Composite": "深证综指",
    "CSI 300": "沪深300", "ChiNext": "创业板",
    # ----- 商品相关 -----
    "Brent": "布伦特原油", "West Texas Intermediate": "西德克萨斯中质原油", "WTI": "西德克萨斯中质原油",
    "OPEC meeting": "欧佩克会议", "production cut": "减产", "production quota": "产量配额",
    "supply": "供应", "demand": "需求", "inventory": "库存", "stockpile": "储备",
    "strategic reserve": "战略储备", "refinery": "炼油厂", "pipeline": "管道",
    "shipment": "出货", "output": "产出",
    # ----- 公司/事件 -----
    "earnings season": "财报季", "quarterly report": "季报", "annual report": "年报",
    "guidance": "业绩指引", "outlook": "展望", "forecast": "预测", "estimate": "预估",
    "consensus": "共识", "beat": "超预期", "miss": "不及预期", "in line": "符合预期",
    "merger": "合并", "acquisition": "收购", "M&A": "并购",
    "initial public offering": "首次公开募股", "IPO": "首次公开募股",
    "share repurchase": "股份回购", "buyback": "回购", "spin-off": "分拆",
    "restructuring": "重组", "layoff": "裁员", "bankruptcy": "破产", "default": "违约",
    "lawsuit": "诉讼", "antitrust": "反垄断", "regulatory approval": "监管批准",
    "FDA approval": "FDA批准", "product launch": "产品发布", "recall": "召回",
    "cyberattack": "网络攻击", "data breach": "数据泄露", "outage": "服务中断",
    # ----- 地缘政治 -----
    "trade war": "贸易战", "tariff war": "关税战", "treaty": "条约",
    "agreement": "协议", "deal": "协议", "summit": "峰会",
    "negotiation": "谈判", "talks": "谈判", "election": "选举", "vote": "投票",
    "referendum": "公投", "geopolitical": "地缘政治", "geopolitics": "地缘政治",
    "conflict": "冲突", "tension": "紧张局势", "war": "战争", "ceasefire": "停火",
    "nuclear": "核", "missile test": "导弹试射",
    # ----- 数据描述 -----
    "month-over-month": "环比", "MoM": "环比", "quarter-over-quarter": "环比", "QoQ": "环比",
    "year-over-year": "同比", "YoY": "同比", "year-on-year": "同比",
    "seasonally adjusted": "季调", "preliminary": "初值", "final": "终值",
    "revised": "修正值", "revision": "修正值", "surprise": "意外",
    "upside surprise": "超预期上行", "downside surprise": "不及预期",
    "monthly": "月度", "quarterly": "季度", "weekly": "周度", "daily": "日度", "annual": "年度",
    "report": "报告", "release": "公布", "announcement": "公告", "statement": "声明",
    "speech": "讲话", "testimony": "证词", "minutes": "纪要", "meeting minutes": "会议纪要",
    "press conference": "新闻发布会", "decision": "决议", "unanimous": "一致", "dissent": "异议",
    "hawkish": "鹰派", "dovish": "鸽派", "neutral": "中性", "patient": "耐心",
    "data-dependent": "数据依赖", "forward guidance": "前瞻指引",
    "pause": "暂停", "hold": "维持", "cut": "降息", "hike": "加息",
    "tighten": "收紧", "ease": "宽松", "normalize": "正常化",
    "transitory": "暂时性", "persistent": "持续性", "structural": "结构性", "cyclical": "周期性",
}

# 按长度降序排列，优先匹配长词
_FINANCIAL_DICT_SORTED = sorted(_FINANCIAL_DICT_EN_ZH.items(), key=lambda x: -len(x[0]))


def _has_english(text) -> bool:
    """判断字符串是否包含显著比例的英文字符（>15% 且字母数>5）。"""
    if not isinstance(text, str) or not text:
        return False
    letters = sum(1 for c in text if ('a' <= c <= 'z') or ('A' <= c <= 'Z'))
    if letters < 5:
        return False
    return letters / max(len(text), 1) > 0.15


def _translate_en_to_zh(text):
    """将文本中的英文金融术语翻译为中文。

    策略：词典最长匹配替换，未匹配的英文保留原样。
    """
    if not isinstance(text, str) or not text:
        return text
    if not _has_english(text):
        return text
    result = text
    for en, zh in _FINANCIAL_DICT_SORTED:
        if en in result:
            pattern = _re.compile(_re.escape(en), _re.IGNORECASE)
            result = pattern.sub(zh, result)
    return result


def _translate_records(records: list[dict], fields=None, translate: bool = True) -> list[dict]:
    """翻译记录列表中的英文文本字段。"""
    if not translate or not records:
        return records
    text_fields = set(fields) if fields else None
    for record in records:
        for key, val in list(record.items()):
            if not isinstance(val, str):
                continue
            if text_fields and key not in text_fields:
                continue
            if _has_english(val):
                record[key] = _translate_en_to_zh(val)
    return records


def translate_text_impl(text: str) -> str:
    """翻译工具实现，返回 JSON。"""
    if not text:
        return json.dumps({"ok": False, "error": "text 不能为空"}, ensure_ascii=False)
    result = _translate_en_to_zh(text)
    return json.dumps({
        "ok": True,
        "original": text,
        "translated": result,
        "has_english": _has_english(text),
    }, ensure_ascii=False)
