"""L0-L3 数据源等级制度与兜底机制。

等级定义：
  L0 核心层  — 本地可用，无网络依赖（翻译、接口列表）
  L1 稳定层  — akshare 稳定 API + 腾讯直连（不封 IP）
  L2 限流层  — 东财 datacenter/push2（需限流，可能被封）
  L3 受限层  — 国际源 Reuters/Bloomberg（需翻墙）

兜底链路：L3 → L2 → L1 → L0
当高等级数据源失败时，自动降级到低等级替代源。
"""
from __future__ import annotations
import json
import functools
from enum import IntEnum
from typing import Callable, Any


class Tier(IntEnum):
    """数据源可靠性等级，数值越低越稳定。"""
    L0_CORE = 0       # 本地核心（翻译、接口列表）
    L1_STABLE = 1     # 稳定数据（akshare 核心API + 腾讯直连）
    L2_RATED = 2      # 限流数据（东财 datacenter/push2）
    L3_RESTRICTED = 3 # 受限数据（国际源 Reuters/Bloomberg）


# ── 工具等级注册表 ──────────────────────────────────────────
# 每个工具名映射到 (等级, 兜底工具名列表)
# 兜底链：当前工具失败时，按顺序尝试兜底工具
TOOL_TIERS: dict[str, tuple[Tier, list[str]]] = {
    # ── L0 核心层 ──
    "translate_text":        (Tier.L0_CORE, []),
    "data_interfaces":       (Tier.L0_CORE, []),
    "tool_tier_info":        (Tier.L0_CORE, []),

    # ── L1 稳定层 ──
    "stock_zh_a_daily":      (Tier.L1_STABLE, []),
    "stock_zh_a_spot":       (Tier.L1_STABLE, ["tencent_realtime_quote"]),
    "stock_zh_index_daily":  (Tier.L1_STABLE, []),
    "stock_zh_index_spot":   (Tier.L1_STABLE, []),
    "tencent_realtime_quote":(Tier.L1_STABLE, ["stock_zh_a_spot"]),
    "fund_etf_spot":         (Tier.L1_STABLE, []),
    "fund_etf_daily":        (Tier.L1_STABLE, []),
    "futures_daily":        (Tier.L1_STABLE, []),
    "futures_global_spot":  (Tier.L1_STABLE, []),
    "index_us_daily":        (Tier.L1_STABLE, []),
    "index_hk_daily":        (Tier.L1_STABLE, []),
    "index_global_list":     (Tier.L1_STABLE, []),
    "stock_news":            (Tier.L1_STABLE, []),
    "news_cctv":             (Tier.L1_STABLE, []),
    "news_economic_calendar":(Tier.L1_STABLE, []),
    "cls_telegraph":         (Tier.L1_STABLE, []),
    "stock_notice_cninfo":   (Tier.L1_STABLE, []),
    "stock_profile_cninfo":  (Tier.L1_STABLE, []),
    "stock_financial_abstract_cninfo": (Tier.L1_STABLE, []),
    "stock_dividend_cninfo": (Tier.L1_STABLE, []),
    "stock_limit_up_pool":   (Tier.L1_STABLE, []),
    "stock_limit_down_pool": (Tier.L1_STABLE, []),
    "sector_realtime":       (Tier.L1_STABLE, []),
    "market_emotion_cls":    (Tier.L1_STABLE, []),
    "market_emotion_kph":    (Tier.L1_STABLE, []),
    "cls_limit_up_pool":     (Tier.L1_STABLE, []),
    "cls_market_wind":       (Tier.L1_STABLE, []),
    "cls_market_mainline":   (Tier.L1_STABLE, []),
    "stock_lhb_daily":       (Tier.L1_STABLE, []),
    "stock_lhb_institution": (Tier.L1_STABLE, []),
    "futures_main_display":  (Tier.L1_STABLE, []),
    "option_commodity_list": (Tier.L1_STABLE, []),
    "option_cffex_hs300_list":(Tier.L1_STABLE, []),
    "data_query":            (Tier.L1_STABLE, []),
    "limit_up_broken":       (Tier.L1_STABLE, []),
    "limit_up_previous":     (Tier.L1_STABLE, []),
    "limit_up_strong":       (Tier.L1_STABLE, []),
    "margin_trading":        (Tier.L1_STABLE, []),
    "block_trade":           (Tier.L1_STABLE, []),
    "holder_count":          (Tier.L1_STABLE, []),
    "lockup_release":        (Tier.L1_STABLE, []),
    "option_t_quote":        (Tier.L1_STABLE, []),
    "northbound_flow":       (Tier.L1_STABLE, []),
    "research_report":       (Tier.L1_STABLE, []),
    "eps_forecast":          (Tier.L1_STABLE, []),

    # ── L2 限流层（东财 push2/datacenter，可能被封）──
    "cls_sector_heat":       (Tier.L2_RATED, []),
    "stock_fund_flow":       (Tier.L2_RATED, ["northbound_flow"]),
    "hot_rank":              (Tier.L2_RATED, ["cls_market_wind"]),
    "concept_belong":        (Tier.L2_RATED, ["sector_realtime"]),
    "global_news_em":        (Tier.L2_RATED, ["global_news_sina", "global_news_ths"]),
    "global_news_sina":      (Tier.L2_RATED, ["global_news_em"]),
    "global_news_ths":       (Tier.L2_RATED, ["global_news_em"]),
    "wallstreet_news":       (Tier.L2_RATED, ["news_economic_calendar"]),
    "futures_news_shmet":    (Tier.L2_RATED, ["global_news_em"]),
    "stock_us_news":         (Tier.L2_RATED, ["global_news_em"]),

    # ── L3 受限层（国际源，需翻墙）──
    "reuters_news":          (Tier.L3_RESTRICTED, ["global_news_em"]),
    "bloomberg_news":        (Tier.L3_RESTRICTED, ["global_news_em"]),
    "bloomberg_billionaires":(Tier.L3_RESTRICTED, []),
    "global_news_search":    (Tier.L3_RESTRICTED, ["global_news_em"]),
}


def get_tier(tool_name: str) -> Tier:
    """获取工具的等级。"""
    info = TOOL_TIERS.get(tool_name)
    return info[0] if info else Tier.L1_STABLE


def tier_info(tool_name: str) -> dict:
    """获取工具的等级和兜底信息。"""
    info = TOOL_TIERS.get(tool_name)
    if not info:
        return {"tier": Tier.L1_STABLE, "fallback": [], "tier_name": "L1_STABLE"}
    tier, fallbacks = info
    return {
        "tier": tier,
        "tier_name": tier.name,
        "fallback": fallbacks,
    }


def with_fallback(primary: Callable, fallbacks: list[Callable], **shared_kwargs) -> str:
    """执行主函数，失败时按顺序尝试兜底函数。

    Args:
        primary: 主数据源函数
        fallbacks: 兜底函数列表（按优先级排序）
        **shared_kwargs: 传递给所有函数的关键字参数

    Returns:
        第一个成功函数的 JSON 结果，或最后一个失败结果
    """
    import json as _json

    # 尝试主函数
    try:
        result = primary(**shared_kwargs)
        parsed = _json.loads(result) if isinstance(result, str) else result
        if isinstance(parsed, dict) and parsed.get("ok"):
            # 标记数据源等级
            parsed["_tier"] = "primary"
            return _json.dumps(parsed, ensure_ascii=False)
        last_error = parsed.get("error", "未知错误") if isinstance(parsed, dict) else str(parsed)
    except Exception as e:
        last_error = f"{type(e).__name__}: {str(e)[:200]}"

    # 尝试兜底函数
    for i, fb_func in enumerate(fallbacks):
        try:
            result = fb_func(**shared_kwargs)
            parsed = _json.loads(result) if isinstance(result, str) else result
            if isinstance(parsed, dict) and parsed.get("ok"):
                parsed["_tier"] = f"fallback_{i+1}"
                parsed["_fallback_from"] = primary.__name__
                return _json.dumps(parsed, ensure_ascii=False)
            last_error = parsed.get("error", "未知错误") if isinstance(parsed, dict) else str(parsed)
        except Exception as e:
            last_error = f"{type(e).__name__}: {str(e)[:200]}"
            continue

    # 全部失败
    return _json.dumps({
        "ok": False,
        "error": f"主数据源及所有兜底均失败: {last_error}",
        "_tier": "all_failed",
    }, ensure_ascii=False)


def run_with_fallback(tool_name: str, tool_registry: dict[str, Callable], **kwargs) -> str:
    """按工具名执行，自动查找兜底链。

    Args:
        tool_name: 工具名
        tool_registry: 工具名 -> 函数 的映射
        **kwargs: 传递给工具的参数

    Returns:
        JSON 结果字符串
    """
    primary_func = tool_registry.get(tool_name)
    if not primary_func:
        return json.dumps({
            "ok": False,
            "error": f"工具 {tool_name} 未注册",
        }, ensure_ascii=False)

    info = TOOL_TIERS.get(tool_name)
    fallback_names = info[1] if info else []
    fallback_funcs = [tool_registry[name] for name in fallback_names if name in tool_registry]

    return with_fallback(primary_func, fallback_funcs, **kwargs)
