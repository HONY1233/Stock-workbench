"""自定义工具（sources/ 模块）与数据提供商的映射。

用于按来源分类整理和按需调用自定义工具。
"""
from __future__ import annotations

# 自定义工具 -> 数据提供商映射
# 键为工具名，值为 provider 列表
CUSTOM_TOOL_PROVIDERS: dict[str, list[str]] = {
    # sources/stock.py
    "stock_zh_a_daily": ["sina"],
    "stock_zh_index_daily": ["sina"],
    "stock_zh_index_spot": ["eastmoney", "sina"],
    "stock_zh_a_spot": ["eastmoney", "sina"],
    # sources/news.py
    "cls_telegraph": ["cls"],
    "news_cctv": ["cctv"],
    "news_economic_calendar": ["baidu"],
    "stock_news": ["eastmoney"],
    "global_news_em": ["eastmoney"],
    "global_news_sina": ["sina"],
    "global_news_ths": ["ths"],
    "wallstreet_news": ["wallstreet"],
    "futures_news_shmet": ["shmet"],
    "stock_us_news": ["eastmoney"],
    "translate_text": ["local"],
    # sources/market_data.py
    "tencent_realtime_quote": ["tencent"],
    "northbound_flow": ["eastmoney"],
    "stock_fund_flow": ["eastmoney"],
    "margin_trading": ["sse", "szse"],
    "block_trade": ["eastmoney"],
    "holder_count": ["eastmoney"],
    "lockup_release": ["sse", "sina"],
    "research_report": ["ths"],
    "eps_forecast": ["ths"],
    "limit_up_broken": ["eastmoney"],
    "limit_up_previous": ["eastmoney"],
    "limit_up_strong": ["eastmoney"],
    "option_t_quote": ["eastmoney", "sse"],
    "hot_rank": ["eastmoney"],
    "concept_belong": ["eastmoney"],
    # sources/international.py
    "reuters_news": ["reuters"],
    "bloomberg_news": ["bloomberg"],
    "bloomberg_billionaires": ["bloomberg"],
    "global_news_search": ["eastmoney", "sina", "ths", "wallstreet"],
    # sources/funds_indices.py
    "fund_etf_spot": ["eastmoney"],
    "fund_etf_daily": ["sina"],
    "futures_realtime": ["sina"],
    "futures_daily": ["sina"],
    "futures_global_spot": ["eastmoney"],
    "index_us_daily": ["sina"],
    "index_hk_daily": ["sina"],
    "index_global_list": ["sina"],
    # sources/cninfo.py
    "stock_notice_cninfo": ["cninfo"],
    "stock_profile_cninfo": ["cninfo"],
    "stock_financial_abstract_cninfo": ["cninfo"],
    "stock_dividend_cninfo": ["cninfo"],
    # sources/sectors.py
    "sector_industry_list": ["ths"],
    "sector_concept_list": ["ths"],
    "sector_industry_daily": ["ths"],
    "sector_concept_daily": ["ths"],
    "sector_daily_rank": ["ths"],
    # sources/xueqiu.py
    "xueqiu_hot_posts": ["xueqiu"],
    "xueqiu_stock_posts": ["xueqiu"],
    "xueqiu_comments": ["xueqiu"],
    "xueqiu_status": ["xueqiu"],
}


def get_tool_providers(tool_name: str) -> list[str]:
    """获取指定自定义工具的数据提供商列表。"""
    return CUSTOM_TOOL_PROVIDERS.get(tool_name, [])


def list_all_providers() -> set[str]:
    """获取所有自定义工具涉及的数据提供商。"""
    providers = set()
    for pl in CUSTOM_TOOL_PROVIDERS.values():
        providers.update(pl)
    return providers


def list_tools_by_provider(provider: str) -> list[str]:
    """按数据提供商筛选自定义工具。

    Args:
        provider: 提供商名称，如 sina, eastmoney, cls 等

    Returns:
        该提供商支持的工具名列表
    """
    provider_lower = provider.lower()
    return [
        name for name, providers in CUSTOM_TOOL_PROVIDERS.items()
        if provider_lower in [p.lower() for p in providers]
    ]
