"""ETF、期货、外围指数数据源。"""
from __future__ import annotations
import json
from typing import Optional

import akshare as ak

from core.helpers import _df_to_records


def register(mcp) -> list[str]:
    """注册 ETF/期货/指数工具，返回工具名列表。"""

    @mcp.tool(description="获取ETF实时行情列表（东方财富），返回全部ETF的当前报价")
    def fund_etf_spot(limit: int = 50) -> str:
        """获取ETF实时行情列表。

        Args:
            limit: 返回条数，默认 50 条

        Returns:
            JSON 格式的ETF实时行情列表
        """
        try:
            df = ak.fund_etf_spot_em()
            data = _df_to_records(df, limit)
            return json.dumps({
                "ok": True,
                "source": "eastmoney",
                "count": len(data),
                "data": data,
            }, ensure_ascii=False)
        except Exception as e:
            return json.dumps({"ok": False, "error": f"{type(e).__name__}: {str(e)[:200]}"}, ensure_ascii=False)

    @mcp.tool(description="获取ETF历史日线行情（新浪财经），如 510300 为沪深300ETF")
    def fund_etf_daily(symbol: str, limit: int = 30) -> str:
        """获取ETF历史日线数据。

        Args:
            symbol: ETF代码，如 sz510300（沪深300ETF）、sz159915（创业板ETF）、sh510050（50ETF）
            limit: 返回条数，默认 30 条

        Returns:
            JSON 格式的ETF日线数据
        """
        try:
            code = symbol.lower()
            if not (code.startswith("sh") or code.startswith("sz")):
                if len(code) == 6:
                    code = "sh" + code if code[0] == "5" else "sz" + code
                else:
                    code = "sh" + code
            df = ak.fund_etf_hist_sina(symbol=code)
            data = _df_to_records(df, limit)
            if data:
                return json.dumps({
                    "ok": True,
                    "source": "sina",
                    "symbol": symbol,
                    "count": len(data),
                    "start": data[0].get("date", ""),
                    "end": data[-1].get("date", ""),
                    "data": data,
                }, ensure_ascii=False)
            return json.dumps({"ok": False, "error": "未获取到数据"}, ensure_ascii=False)
        except Exception as e:
            return json.dumps({"ok": False, "error": f"{type(e).__name__}: {str(e)[:200]}"}, ensure_ascii=False)

    @mcp.tool(description="获取期货实时行情（新浪财经），返回国内期货所有品种的实时报价")
    def futures_realtime() -> str:
        """获取国内期货实时行情。

        Returns:
            JSON 格式的期货实时行情列表
        """
        try:
            # 修复: akshare 中函数名为 futures_zh_realtime_sina，不是 futures_zh_realtime
            try:
                df = ak.futures_zh_realtime_sina()
            except AttributeError:
                df = ak.futures_main_sina()
            data = _df_to_records(df)
            return json.dumps({
                "ok": True,
                "source": "sina",
                "count": len(data),
                "data": data,
            }, ensure_ascii=False)
        except Exception as e:
            return json.dumps({"ok": False, "error": f"{type(e).__name__}: {str(e)[:200]}"}, ensure_ascii=False)

    @mcp.tool(description="获取期货历史日线行情（新浪财经），如 V0 为PVC主力")
    def futures_daily(symbol: str, limit: int = 30) -> str:
        """获取期货历史日线数据。

        Args:
            symbol: 期货合约代码，如 V0（PVC主力）、RB0（螺纹钢主力）、AU0（黄金主力）
            limit: 返回条数，默认 30 条

        Returns:
            JSON 格式的期货日线数据
        """
        try:
            df = ak.futures_zh_daily_sina(symbol=symbol)
            data = _df_to_records(df, limit)
            if data:
                return json.dumps({
                    "ok": True,
                    "source": "sina",
                    "symbol": symbol,
                    "count": len(data),
                    "start": data[0].get("date", ""),
                    "end": data[-1].get("date", ""),
                    "data": data,
                }, ensure_ascii=False)
            return json.dumps({"ok": False, "error": "未获取到数据"}, ensure_ascii=False)
        except Exception as e:
            return json.dumps({"ok": False, "error": f"{type(e).__name__}: {str(e)[:200]}"}, ensure_ascii=False)

    @mcp.tool(description="获取全球期货实时行情（东方财富），包含CBOT/NYMEX/COMEX/LME等")
    def futures_global_spot(limit: int = 50) -> str:
        """获取全球期货实时行情。

        Args:
            limit: 返回条数，默认 50 条

        Returns:
            JSON 格式的全球期货行情列表
        """
        try:
            df = ak.futures_global_spot_em()
            data = _df_to_records(df, limit)
            return json.dumps({
                "ok": True,
                "source": "eastmoney",
                "count": len(data),
                "data": data,
            }, ensure_ascii=False)
        except Exception as e:
            return json.dumps({"ok": False, "error": f"{type(e).__name__}: {str(e)[:200]}"}, ensure_ascii=False)

    @mcp.tool(description="获取美股指数历史日线（新浪财经），如道琼斯、纳斯达克、标普500")
    def index_us_daily(symbol: str, limit: int = 30) -> str:
        """获取美股指数历史日线数据。

        Args:
            symbol: 指数代码，如 .DJI（道琼斯）、.IXIC（纳斯达克）、.INX（标普500）
            limit: 返回条数，默认 30 条

        Returns:
            JSON 格式的美股指数日线数据
        """
        try:
            df = ak.index_us_stock_sina(symbol=symbol)
            data = _df_to_records(df, limit)
            if data:
                return json.dumps({
                    "ok": True,
                    "source": "sina",
                    "symbol": symbol,
                    "count": len(data),
                    "start": data[0].get("date", ""),
                    "end": data[-1].get("date", ""),
                    "data": data,
                }, ensure_ascii=False)
            return json.dumps({"ok": False, "error": "未获取到数据"}, ensure_ascii=False)
        except Exception as e:
            return json.dumps({"ok": False, "error": f"{type(e).__name__}: {str(e)[:200]}"}, ensure_ascii=False)

    @mcp.tool(description="获取港股指数历史日线（新浪财经），如恒生指数、国企指数")
    def index_hk_daily(symbol: str, limit: int = 30) -> str:
        """获取港股指数历史日线数据。

        Args:
            symbol: 指数代码，如 HSI（恒生指数）、HSCEI（国企指数）、HSTECH（恒生科技）
            limit: 返回条数，默认 30 条

        Returns:
            JSON 格式的港股指数日线数据
        """
        try:
            df = ak.stock_hk_index_daily_sina(symbol=symbol)
            data = _df_to_records(df, limit)
            if data:
                return json.dumps({
                    "ok": True,
                    "source": "sina",
                    "symbol": symbol,
                    "count": len(data),
                    "start": data[0].get("date", ""),
                    "end": data[-1].get("date", ""),
                    "data": data,
                }, ensure_ascii=False)
            return json.dumps({"ok": False, "error": "未获取到数据"}, ensure_ascii=False)
        except Exception as e:
            return json.dumps({"ok": False, "error": f"{type(e).__name__}: {str(e)[:200]}"}, ensure_ascii=False)

    @mcp.tool(description="获取全球指数名称代码表，用于查询外围指数的代码")
    def index_global_list() -> str:
        """获取全球指数名称代码表。

        Returns:
            JSON 格式的全球指数名称与代码对照表
        """
        try:
            df = ak.index_global_name_table()
            data = _df_to_records(df)
            return json.dumps({
                "ok": True,
                "source": "sina",
                "count": len(data),
                "data": data,
            }, ensure_ascii=False)
        except Exception as e:
            return json.dumps({"ok": False, "error": f"{type(e).__name__}: {str(e)[:200]}"}, ensure_ascii=False)

    return ["fund_etf_spot", "fund_etf_daily", "futures_realtime", "futures_daily",
            "futures_global_spot", "index_us_daily", "index_hk_daily", "index_global_list"]
