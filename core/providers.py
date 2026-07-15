"""信息源提供商独立定义：每个数据来源都有清晰的标识、特征和别名。

设计思路：
  - 将信息源从路由逻辑中解耦出来，成为独立的配置层
  - 每个 provider 有：标识名、显示名、描述、特征关键词、支持的接口类型
  - 路由时只需根据 provider 名称查找，无需从接口名推断
  - 新增信息源只需在此添加定义，无需修改路由代码
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class Provider:
    """信息源提供商定义。"""
    id: str
    name: str
    description: str
    keywords: list[str] = field(default_factory=list)
    supports: list[str] = field(default_factory=list)
    base_url: Optional[str] = None
    requires_proxy: bool = False
    reliability: float = 0.8


PROVIDERS: dict[str, Provider] = {
    "sina": Provider(
        id="sina",
        name="新浪财经",
        description="新浪财经数据接口，覆盖股票、指数、期货实时行情",
        keywords=["sina", "sinajs", "finance.sina"],
        supports=["realtime", "daily", "index", "futures", "lhb"],
        base_url="https://finance.sina.com.cn",
        reliability=0.9,
    ),
    "eastmoney": Provider(
        id="eastmoney",
        name="东方财富",
        description="东方财富数据接口，覆盖A股、板块、资金流向",
        keywords=["eastmoney", "east", "push2", "eastmoney.com"],
        supports=["realtime", "daily", "sector", "fund_flow", "hot_rank"],
        base_url="https://push2.eastmoney.com",
        requires_proxy=True,
        reliability=0.85,
    ),
    "cls": Provider(
        id="cls",
        name="财联社",
        description="财联社财经资讯，包括电报快讯、市场情绪、涨停池",
        keywords=["cls", "cailianshe", "财联社"],
        supports=["news", "emotion", "limit_up", "sector_heat"],
        base_url="https://www.cls.cn",
        reliability=0.95,
    ),
    "tencent": Provider(
        id="tencent",
        name="腾讯财经",
        description="腾讯财经数据接口，覆盖股票行情",
        keywords=["tencent", "qq", "tx"],
        supports=["realtime", "daily"],
        base_url="https://qt.gtimg.cn",
        reliability=0.9,
    ),
    "ths": Provider(
        id="ths",
        name="同花顺",
        description="同花顺数据接口，覆盖板块、研报",
        keywords=["ths", "10jqka", "同花顺"],
        supports=["sector", "research", "news"],
        base_url="https://q.10jqka.com.cn",
        reliability=0.8,
    ),
    "cninfo": Provider(
        id="cninfo",
        name="巨潮资讯",
        description="巨潮资讯网，上市公司公告、财务数据",
        keywords=["cninfo", "巨潮", "www.cninfo.com.cn"],
        supports=["announcement", "profile", "financial"],
        base_url="https://www.cninfo.com.cn",
        reliability=0.95,
    ),
    "kph": Provider(
        id="kph",
        name="开盘红",
        description="开盘红市场情绪数据",
        keywords=["kph", "开盘红"],
        supports=["emotion"],
        reliability=0.85,
    ),
    "sse": Provider(
        id="sse",
        name="上交所",
        description="上海证券交易所官方数据",
        keywords=["sse", "shanghai", "exchange"],
        supports=["margin", "block_trade", "restricted"],
        base_url="https://www.sse.com.cn",
        reliability=0.99,
    ),
    "wallstreet": Provider(
        id="wallstreet",
        name="华尔街见闻",
        description="华尔街见闻财经日历",
        keywords=["wallstreet", "wsj", "wallstreetcn"],
        supports=["calendar"],
        base_url="https://wallstreetcn.com",
        reliability=0.85,
    ),
    "shmet": Provider(
        id="shmet",
        name="上期所",
        description="上海期货交易所新闻",
        keywords=["shmet", "shfe", "futures"],
        supports=["news"],
        base_url="https://www.shmet.com",
        reliability=0.9,
    ),
    "cctv": Provider(
        id="cctv",
        name="央视新闻",
        description="新闻联播文字稿",
        keywords=["cctv", "news"],
        supports=["news"],
        base_url="https://news.cctv.com",
        reliability=0.99,
    ),
    "baidu": Provider(
        id="baidu",
        name="百度",
        description="百度财经日历",
        keywords=["baidu"],
        supports=["calendar"],
        reliability=0.8,
    ),
    "bloomberg": Provider(
        id="bloomberg",
        name="彭博社",
        description="彭博社财经新闻和亿万富豪榜",
        keywords=["bloomberg"],
        supports=["news", "billionaires"],
        base_url="https://www.bloomberg.com",
        requires_proxy=True,
        reliability=0.75,
    ),
    "reuters": Provider(
        id="reuters",
        name="路透社",
        description="路透社财经新闻",
        keywords=["reuters"],
        supports=["news"],
        base_url="https://www.reuters.com",
        requires_proxy=True,
        reliability=0.8,
    ),
}


def get_provider(provider_id: str) -> Optional[Provider]:
    """根据 ID 获取 provider 定义。"""
    return PROVIDERS.get(provider_id.lower())


def list_providers() -> list[Provider]:
    """列出所有 provider。"""
    return list(PROVIDERS.values())


def get_provider_ids() -> list[str]:
    """获取所有 provider ID 列表。"""
    return list(PROVIDERS.keys())


def get_providers_by_capability(capability: str) -> list[Provider]:
    """根据能力筛选 provider。"""
    return [p for p in PROVIDERS.values() if capability in p.supports]


def infer_provider_from_name(name: str) -> Optional[str]:
    """从接口名/函数名推断 provider ID。"""
    name_lower = name.lower()
    for pid, provider in PROVIDERS.items():
        for kw in provider.keywords:
            if kw.lower() in name_lower:
                return pid
    return None
