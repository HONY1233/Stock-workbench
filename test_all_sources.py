#!/usr/bin/env python3
"""全量测试：按分类验证所有数据源能否正常拉取。"""
import json
import sys
import time
import traceback

from core.registry import SourceRegistry, load_custom_sources, call_unified

registry = SourceRegistry()

# 结果统计
results = {"pass": [], "fail": [], "skip": []}


def test_yaml_source(alias: str, params: dict = None, source_preference: str = "any"):
    """测试一个 YAML 配置的数据源。"""
    cfg = registry.get_source(alias)
    if not cfg:
        results["skip"].append({"name": alias, "reason": "接口不存在"})
        return

    has_source = cfg.get("axdata") or cfg.get("akshare")
    if not has_source:
        results["skip"].append({"name": alias, "reason": "无数据源配置"})
        return

    try:
        ok, data, source = call_unified(alias, registry.sources, source_preference=source_preference, **(params or {}))
        if ok:
            count = len(data) if data else 0
            results["pass"].append({"name": alias, "source": source, "count": count})
        else:
            err = data[0].get("error", "未知错误") if data else "未知错误"
            results["fail"].append({"name": alias, "source": source, "error": err[:100]})
    except Exception as e:
        results["fail"].append({"name": alias, "error": f"{type(e).__name__}: {str(e)[:100]}"})


def test_custom_tool(tool_name: str):
    """测试自定义工具（通过导入 sources 模块调用）。"""
    try:
        import akshare as ak
        # 用 akshare 函数名直接调用简单测试
        func_map = {
            "cls_telegraph": None,  # 需要特殊处理
            "news_cctv": lambda: ak.news_cctv(),
            "news_economic_calendar": lambda: ak.news_economic_baidu(),
            "stock_news": lambda: ak.stock_news_em(symbol="600519"),
            "global_news": lambda: ak.stock_info_global_em(),
            "wallstreet_news": lambda: ak.macro_info_ws(),
            "futures_news_shmet": lambda: ak.futures_news_shmet(),
            "stock_profile_cninfo": lambda: ak.stock_profile_cninfo(symbol="600519"),
            "stock_financial_abstract_cninfo": lambda: ak.stock_financial_abstract(symbol="600519"),
            "stock_dividend_cninfo": lambda: ak.stock_dividend_cninfo(symbol="600519"),
            "sector_industry_list": lambda: ak.stock_board_industry_name_ths(),
            "sector_concept_list": lambda: ak.stock_board_concept_name_ths(),
            "northbound_flow": lambda: ak.stock_hsgt_individual_em(symbol="沪股通"),
            "stock_fund_flow": lambda: ak.stock_individual_fund_flow(symbol="600519", market="sh"),
            "margin_trading": lambda: ak.stock_margin_sse(start_date="20250101", end_date="20250110"),
            "block_trade": lambda: ak.stock_dzjy_mrmx(start_date="20250101", end_date="20250110"),
            "holder_count": lambda: ak.stock_zh_a_gdhs(symbol="600519"),
            "hot_rank": lambda: ak.stock_hot_rank_em(),
            "concept_belong": lambda: ak.stock_board_concept_name_em(symbol="600519"),
            "limit_up_broken": lambda: ak.stock_zt_pool_dtgc_em(date="20250110"),
            "limit_up_previous": lambda: ak.stock_zt_pool_previous_em(date="20250110"),
            "limit_up_strong": lambda: ak.stock_zt_pool_strong_em(date="20250110"),
            "option_t_quote": lambda: ak.option_current_em(),
            "reuters_news": None,  # 需要网络
            "bloomberg_news": None,  # 需要网络
            "bloomberg_billionaires": lambda: ak.index_bloomberg_billionaires(),
            "global_news_search": None,  # 聚合搜索
        }
        if tool_name not in func_map:
            results["skip"].append({"name": tool_name, "reason": "未映射测试函数"})
            return
        fn = func_map[tool_name]
        if fn is None:
            results["skip"].append({"name": tool_name, "reason": "需要特殊网络环境"})
            return
        df = fn()
        count = len(df) if df is not None and not df.empty else 0
        results["pass"].append({"name": tool_name, "count": count})
    except Exception as e:
        results["fail"].append({"name": tool_name, "error": f"{type(e).__name__}: {str(e)[:100]}"})


if __name__ == "__main__":
    print("=" * 60)
    print("1. 测试分类查询工具")
    print("=" * 60)

    # 测试 list_interfaces_by_source
    providers = registry.get_providers()
    print(f"\nYAML 配置中的数据提供商: {sorted(providers)}")
    print(f"接口总数: {len(registry.sources)}")

    for p in sorted(providers):
        tools = list(registry.list_by_provider(p).keys())
        print(f"  {p}: {len(tools)} 个接口 → {tools[:5]}{'...' if len(tools) > 5 else ''}")

    print("\n" + "=" * 60)
    print("2. 测试 YAML 配置源数据拉取")
    print("=" * 60)

    # 按分类测试关键接口
    test_cases = [
        # 个股
        ("stock_daily", {"symbol": "600519"}),
        ("stock_realtime", {}),
        # 指数
        ("index_daily", {"symbol": "sh000001"}),
        ("index_realtime", {}),
        # ETF
        ("etf_daily", {"symbol": "sh510300"}),
        ("etf_realtime", {}),
        # 期货
        ("futures_daily", {"symbol": "V0"}),
        ("futures_realtime", {}),
        # 涨跌停/板块
        ("limit_up_pool", {}),
        ("limit_down_pool", {}),
        ("sector_realtime", {}),
        ("market_index_realtime", {}),
        # 财联社
        ("cls_telegraph", {}),
        ("cls_market_emotion", {}),
        ("cls_limit_up_pool", {}),
        ("cls_sector_heat", {}),
        ("cls_market_wind", {}),
        ("cls_market_mainline", {}),
        # 开盘红
        ("kph_market_emotion", {}),
        # 龙虎榜
        ("lhb_daily", {}),
        # 期权
        ("option_commodity_list", {}),
        # 新闻
        ("news_cctv", {}),
        ("economic_calendar", {}),
        ("stock_news", {"symbol": "600519"}),
        # 外围新闻
        ("global_news_em", {}),
        ("global_news_sina", {}),
        ("global_news_ths", {}),
        ("wallstreet_news", {}),
        ("futures_news_shmet", {}),
        # 外围指数
        ("index_us_daily", {"symbol": ".DJI"}),
        ("index_hk_daily", {"symbol": "HSI"}),
        ("index_global_list", {}),
        ("futures_global_spot", {}),
        # 补充
        ("northbound_flow", {}),
        ("margin_trading", {}),
        ("block_trade", {}),
        ("holder_count", {}),
        ("hot_rank", {}),
        ("concept_belong", {"symbol": "600519"}),
        ("limit_up_broken", {"date": "20250711"}),
        ("limit_up_strong", {"date": "20250711"}),
        # 巨潮（需要 code 参数）
        ("cninfo_announcements", {"code": "600519"}),
        ("stock_profile_cninfo", {"code": "600519"}),
        ("stock_dividend_cninfo", {"code": "600519"}),
        # 国际
        ("bloomberg_billionaires", {}),
        # 其他
        ("etf_spot", {}),
        ("lockup_release", {}),
        ("research_report", {"symbol": "600519"}),
        ("eps_forecast", {"symbol": "600519"}),
    ]

    for alias, params in test_cases:
        print(f"\n  测试 {alias}...", end=" ")
        test_yaml_source(alias, params)
        # 找结果
        last_result = None
        for r in results["pass"]:
            if r["name"] == alias:
                last_result = r
                break
        for r in results["fail"]:
            if r["name"] == alias:
                last_result = r
                break
        for r in results["skip"]:
            if r["name"] == alias:
                last_result = r
                break

        if last_result:
            if last_result in results["pass"]:
                print(f"OK (count={last_result['count']}, source={last_result.get('source', '')})")
            elif last_result in results["fail"]:
                print(f"FAIL ({last_result.get('error', '')[:60]})")
            else:
                print(f"SKIP ({last_result.get('reason', '')})")

        time.sleep(0.3)  # 避免限流

    print("\n" + "=" * 60)
    print("3. 测试按来源按需调用")
    print("=" * 60)

    # 测试 source_preference
    sp_tests = [
        ("stock_daily", {"symbol": "600519"}, "akshare_only"),
        ("stock_daily", {"symbol": "600519"}, "any"),
    ]
    for alias, params, sp in sp_tests:
        print(f"\n  测试 {alias} source_preference={sp}...", end=" ")
        try:
            ok, data, source = call_unified(alias, registry.sources, source_preference=sp, **params)
            if ok:
                print(f"OK (source={source}, count={len(data) if data else 0})")
            else:
                err = data[0].get("error", "未知") if data else "未知"
                print(f"FAIL ({err[:60]})")
        except Exception as e:
            print(f"ERROR ({type(e).__name__}: {str(e)[:60]})")

    # 汇总
    print("\n" + "=" * 60)
    print("测试结果汇总")
    print("=" * 60)
    print(f"\n通过: {len(results['pass'])}")
    print(f"失败: {len(results['fail'])}")
    print(f"跳过: {len(results['skip'])}")

    if results["fail"]:
        print("\n失败详情:")
        for r in results["fail"]:
            print(f"  - {r['name']}: {r.get('error', '')[:80]}")

    if results["skip"]:
        print("\n跳过详情:")
        for r in results["skip"]:
            print(f"  - {r['name']}: {r.get('reason', '')}")

    sys.exit(0 if not results["fail"] else 1)
