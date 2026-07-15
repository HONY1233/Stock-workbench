"""市场数据源：资金流向、融资融券、大宗交易、龙虎榜等。"""
from __future__ import annotations
import json

from pydantic import BaseModel, Field, field_validator

import akshare as ak

from core.helpers import _df_to_records
from core.registry import call_unified


_READ_ONLY = {"readOnlyHint": True}


class _NorthboundFlowInput(BaseModel):
    symbol: str = Field("北向资金", description="查询标的，如 '北向资金'、'沪股通'、个股代码等")

    @field_validator("symbol")
    @classmethod
    def _strip(cls, v: str) -> str:
        return v.strip()


class _StockFundFlowInput(BaseModel):
    symbol: str = Field(..., description="股票代码，如 600519")
    indicator: str = Field("今日", description="时间周期，可选 '今日'/'3日'/'5日'/'10日'")

    @field_validator("symbol")
    @classmethod
    def _clean(cls, v: str) -> str:
        v = v.strip().replace("sh", "").replace("sz", "").replace(".SH", "").replace(".SZ", "")
        if not v:
            raise ValueError("symbol 不能为空")
        return v


class _MarginTradingInput(BaseModel):
    market: str = Field("sh", description="市场，'sh'为沪市，'sz'为深市")
    date: str = Field("", description="查询日期，格式 YYYYMMDD，默认为最新")

    @field_validator("date")
    @classmethod
    def _clean_date(cls, v: str) -> str:
        return v.replace("-", "") if v else v


class _BlockTradeInput(BaseModel):
    date: str = Field("", description="查询日期，格式 YYYYMMDD 或 YYYY-MM-DD，默认为最新")

    @field_validator("date")
    @classmethod
    def _clean_date(cls, v: str) -> str:
        return v.replace("-", "") if v else v


class _HolderCountInput(BaseModel):
    date: str = Field("", description="统计截止日期，如 20230930（YYYYMMDD格式），默认为最新")

    @field_validator("date")
    @classmethod
    def _clean_date(cls, v: str) -> str:
        return v.replace("-", "") if v else v


class _LockupReleaseInput(BaseModel):
    market: str = Field("em", description="数据源，'em'为东财(默认)，'sina'为新浪")


class _ResearchReportInput(BaseModel):
    symbol: str = Field(..., description="股票代码，如 600519")
    indicator: str = Field("一致预期EPS", description="指标类型，如 '一致预期EPS'/'一致预期ROE'/'一致预期PE'等")

    @field_validator("symbol")
    @classmethod
    def _clean(cls, v: str) -> str:
        v = v.strip().replace("sh", "").replace("sz", "").replace(".SH", "").replace(".SZ", "")
        if not v:
            raise ValueError("symbol 不能为空")
        return v


class _EpsForecastInput(BaseModel):
    symbol: str = Field(..., description="股票代码，如 600519")

    @field_validator("symbol")
    @classmethod
    def _clean(cls, v: str) -> str:
        v = v.strip().replace("sh", "").replace("sz", "").replace(".SH", "").replace(".SZ", "")
        if not v:
            raise ValueError("symbol 不能为空")
        return v


class _LimitUpBrokenInput(BaseModel):
    date: str = Field("", description="查询日期，格式 YYYYMMDD，如 20260710")

    @field_validator("date")
    @classmethod
    def _clean_date(cls, v: str) -> str:
        return v.replace("-", "") if v else v


class _LimitUpPreviousInput(BaseModel):
    date: str = Field("", description="查询日期，格式 YYYYMMDD，如 20260710")

    @field_validator("date")
    @classmethod
    def _clean_date(cls, v: str) -> str:
        return v.replace("-", "") if v else v


class _LimitUpStrongInput(BaseModel):
    date: str = Field("", description="查询日期，格式 YYYYMMDD，如 20260710")

    @field_validator("date")
    @classmethod
    def _clean_date(cls, v: str) -> str:
        return v.replace("-", "") if v else v


class _OptionTQuoteInput(BaseModel):
    symbol: str = Field("sh510300", description="期权标的代码，如 sh510300(沪深300ETF)/sh510050(上证50ETF)")

    @field_validator("symbol")
    @classmethod
    def _clean(cls, v: str) -> str:
        return v.strip().replace("sh", "").replace("sz", "").replace(".SH", "").replace(".SZ", "")


class _HotRankInput(BaseModel):
    limit: int = Field(100, ge=1, le=500, description="返回条数")


class _ConceptBelongInput(BaseModel):
    symbol: str = Field("", description="股票代码（可选），如 600519，传入则过滤出该股所属概念")

    @field_validator("symbol")
    @classmethod
    def _clean(cls, v: str) -> str:
        return v.strip().replace("sh", "").replace("sz", "").replace(".SH", "").replace(".SZ", "")


def register(mcp) -> list[str]:
    """注册市场数据工具，返回工具名列表。"""

    @mcp.tool(
        name="northbound_flow",
        description="北向资金(沪深港通)数据：汇总、历史、个股持股明细",
        annotations=_READ_ONLY,
    )
    def northbound_flow(symbol: str = "北向资金") -> str:
        try:
            params = _NorthboundFlowInput(symbol=symbol)
            if params.symbol in ("北向资金", "汇总", "all"):
                df = ak.stock_hsgt_fund_flow_summary_em()
            elif params.symbol in ("沪股通", "深股通", "港股通(沪)", "港股通(深)"):
                df = ak.stock_hsgt_hist_em(symbol=params.symbol)
            else:
                df = ak.stock_hsgt_individual_em(symbol=params.symbol)
            data = _df_to_records(df)
            return json.dumps({"ok": True, "data": data, "count": len(data)}, ensure_ascii=False)
        except Exception as e:
            return json.dumps(
                {"ok": False, "data": [], "count": 0, "error": f"{type(e).__name__}: {str(e)[:200]}"},
                ensure_ascii=False,
            )

    @mcp.tool(
        name="stock_fund_flow",
        description="个股资金流向：主力/大单/中单/小单净流入",
        annotations=_READ_ONLY,
    )
    def stock_fund_flow(symbol: str, indicator: str = "今日") -> str:
        try:
            params = _StockFundFlowInput(symbol=symbol, indicator=indicator)
            market = "sh" if params.symbol[0] in ("6", "9") else "sz"
            df = ak.stock_individual_fund_flow(stock=params.symbol, market=market)
            data = _df_to_records(df)
            return json.dumps({"ok": True, "data": data, "count": len(data)}, ensure_ascii=False)
        except Exception as e:
            return json.dumps(
                {"ok": False, "data": [], "count": 0, "error": f"{type(e).__name__}: {str(e)[:200]}"},
                ensure_ascii=False,
            )

    @mcp.tool(
        name="margin_trading",
        description="融资融券数据（沪市/深市）",
        annotations=_READ_ONLY,
    )
    def margin_trading(market: str = "sh", date: str = "") -> str:
        try:
            params = _MarginTradingInput(market=market, date=date)
            kwargs = {}
            if params.date:
                kwargs["date"] = params.date
            if params.market.lower() == "sz":
                df = ak.stock_margin_szse(**kwargs)
            else:
                df = ak.stock_margin_sse(**kwargs)
            data = _df_to_records(df)
            return json.dumps({"ok": True, "data": data, "count": len(data)}, ensure_ascii=False)
        except Exception as e:
            return json.dumps(
                {"ok": False, "data": [], "count": 0, "error": f"{type(e).__name__}: {str(e)[:200]}"},
                ensure_ascii=False,
            )

    @mcp.tool(
        name="block_trade",
        description="大宗交易数据",
        annotations=_READ_ONLY,
    )
    def block_trade(date: str = "") -> str:
        try:
            params = _BlockTradeInput(date=date)
            kwargs = {}
            if params.date:
                kwargs["date"] = params.date
            df = ak.stock_dzjy_mrmx(**kwargs)
            data = _df_to_records(df)
            return json.dumps({"ok": True, "data": data, "count": len(data)}, ensure_ascii=False)
        except Exception as e:
            return json.dumps(
                {"ok": False, "data": [], "count": 0, "error": f"{type(e).__name__}: {str(e)[:200]}"},
                ensure_ascii=False,
            )

    @mcp.tool(
        name="holder_count",
        description="股东户数变化（筹码集中度）",
        annotations=_READ_ONLY,
    )
    def holder_count(date: str = "") -> str:
        try:
            params = _HolderCountInput(date=date)
            if params.date:
                symbol = params.date
            else:
                from datetime import datetime
                now = datetime.now()
                y = now.year
                m = now.month
                if m <= 3:
                    symbol = f"{y - 1}0930"
                elif m <= 6:
                    symbol = f"{y}0331"
                elif m <= 9:
                    symbol = f"{y}0630"
                else:
                    symbol = f"{y}0930"
            df = ak.stock_zh_a_gdhs(symbol=symbol)
            data = _df_to_records(df)
            return json.dumps({"ok": True, "data": data, "count": len(data)}, ensure_ascii=False)
        except Exception as e:
            return json.dumps(
                {"ok": False, "data": [], "count": 0, "error": f"{type(e).__name__}: {str(e)[:200]}"},
                ensure_ascii=False,
            )

    @mcp.tool(
        name="lockup_release",
        description="限售解禁日历",
        annotations=_READ_ONLY,
    )
    def lockup_release(market: str = "em") -> str:
        try:
            params = _LockupReleaseInput(market=market)
            if params.market.lower() == "sina":
                df = ak.stock_restricted_release_queue_sina()
            else:
                df = ak.stock_restricted_release_queue_em()
            data = _df_to_records(df)
            return json.dumps({"ok": True, "data": data, "count": len(data)}, ensure_ascii=False)
        except Exception as e:
            return json.dumps(
                {"ok": False, "data": [], "count": 0, "error": f"{type(e).__name__}: {str(e)[:200]}"},
                ensure_ascii=False,
            )

    @mcp.tool(
        name="research_report",
        description="研报列表（个股盈利预测）",
        annotations=_READ_ONLY,
    )
    def research_report(symbol: str, indicator: str = "一致预期EPS") -> str:
        try:
            params = _ResearchReportInput(symbol=symbol, indicator=indicator)
            df = ak.stock_profit_forecast_ths(symbol=params.symbol, indicator=params.indicator)
            data = _df_to_records(df)
            return json.dumps({"ok": True, "data": data, "count": len(data)}, ensure_ascii=False)
        except Exception as e:
            return json.dumps(
                {"ok": False, "data": [], "count": 0, "error": f"{type(e).__name__}: {str(e)[:200]}"},
                ensure_ascii=False,
            )

    @mcp.tool(
        name="eps_forecast",
        description="一致预期EPS（同花顺）",
        annotations=_READ_ONLY,
    )
    def eps_forecast(symbol: str) -> str:
        try:
            params = _EpsForecastInput(symbol=symbol)
            df = ak.stock_profit_forecast_ths(symbol=params.symbol, indicator="一致预期EPS")
            data = _df_to_records(df)
            return json.dumps({"ok": True, "data": data, "count": len(data)}, ensure_ascii=False)
        except Exception as e:
            return json.dumps(
                {"ok": False, "data": [], "count": 0, "error": f"{type(e).__name__}: {str(e)[:200]}"},
                ensure_ascii=False,
            )

    @mcp.tool(
        name="limit_up_broken",
        description="炸板池：曾涨停又开板的股票",
        annotations=_READ_ONLY,
    )
    def limit_up_broken(date: str = "") -> str:
        try:
            params = _LimitUpBrokenInput(date=date)
            if not params.date:
                from datetime import datetime, timedelta
                d = (datetime.now() - timedelta(days=1)).strftime("%Y%m%d")
            else:
                d = params.date
            df = ak.stock_zt_pool_dtgc_em(date=d)
            data = _df_to_records(df)
            return json.dumps({"ok": True, "data": data, "count": len(data)}, ensure_ascii=False)
        except Exception as e:
            return json.dumps(
                {"ok": False, "data": [], "count": 0, "error": f"{type(e).__name__}: {str(e)[:200]}"},
                ensure_ascii=False,
            )

    @mcp.tool(
        name="limit_up_previous",
        description="昨日涨停池（今日表现）",
        annotations=_READ_ONLY,
    )
    def limit_up_previous(date: str = "") -> str:
        try:
            params = _LimitUpPreviousInput(date=date)
            if not params.date:
                from datetime import datetime, timedelta
                d = (datetime.now() - timedelta(days=1)).strftime("%Y%m%d")
            else:
                d = params.date
            df = ak.stock_zt_pool_previous_em(date=d)
            data = _df_to_records(df)
            return json.dumps({"ok": True, "data": data, "count": len(data)}, ensure_ascii=False)
        except Exception as e:
            return json.dumps(
                {"ok": False, "data": [], "count": 0, "error": f"{type(e).__name__}: {str(e)[:200]}"},
                ensure_ascii=False,
            )

    @mcp.tool(
        name="limit_up_strong",
        description="强势股池（连板等）",
        annotations=_READ_ONLY,
    )
    def limit_up_strong(date: str = "") -> str:
        try:
            params = _LimitUpStrongInput(date=date)
            if not params.date:
                from datetime import datetime, timedelta
                d = (datetime.now() - timedelta(days=1)).strftime("%Y%m%d")
            else:
                d = params.date
            df = ak.stock_zt_pool_strong_em(date=d)
            data = _df_to_records(df)
            return json.dumps({"ok": True, "data": data, "count": len(data)}, ensure_ascii=False)
        except Exception as e:
            return json.dumps(
                {"ok": False, "data": [], "count": 0, "error": f"{type(e).__name__}: {str(e)[:200]}"},
                ensure_ascii=False,
            )

    @mcp.tool(
        name="option_t_quote",
        description="ETF期权实时行情",
        annotations=_READ_ONLY,
    )
    def option_t_quote(symbol: str = "sh510300") -> str:
        try:
            params = _OptionTQuoteInput(symbol=symbol)
            try:
                df = ak.option_current_em()
            except Exception:
                df = ak.option_current_day_sse()
            data = _df_to_records(df)
            return json.dumps({"ok": True, "data": data, "count": len(data)}, ensure_ascii=False)
        except Exception as e:
            return json.dumps(
                {"ok": False, "data": [], "count": 0, "error": f"{type(e).__name__}: {str(e)[:200]}"},
                ensure_ascii=False,
            )

    @mcp.tool(
        name="hot_rank",
        description="东财人气排行榜",
        annotations=_READ_ONLY,
    )
    def hot_rank(limit: int = 100) -> str:
        try:
            params = _HotRankInput(limit=limit)
            try:
                df = ak.stock_hot_rank_em()
                data = _df_to_records(df, params.limit)
                return json.dumps({"ok": True, "data": data, "count": len(data)}, ensure_ascii=False)
            except Exception:
                ok, fb_data, _ = call_unified("sector_realtime", {}, limit=params.limit)
                if ok and fb_data:
                    return json.dumps(
                        {"ok": True, "data": fb_data, "count": len(fb_data)},
                        ensure_ascii=False,
                    )
                raise Exception("板块行情兜底也失败")
        except Exception as e:
            return json.dumps(
                {"ok": False, "data": [], "count": 0, "error": f"{type(e).__name__}: {str(e)[:200]}"},
                ensure_ascii=False,
            )

    @mcp.tool(
        name="concept_belong",
        description="个股概念板块归属",
        annotations=_READ_ONLY,
    )
    def concept_belong(symbol: str = "") -> str:
        try:
            params = _ConceptBelongInput(symbol=symbol)
            try:
                df = ak.stock_board_concept_name_em()
                data = _df_to_records(df)
                if params.symbol:
                    filtered = []
                    for item in data:
                        item_code = str(item.get("代码", item.get("股票代码", "")))
                        if params.symbol in item_code:
                            filtered.append(item)
                    if filtered:
                        data = filtered
                return json.dumps({"ok": True, "data": data, "count": len(data)}, ensure_ascii=False)
            except Exception:
                ok, fb_data, _ = call_unified("sector_realtime", {}, limit=100)
                if ok and fb_data:
                    return json.dumps(
                        {"ok": True, "data": fb_data, "count": len(fb_data)},
                        ensure_ascii=False,
                    )
                raise Exception("板块行情兜底也失败")
        except Exception as e:
            return json.dumps(
                {"ok": False, "data": [], "count": 0, "error": f"{type(e).__name__}: {str(e)[:200]}"},
                ensure_ascii=False,
            )

    return [
        "northbound_flow",
        "stock_fund_flow",
        "margin_trading",
        "block_trade",
        "holder_count",
        "lockup_release",
        "research_report",
        "eps_forecast",
        "limit_up_broken",
        "limit_up_previous",
        "limit_up_strong",
        "option_t_quote",
        "hot_rank",
        "concept_belong",
    ]
