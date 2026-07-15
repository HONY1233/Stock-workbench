"""巨潮信息网数据源：公司资料、财务摘要、分红配送。"""
from __future__ import annotations
import json

from pydantic import BaseModel, Field, field_validator

import akshare as ak

from core.helpers import _df_to_records


class _StockProfileInput(BaseModel):
    symbol: str = Field(..., description="股票代码，如 600519、000001")

    @field_validator("symbol")
    @classmethod
    def _clean(cls, v: str) -> str:
        return v.strip().replace("sh", "").replace("sz", "").replace(".SH", "").replace(".SZ", "")


class _StockFinancialAbstractInput(BaseModel):
    symbol: str = Field(..., description="股票代码，如 600519、000001")
    limit: int = Field(10, ge=1, le=100, description="返回报告期数")

    @field_validator("symbol")
    @classmethod
    def _clean(cls, v: str) -> str:
        return v.strip().replace("sh", "").replace("sz", "").replace(".SH", "").replace(".SZ", "")


class _StockDividendInput(BaseModel):
    symbol: str = Field(..., description="股票代码，如 600519、000001")
    limit: int = Field(20, ge=1, le=500, description="返回条数")

    @field_validator("symbol")
    @classmethod
    def _clean(cls, v: str) -> str:
        return v.strip().replace("sh", "").replace("sz", "").replace(".SH", "").replace(".SZ", "")


_READ_ONLY = {"readOnlyHint": True}


def register(mcp) -> list[str]:
    """注册巨潮信息工具，返回工具名列表。"""

    @mcp.tool(description="获取上市公司基本资料（巨潮信息网）", annotations=_READ_ONLY)
    def stock_profile_cninfo(symbol: str) -> str:
        try:
            params = _StockProfileInput(symbol=symbol)
            df = ak.stock_profile_cninfo(symbol=params.symbol)
            data = _df_to_records(df)
            return json.dumps({"ok": True, "data": data, "count": len(data)}, ensure_ascii=False)
        except Exception as e:
            return json.dumps(
                {"ok": False, "data": [], "count": 0, "error": f"{type(e).__name__}: {str(e)[:200]}"},
                ensure_ascii=False,
            )

    @mcp.tool(description="获取上市公司财务摘要（巨潮信息网）", annotations=_READ_ONLY)
    def stock_financial_abstract_cninfo(symbol: str, limit: int = 10) -> str:
        try:
            params = _StockFinancialAbstractInput(symbol=symbol, limit=limit)
            df = ak.stock_financial_abstract(symbol=params.symbol)
            data = _df_to_records(df, params.limit)
            return json.dumps({"ok": True, "data": data, "count": len(data)}, ensure_ascii=False)
        except Exception as e:
            return json.dumps(
                {"ok": False, "data": [], "count": 0, "error": f"{type(e).__name__}: {str(e)[:200]}"},
                ensure_ascii=False,
            )

    @mcp.tool(description="获取上市公司分红配送信息（巨潮信息网）", annotations=_READ_ONLY)
    def stock_dividend_cninfo(symbol: str, limit: int = 20) -> str:
        try:
            params = _StockDividendInput(symbol=symbol, limit=limit)
            df = ak.stock_dividend_cninfo(symbol=params.symbol)
            data = _df_to_records(df, params.limit)
            return json.dumps({"ok": True, "data": data, "count": len(data)}, ensure_ascii=False)
        except Exception as e:
            return json.dumps(
                {"ok": False, "data": [], "count": 0, "error": f"{type(e).__name__}: {str(e)[:200]}"},
                ensure_ascii=False,
            )

    return [
        "stock_profile_cninfo",
        "stock_financial_abstract_cninfo",
        "stock_dividend_cninfo",
    ]
