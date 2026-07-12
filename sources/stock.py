"""A股行情数据源：个股/指数的日线和实时行情。"""
from __future__ import annotations
import json
from typing import Optional

import akshare as ak

from core.helpers import _df_to_records
from core.registry import _get_sina_spot


def register(mcp) -> list[str]:
    """注册 A股行情工具，返回工具名列表。"""

    @mcp.tool(description="获取A股个股日线历史行情数据（前复权），数据来自新浪财经")
    def stock_zh_a_daily(
        symbol: str,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        limit: int = 500,
    ) -> str:
        """获取A股个股日线历史行情。

        Args:
            symbol: 股票代码，如 sh600519、sz000001、600519、000001
            start_date: 起始日期，格式 YYYY-MM-DD 或 YYYYMMDD，可选
            end_date: 结束日期，格式 YYYY-MM-DD 或 YYYYMMDD，可选，默认今天
            limit: 返回数据条数限制（取最近N条），默认 500

        Returns:
            JSON 格式的K线数据，包含 date/open/high/low/close/volume
        """
        try:
            s = symbol.lower()
            if s.startswith("sh") or s.startswith("sz"):
                code = s
            elif s.endswith(".sh") or s.endswith(".sz"):
                code = s[-2:] + s[:-3]
            else:
                if len(s) == 6 and (s[0] in "6" or s[:2] in ("68", "90", "11", "13", "51")):
                    code = "sh" + s
                else:
                    code = "sz" + s
            df = ak.stock_zh_a_daily(symbol=code, adjust="qfq")
            if df is None or df.empty:
                return json.dumps({"ok": False, "error": "未获取到数据，请检查代码是否正确"}, ensure_ascii=False)

            df = df.sort_values("date").reset_index(drop=True)

            if start_date:
                sd = start_date.replace("-", "")
                df = df[df["date"].astype(str).str.replace("-", "") >= sd]
            if end_date:
                ed = end_date.replace("-", "")
                df = df[df["date"].astype(str).str.replace("-", "") <= ed]

            data = _df_to_records(df, limit)
            return json.dumps({
                "ok": True,
                "symbol": symbol,
                "source": "sina",
                "count": len(data),
                "start": data[0]["date"] if data else None,
                "end": data[-1]["date"] if data else None,
                "bars": data,
            }, ensure_ascii=False)
        except Exception as e:
            return json.dumps({"ok": False, "error": f"{type(e).__name__}: {str(e)[:200]}"}, ensure_ascii=False)

    @mcp.tool(description="获取A股指数日线历史行情数据，数据来自新浪财经")
    def stock_zh_index_daily(
        symbol: str,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        limit: int = 500,
    ) -> str:
        """获取A股指数日线历史行情。

        Args:
            symbol: 指数代码，如 sh000001、sh000102、sz399001
            start_date: 起始日期，格式 YYYY-MM-DD 或 YYYYMMDD，可选
            end_date: 结束日期，格式 YYYY-MM-DD 或 YYYYMMDD，可选，默认今天
            limit: 返回数据条数限制（取最近N条），默认 500

        Returns:
            JSON 格式的K线数据，包含 date/open/high/low/close/volume
        """
        try:
            df = ak.stock_zh_index_daily(symbol=symbol)
            if df is None or df.empty:
                return json.dumps({"ok": False, "error": "未获取到数据，请检查代码是否正确"}, ensure_ascii=False)

            # 兼容不同 akshare 版本的列名
            date_col = "date" if "date" in df.columns else df.columns[0]
            df = df.sort_values(date_col).reset_index(drop=True)

            if start_date:
                sd = start_date.replace("-", "")
                df = df[df[date_col].astype(str).str.replace("-", "") >= sd]
            if end_date:
                ed = end_date.replace("-", "")
                df = df[df[date_col].astype(str).str.replace("-", "") <= ed]

            data = _df_to_records(df, limit)
            return json.dumps({
                "ok": True,
                "symbol": symbol,
                "source": "sina",
                "count": len(data),
                "start": data[0]["date"] if data else None,
                "end": data[-1]["date"] if data else None,
                "bars": data,
            }, ensure_ascii=False)
        except Exception as e:
            return json.dumps({"ok": False, "error": f"{type(e).__name__}: {str(e)[:200]}"}, ensure_ascii=False)

    @mcp.tool(description="获取A股指数实时行情列表，支持多源 fallback（新浪/东方财富）")
    def stock_zh_index_spot() -> str:
        """获取A股指数实时行情。

        Returns:
            JSON 格式的指数实时行情列表
        """
        try:
            try:
                df = ak.stock_zh_index_spot_em()
                data = _df_to_records(df)
                if data:
                    return json.dumps({
                        "ok": True,
                        "source": "eastmoney",
                        "count": len(data),
                        "data": data[:100],
                    }, ensure_ascii=False)
            except Exception:
                pass

            try:
                df = ak.stock_zh_index_spot_sina()
                data = _df_to_records(df)
                if data:
                    return json.dumps({
                        "ok": True,
                        "source": "sina",
                        "count": len(data),
                        "data": data[:100],
                    }, ensure_ascii=False)
            except Exception:
                pass

            index_codes = [
                "sh000001", "sh000002", "sh000003", "sh000300", "sh000905",
                "sz399001", "sz399006", "sz399005", "sh000688", "sh000016",
            ]
            data = _get_sina_spot(index_codes)
            if data:
                return json.dumps({
                    "ok": True,
                    "source": "sina",
                    "count": len(data),
                    "data": data,
                }, ensure_ascii=False)

            return json.dumps({"ok": False, "error": "所有数据源均失败"}, ensure_ascii=False)
        except Exception as e:
            return json.dumps({"ok": False, "error": f"{type(e).__name__}: {str(e)[:200]}"}, ensure_ascii=False)

    @mcp.tool(description="获取A股个股实时行情，支持单只或多只股票，多源 fallback")
    def stock_zh_a_spot(symbols: Optional[str] = None) -> str:
        """获取A股实时行情。

        Args:
            symbols: 股票代码，多个用逗号分隔，如 sh600519,sz000001,600519

        Returns:
            JSON 格式的实时行情数据
        """
        try:
            if not symbols:
                try:
                    df = ak.stock_zh_a_spot_em()
                    data = _df_to_records(df)
                    if data:
                        return json.dumps({"ok": True, "source": "eastmoney", "count": len(data), "data": data[:200]}, ensure_ascii=False)
                except Exception:
                    pass
                try:
                    df = ak.stock_zh_a_spot()
                    data = _df_to_records(df)
                    if data:
                        return json.dumps({"ok": True, "source": "sina", "count": len(data), "data": data[:200]}, ensure_ascii=False)
                except Exception:
                    pass
                return json.dumps({"ok": False, "error": "获取全部A股行情失败，请指定具体股票代码"}, ensure_ascii=False)

            sym_list = [s.strip() for s in symbols.split(",") if s.strip()]
            if not sym_list:
                return json.dumps({"ok": False, "error": "请提供股票代码"}, ensure_ascii=False)

            try:
                df = ak.stock_zh_a_spot_em()
                results = []
                for sym in sym_list:
                    code = sym.replace("sh", "").replace("sz", "").replace(".SH", "").replace(".SZ", "")
                    match = df[df["代码"].astype(str).str.contains(code, case=False)]
                    results.extend(_df_to_records(match))
                if results:
                    return json.dumps({"ok": True, "source": "eastmoney", "count": len(results), "data": results}, ensure_ascii=False)
            except Exception:
                pass

            data = _get_sina_spot(sym_list)
            if data:
                return json.dumps({"ok": True, "source": "sina", "count": len(data), "data": data}, ensure_ascii=False)

            return json.dumps({"ok": False, "error": "未获取到数据，请检查股票代码是否正确"}, ensure_ascii=False)
        except Exception as e:
            return json.dumps({"ok": False, "error": f"{type(e).__name__}: {str(e)[:200]}"}, ensure_ascii=False)

    return ["stock_zh_a_daily", "stock_zh_index_daily", "stock_zh_index_spot", "stock_zh_a_spot"]
