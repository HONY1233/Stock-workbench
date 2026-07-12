"""巨潮信息网数据源：公告、公司资料、财务摘要、分红配送。"""
from __future__ import annotations
import json
from typing import Optional

import akshare as ak

from core.helpers import _df_to_records


def register(mcp) -> list[str]:
    """注册巨潮信息工具，返回工具名列表。"""

    @mcp.tool(description="获取上市公司公告（巨潮信息网），支持按类型、日期、关键词筛选")
    def stock_notice_cninfo(
        symbol: str,
        category: Optional[str] = None,
        keyword: Optional[str] = None,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        limit: int = 20,
    ) -> str:
        """获取上市公司公告（巨潮信息网）。

        Args:
            symbol: 股票代码，如 600519、000001
            category: 公告类型，可选：年报、半年报、一季报、三季报、业绩预告、权益分派、
                      董事会、监事会、股东大会、日常经营、公司治理、中介报告、
                      首发、增发、股权激励、配股、解禁、公司债、可转债、其他融资、
                      股权变动、补充更正、澄清致歉、风险提示、特别处理和退市
            keyword: 关键词过滤，可选
            start_date: 开始日期，格式 YYYY-MM-DD 或 YYYYMMDD，可选
            end_date: 结束日期，格式 YYYY-MM-DD 或 YYYYMMDD，可选
            limit: 返回条数，默认 20 条

        Returns:
            JSON 格式的公告列表
        """
        try:
            code = symbol.replace("sh", "").replace("sz", "").replace(".SH", "").replace(".SZ", "")

            if not start_date:
                start_date = "20200101"
            else:
                start_date = start_date.replace("-", "")
            if not end_date:
                end_date = "20991231"
            else:
                end_date = end_date.replace("-", "")

            params = {
                "symbol": code,
                "market": "沪深京",
                "start_date": start_date,
                "end_date": end_date,
            }
            if category:
                params["category"] = category
            if keyword:
                params["keyword"] = keyword

            df = ak.stock_zh_a_disclosure_report_cninfo(**params)
            data = _df_to_records(df, limit)
            return json.dumps({
                "ok": True,
                "source": "cninfo",
                "symbol": symbol,
                "count": len(data),
                "data": data,
            }, ensure_ascii=False)
        except Exception as e:
            return json.dumps({"ok": False, "error": f"{type(e).__name__}: {str(e)[:200]}"}, ensure_ascii=False)

    @mcp.tool(description="获取上市公司基本资料（巨潮信息网）")
    def stock_profile_cninfo(symbol: str) -> str:
        """获取上市公司基本资料。

        Args:
            symbol: 股票代码，如 600519、000001

        Returns:
            JSON 格式的公司基本资料
        """
        try:
            code = symbol.replace("sh", "").replace("sz", "").replace(".SH", "").replace(".SZ", "")
            df = ak.stock_profile_cninfo(symbol=code)
            data = _df_to_records(df)
            return json.dumps({
                "ok": True,
                "source": "cninfo",
                "symbol": symbol,
                "count": len(data),
                "data": data,
            }, ensure_ascii=False)
        except Exception as e:
            return json.dumps({"ok": False, "error": f"{type(e).__name__}: {str(e)[:200]}"}, ensure_ascii=False)

    @mcp.tool(description="获取上市公司财务摘要（巨潮信息网）")
    def stock_financial_abstract_cninfo(symbol: str, limit: int = 10) -> str:
        """获取上市公司财务摘要。

        Args:
            symbol: 股票代码，如 600519、000001
            limit: 返回报告期数，默认 10 期

        Returns:
            JSON 格式的财务摘要数据
        """
        try:
            code = symbol.replace("sh", "").replace("sz", "").replace(".SH", "").replace(".SZ", "")
            df = ak.stock_financial_abstract(symbol=code)
            data = _df_to_records(df, limit)
            return json.dumps({
                "ok": True,
                "source": "cninfo",
                "symbol": symbol,
                "count": len(data),
                "data": data,
            }, ensure_ascii=False)
        except Exception as e:
            return json.dumps({"ok": False, "error": f"{type(e).__name__}: {str(e)[:200]}"}, ensure_ascii=False)

    @mcp.tool(description="获取上市公司分红配送信息（巨潮信息网）")
    def stock_dividend_cninfo(symbol: str, limit: int = 20) -> str:
        """获取上市公司分红配送信息。

        Args:
            symbol: 股票代码，如 600519、000001
            limit: 返回条数，默认 20 条

        Returns:
            JSON 格式的分红配送数据
        """
        try:
            code = symbol.replace("sh", "").replace("sz", "").replace(".SH", "").replace(".SZ", "")
            df = ak.stock_dividend_cninfo(symbol=code)
            data = _df_to_records(df, limit)
            return json.dumps({
                "ok": True,
                "source": "cninfo",
                "symbol": symbol,
                "count": len(data),
                "data": data,
            }, ensure_ascii=False)
        except Exception as e:
            return json.dumps({"ok": False, "error": f"{type(e).__name__}: {str(e)[:200]}"}, ensure_ascii=False)

    return ["stock_notice_cninfo", "stock_profile_cninfo",
            "stock_financial_abstract_cninfo", "stock_dividend_cninfo"]
