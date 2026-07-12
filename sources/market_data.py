"""市场数据源：腾讯行情、资金流向、融资融券、大宗交易、龙虎榜等。"""
from __future__ import annotations
import json
from typing import Optional

import akshare as ak

from core.helpers import _df_to_records
from core.registry import call_unified


def register(mcp) -> list[str]:
    """注册市场数据工具，返回工具名列表。"""

    @mcp.tool(description="腾讯财经实时行情：PE/PB/市值/换手率/涨跌停价，不封IP")
    def tencent_realtime_quote(symbol: str) -> str:
        """腾讯财经实时行情，支持个股、指数、ETF。

        Args:
            symbol: 股票代码，如 sh600519、sz000001、sh000001(指数)、sh510300(ETF)，多个用逗号分隔

        Returns:
            JSON 格式的实时行情数据，含PE_TTM/PB/总市值/换手率/涨停价/跌停价
        """
        try:
            import urllib.request
            codes = [s.strip() for s in symbol.split(",") if s.strip()]
            # 腾讯行情接口：sh600519->sh600519, 600519->sh600519
            qt_codes = []
            for c in codes:
                cl = c.lower()
                if cl.startswith("sh") or cl.startswith("sz") or cl.startswith("hk"):
                    qt_codes.append(c.lower())
                elif cl.endswith(".sh") or cl.endswith(".sz"):
                    qt_codes.append(c[-2:].lower() + c[:-3])
                else:
                    if c[0] in ("6", "9"):
                        qt_codes.append("sh" + c)
                    else:
                        qt_codes.append("sz" + c)
            url = "https://qt.gtimg.cn/q=" + ",".join(qt_codes)
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=10) as resp:
                raw = resp.read()
            text = raw.decode("gbk", errors="replace")
            results = []
            for segment in text.split(";"):
                segment = segment.strip()
                if not segment or "~" not in segment:
                    continue
                # 提取引号内内容
                eq_idx = segment.find("=")
                if eq_idx < 0:
                    continue
                content = segment[eq_idx + 1:].strip('"').strip()
                fields = content.split("~")
                if len(fields) < 50:
                    continue
                item = {
                    "代码": fields[2],
                    "名称": fields[1],
                    "现价": fields[3],
                    "昨收": fields[4],
                    "今开": fields[5],
                    "成交量(手)": fields[6],
                    "成交额(万)": fields[37],
                    "涨跌额": fields[31],
                    "涨跌幅(%)": fields[32],
                    "最高": fields[33],
                    "最低": fields[34],
                    "PE_TTM": fields[39],
                    "PB": fields[46],
                    "总市值(万)": fields[45],
                    "流通市值(万)": fields[44],
                    "换手率(%)": fields[38],
                    "涨停价": fields[47],
                    "跌停价": fields[48],
                    "60日均价": fields[42],
                    "年初至今涨跌幅(%)": fields[43],
                }
                results.append(item)
            if not results:
                return json.dumps({"ok": False, "error": "未获取到数据，请检查代码格式"}, ensure_ascii=False)
            return json.dumps({
                "ok": True,
                "source": "tencent",
                "count": len(results),
                "data": results,
            }, ensure_ascii=False)
        except Exception as e:
            return json.dumps({"ok": False, "error": f"{type(e).__name__}: {str(e)[:200]}"}, ensure_ascii=False)

    @mcp.tool(description="北向资金(沪深港通)个股持股明细")
    def northbound_flow(symbol: str = "北向资金") -> str:
        """获取北向资金(沪深港通)持股明细数据。

        Args:
            symbol: 标的名称，默认"北向资金"；也可传个股代码如"600519"

        Returns:
            JSON 格式的北向资金数据
        """
        try:
            # stock_hsgt_individual_em 的 symbol 参数是股票代码，不是"北向资金"
            # 尝试多种调用方式
            if symbol in ("北向资金", "沪股通", "深股通", "港股通"):
                # 获取汇总数据
                df = ak.stock_market_fund_flow()
                source = "eastmoney汇总"
            else:
                df = ak.stock_hsgt_individual_em(symbol=symbol)
                source = "eastmoney"
            data = _df_to_records(df)
            return json.dumps({
                "ok": True,
                "source": source,
                "count": len(data),
                "data": data,
            }, ensure_ascii=False)
        except Exception as e:
            return json.dumps({"ok": False, "error": f"{type(e).__name__}: {str(e)[:200]}"}, ensure_ascii=False)

    @mcp.tool(description="个股资金流向：主力/大单/中单/小单净流入")
    def stock_fund_flow(symbol: str, indicator: str = "今日") -> str:
        """获取个股资金流向数据。

        Args:
            symbol: 股票代码，如 600519
            indicator: 时间周期，可选 "今日"/"3日"/"5日"/"10日"，默认 "今日"

        Returns:
            JSON 格式的个股资金流向数据
        """
        try:
            code = symbol.replace("sh", "").replace("sz", "").replace(".SH", "").replace(".SZ", "")
            market = "sh" if code[0] in ("6", "9") else "sz"
            # L2 兜底：东财 push2 失败时，降级到腾讯实时行情（L1，不封 IP）
            try:
                df = ak.stock_individual_fund_flow(stock=code, market=market)
                data = _df_to_records(df)
                return json.dumps({
                    "ok": True,
                    "symbol": code,
                    "indicator": indicator,
                    "source": "eastmoney",
                    "_tier": "L2",
                    "count": len(data),
                    "data": data,
                }, ensure_ascii=False)
            except Exception:
                # 兜底：使用腾讯实时行情（L1 级别，不封 IP）
                prefix = "sh" if code[0] in ("6", "9") else "sz"
                r = tencent_realtime_quote(symbol=f"{prefix}{code}")
                d = json.loads(r)
                if d.get("ok") and d.get("data"):
                    return json.dumps({
                        "ok": True,
                        "symbol": code,
                        "indicator": indicator,
                        "source": "tencent",
                        "_tier": "L2_fallback_L1",
                        "count": d.get("count", 1),
                        "data": d["data"],
                        "note": "个股资金流接口被封，已降级为腾讯实时行情",
                    }, ensure_ascii=False)
                raise Exception("腾讯行情兜底也失败")
        except Exception as e:
            return json.dumps({"ok": False, "error": f"{type(e).__name__}: {str(e)[:200]}"}, ensure_ascii=False)

    @mcp.tool(description="融资融券数据（沪市/深市）")
    def margin_trading(market: str = "sh", date: str = "") -> str:
        """获取融资融券数据。

        Args:
            market: 市场，"sh"为沪市，"sz"为深市，默认 "sh"
            date: 查询日期，格式 YYYYMMDD，默认为最新

        Returns:
            JSON 格式的融资融券数据
        """
        try:
            params = {}
            if date:
                params["date"] = date.replace("-", "")
            if market.lower() == "sz":
                df = ak.stock_margin_szse(**params)
                source = "szse"
            else:
                df = ak.stock_margin_sse(**params)
                source = "sse"
            data = _df_to_records(df)
            return json.dumps({
                "ok": True,
                "market": market,
                "source": source,
                "count": len(data),
                "data": data,
            }, ensure_ascii=False)
        except Exception as e:
            return json.dumps({"ok": False, "error": f"{type(e).__name__}: {str(e)[:200]}"}, ensure_ascii=False)

    @mcp.tool(description="大宗交易数据")
    def block_trade(date: str = "") -> str:
        """获取大宗交易数据。

        Args:
            date: 查询日期，格式 YYYYMMDD 或 YYYY-MM-DD，默认为最新

        Returns:
            JSON 格式的大宗交易数据
        """
        try:
            params = {}
            if date:
                params["date"] = date.replace("-", "")
            df = ak.stock_dzjy_mrmx(**params)
            data = _df_to_records(df)
            return json.dumps({
                "ok": True,
                "source": "eastmoney",
                "count": len(data),
                "data": data,
            }, ensure_ascii=False)
        except Exception as e:
            return json.dumps({"ok": False, "error": f"{type(e).__name__}: {str(e)[:200]}"}, ensure_ascii=False)

    @mcp.tool(description="股东户数变化（筹码集中度）")
    def holder_count(date: str = "") -> str:
        """获取A股股东户数变化数据，用于分析筹码集中度。

        Args:
            date: 统计截止日期，如 20230930（YYYYMMDD格式），默认为最新

        Returns:
            JSON 格式的股东户数变化数据
        """
        try:
            if date:
                symbol = date.replace("-", "")
            else:
                # 使用最近的季度末
                from datetime import datetime
                now = datetime.now()
                y = now.year
                m = now.month
                if m <= 3:
                    symbol = f"{y-1}0930"
                elif m <= 6:
                    symbol = f"{y}0331"
                elif m <= 9:
                    symbol = f"{y}0630"
                else:
                    symbol = f"{y}0930"
            df = ak.stock_zh_a_gdhs(symbol=symbol)
            data = _df_to_records(df)
            return json.dumps({
                "ok": True,
                "date": symbol,
                "source": "eastmoney",
                "count": len(data),
                "data": data,
            }, ensure_ascii=False)
        except Exception as e:
            return json.dumps({"ok": False, "error": f"{type(e).__name__}: {str(e)[:200]}"}, ensure_ascii=False)

    @mcp.tool(description="限售解禁日历")
    def lockup_release(market: str = "em") -> str:
        """获取限售解禁日历数据。

        Args:
            market: 数据源，"em"为东财(默认)，"sina"为新浪

        Returns:
            JSON 格式的限售解禁数据
        """
        try:
            if market.lower() == "sina":
                df = ak.stock_restricted_release_queue_sina()
                source = "sina"
            else:
                df = ak.stock_restricted_release_queue_em()
                source = "eastmoney"
            data = _df_to_records(df)
            return json.dumps({
                "ok": True,
                "market": market,
                "source": source,
                "count": len(data),
                "data": data,
            }, ensure_ascii=False)
        except Exception as e:
            return json.dumps({"ok": False, "error": f"{type(e).__name__}: {str(e)[:200]}"}, ensure_ascii=False)

    @mcp.tool(description="研报列表（个股盈利预测）")
    def research_report(symbol: str, indicator: str = "一致预期EPS") -> str:
        """获取个股研报盈利预测数据。

        Args:
            symbol: 股票代码，如 600519
            indicator: 指标类型，可选 "一致预期EPS"/"一致预期ROE"/"一致预期PE"等，默认 "一致预期EPS"

        Returns:
            JSON 格式的研报盈利预测数据
        """
        try:
            code = symbol.replace("sh", "").replace("sz", "").replace(".SH", "").replace(".SZ", "")
            df = ak.stock_profit_forecast_ths(symbol=code, indicator=indicator)
            data = _df_to_records(df)
            return json.dumps({
                "ok": True,
                "symbol": code,
                "indicator": indicator,
                "source": "ths",
                "count": len(data),
                "data": data,
            }, ensure_ascii=False)
        except Exception as e:
            return json.dumps({"ok": False, "error": f"{type(e).__name__}: {str(e)[:200]}"}, ensure_ascii=False)

    @mcp.tool(description="一致预期EPS（同花顺）")
    def eps_forecast(symbol: str) -> str:
        """获取个股一致预期EPS数据。

        Args:
            symbol: 股票代码，如 600519

        Returns:
            JSON 格式的一致预期EPS数据
        """
        try:
            code = symbol.replace("sh", "").replace("sz", "").replace(".SH", "").replace(".SZ", "")
            df = ak.stock_profit_forecast_ths(symbol=code, indicator="一致预期EPS")
            data = _df_to_records(df)
            return json.dumps({
                "ok": True,
                "symbol": code,
                "source": "ths",
                "count": len(data),
                "data": data,
            }, ensure_ascii=False)
        except Exception as e:
            return json.dumps({"ok": False, "error": f"{type(e).__name__}: {str(e)[:200]}"}, ensure_ascii=False)

    @mcp.tool(description="炸板池：曾涨停又开板的股票")
    def limit_up_broken(date: str = "") -> str:
        """获取炸板池数据（曾涨停又开板的股票）。

        Args:
            date: 查询日期，格式 YYYYMMDD，如 20260710

        Returns:
            JSON 格式的炸板股列表
        """
        try:
            if not date:
                from datetime import datetime, timedelta
                date = (datetime.now() - timedelta(days=1)).strftime("%Y%m%d")
            else:
                date = date.replace("-", "")
            df = ak.stock_zt_pool_dtgc_em(date=date)
            data = _df_to_records(df)
            return json.dumps({
                "ok": True,
                "date": date,
                "source": "eastmoney",
                "count": len(data),
                "data": data,
            }, ensure_ascii=False)
        except Exception as e:
            return json.dumps({"ok": False, "error": f"{type(e).__name__}: {str(e)[:200]}"}, ensure_ascii=False)

    @mcp.tool(description="昨日涨停池（今日表现）")
    def limit_up_previous(date: str = "") -> str:
        """获取昨日涨停池股票今日表现数据。

        Args:
            date: 查询日期，格式 YYYYMMDD，如 20260710

        Returns:
            JSON 格式的昨日涨停池今日表现数据
        """
        try:
            if not date:
                from datetime import datetime, timedelta
                date = (datetime.now() - timedelta(days=1)).strftime("%Y%m%d")
            else:
                date = date.replace("-", "")
            df = ak.stock_zt_pool_previous_em(date=date)
            data = _df_to_records(df)
            return json.dumps({
                "ok": True,
                "source": "eastmoney",
                "count": len(data),
                "data": data,
            }, ensure_ascii=False)
        except Exception as e:
            return json.dumps({"ok": False, "error": f"{type(e).__name__}: {str(e)[:200]}"}, ensure_ascii=False)

    @mcp.tool(description="强势股池（连板等）")
    def limit_up_strong(date: str = "") -> str:
        """获取强势股池数据（连板股等）。

        Args:
            date: 查询日期，格式 YYYYMMDD，如 20260710

        Returns:
            JSON 格式的强势股池数据
        """
        try:
            if not date:
                from datetime import datetime, timedelta
                date = (datetime.now() - timedelta(days=1)).strftime("%Y%m%d")
            else:
                date = date.replace("-", "")
            df = ak.stock_zt_pool_strong_em(date=date)
            data = _df_to_records(df)
            return json.dumps({
                "ok": True,
                "source": "eastmoney",
                "count": len(data),
                "data": data,
            }, ensure_ascii=False)
        except Exception as e:
            return json.dumps({"ok": False, "error": f"{type(e).__name__}: {str(e)[:200]}"}, ensure_ascii=False)

    @mcp.tool(description="ETF期权实时行情")
    def option_t_quote(symbol: str = "sh510300") -> str:
        """获取ETF期权实时行情数据。

        Args:
            symbol: 期权标的代码，如 sh510300(沪深300ETF)/sh510050(上证50ETF)，默认 sh510300

        Returns:
            JSON 格式的期权行情数据
        """
        try:
            # option_current_em 无参数，返回全部期权行情
            # 也支持 option_current_day_sse/szse
            try:
                df = ak.option_current_em()
                source = "eastmoney"
            except Exception:
                df = ak.option_current_day_sse()
                source = "sse"
            data = _df_to_records(df)
            return json.dumps({
                "ok": True,
                "symbol": symbol,
                "source": source,
                "count": len(data),
                "data": data,
            }, ensure_ascii=False)
        except Exception as e:
            return json.dumps({"ok": False, "error": f"{type(e).__name__}: {str(e)[:200]}"}, ensure_ascii=False)

    @mcp.tool(description="东财人气排行榜")
    def hot_rank(limit: int = 100) -> str:
        """获取东方财富人气排行榜数据。

        Args:
            limit: 返回条数，默认 100 条

        Returns:
            JSON 格式的人气排行数据
        """
        try:
            # L2 兜底：东财人气榜失败时，降级到板块行情（L1，调用已通过的工具函数）
            try:
                df = ak.stock_hot_rank_em()
                data = _df_to_records(df, limit)
                return json.dumps({
                    "ok": True,
                    "source": "eastmoney",
                    "_tier": "L2",
                    "count": len(data),
                    "data": data,
                }, ensure_ascii=False)
            except Exception:
                # 兜底：通过统一注册中心调用 sector_realtime（L1 级别，内部有 axdata→akshare fallback）
                ok, fb_data, fb_source = call_unified("sector_realtime", {}, limit=limit)
                if ok and fb_data:
                    return json.dumps({
                        "ok": True,
                        "source": "sector_realtime_fallback",
                        "_tier": "L2_fallback_L1",
                        "count": len(fb_data),
                        "data": fb_data,
                        "note": "东财人气榜接口被封，已降级为板块实时行情",
                    }, ensure_ascii=False)
                raise Exception("板块行情兜底也失败")
        except Exception as e:
            return json.dumps({"ok": False, "error": f"{type(e).__name__}: {str(e)[:200]}"}, ensure_ascii=False)

    @mcp.tool(description="个股概念板块归属")
    def concept_belong(symbol: str = "") -> str:
        """获取概念板块列表，可按个股代码过滤归属概念。

        Args:
            symbol: 股票代码（可选），如 600519，传入则过滤出该股所属概念

        Returns:
            JSON 格式的概念板块数据
        """
        try:
            # L2 兜底：东财概念板块失败时，降级到板块行情（L1，调用已通过的工具函数）
            try:
                df = ak.stock_board_concept_name_em()
                data = _df_to_records(df)
                if symbol:
                    code = symbol.replace("sh", "").replace("sz", "").replace(".SH", "").replace(".SZ", "")
                    filtered = []
                    for item in data:
                        item_code = str(item.get("代码", item.get("股票代码", "")))
                        if code in item_code:
                            filtered.append(item)
                    if filtered:
                        data = filtered
                return json.dumps({
                    "ok": True,
                    "source": "eastmoney_concept",
                    "_tier": "L2",
                    "count": len(data),
                    "data": data,
                }, ensure_ascii=False)
            except Exception:
                # 兜底：通过统一注册中心调用 sector_realtime（L1 级别，内部有 axdata→akshare fallback）
                ok, fb_data, fb_source = call_unified("sector_realtime", {}, limit=100)
                if ok and fb_data:
                    return json.dumps({
                        "ok": True,
                        "source": "sector_realtime_fallback",
                        "_tier": "L2_fallback_L1",
                        "count": len(fb_data),
                        "data": fb_data,
                        "note": "东财概念板块接口被封，已降级为板块实时行情",
                    }, ensure_ascii=False)
                raise Exception("板块行情兜底也失败")
        except Exception as e:
            return json.dumps({"ok": False, "error": f"{type(e).__name__}: {str(e)[:200]}"}, ensure_ascii=False)

    return ["tencent_realtime_quote", "northbound_flow", "stock_fund_flow",
            "margin_trading", "block_trade", "holder_count", "lockup_release",
            "research_report", "eps_forecast", "limit_up_broken", "limit_up_previous",
            "limit_up_strong", "option_t_quote", "hot_rank", "concept_belong"]
