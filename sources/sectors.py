"""板块历史数据源：同花顺行业/概念板块的历史行情。

支持：
  - sector_industry_list: 行业板块列表
  - sector_concept_list: 概念板块列表
  - sector_industry_daily: 行业板块历史日线
  - sector_concept_daily: 概念板块历史日线
  - sector_daily_all: 按日期获取全部行业板块涨跌幅（复盘用）
"""
from __future__ import annotations
import json
from typing import Optional

import akshare as ak

from core.helpers import _df_to_records


def _calc_pct_change(df, date_col: str, close_col: str) -> list[dict]:
    """计算每日涨跌幅（和前一日收盘比较）。"""
    data = _df_to_records(df)
    for i in range(len(data)):
        if i == 0:
            data[i]["涨跌幅"] = None
        else:
            prev_close = data[i-1].get(close_col, 0)
            cur_close = data[i].get(close_col, 0)
            if prev_close:
                data[i]["涨跌幅"] = round((cur_close - prev_close) / prev_close * 100, 2)
            else:
                data[i]["涨跌幅"] = None
    return data


def register(mcp) -> list[str]:
    """注册板块历史工具，返回工具名列表。"""

    @mcp.tool(description="获取同花顺行业板块列表（90个）")
    def sector_industry_list() -> str:
        """获取全部行业板块名称和代码。

        Returns:
            JSON 格式的板块列表
        """
        try:
            df = ak.stock_board_industry_name_ths()
            data = _df_to_records(df)
            return json.dumps({
                "ok": True, "source": "ths", "count": len(data), "sectors": data,
            }, ensure_ascii=False)
        except Exception as e:
            return json.dumps({"ok": False, "error": f"{type(e).__name__}: {str(e)[:200]}"}, ensure_ascii=False)

    @mcp.tool(description="获取同花顺概念板块列表（300+个）")
    def sector_concept_list() -> str:
        """获取全部概念板块名称和代码。

        Returns:
            JSON 格式的板块列表
        """
        try:
            df = ak.stock_board_concept_name_ths()
            data = _df_to_records(df)
            return json.dumps({
                "ok": True, "source": "ths", "count": len(data), "sectors": data,
            }, ensure_ascii=False)
        except Exception as e:
            return json.dumps({"ok": False, "error": f"{type(e).__name__}: {str(e)[:200]}"}, ensure_ascii=False)

    @mcp.tool(description="获取行业板块历史日线行情（同花顺）")
    def sector_industry_daily(
        symbol: str,
        start_date: str = "20200101",
        end_date: str = "20991231",
    ) -> str:
        """获取单个行业板块的历史日线数据。

        Args:
            symbol: 板块名称，如 "半导体"、"白酒"、"新能源汽车"
            start_date: 开始日期 YYYYMMDD
            end_date: 结束日期 YYYYMMDD

        Returns:
            JSON 格式的日线数据（含涨跌幅）
        """
        try:
            df = ak.stock_board_industry_index_ths(
                symbol=symbol, start_date=start_date, end_date=end_date,
            )
            data = _calc_pct_change(df, "日期", "收盘价")
            return json.dumps({
                "ok": True, "source": "ths:industry", "symbol": symbol,
                "count": len(data), "bars": data,
            }, ensure_ascii=False)
        except Exception as e:
            return json.dumps({"ok": False, "error": f"{type(e).__name__}: {str(e)[:200]}"}, ensure_ascii=False)

    @mcp.tool(description="获取概念板块历史日线行情（同花顺）")
    def sector_concept_daily(
        symbol: str,
        start_date: str = "20200101",
        end_date: str = "20991231",
    ) -> str:
        """获取单个概念板块的历史日线数据。

        Args:
            symbol: 概念名称，如 "人工智能"、"华为概念"、"芯片"
            start_date: 开始日期 YYYYMMDD
            end_date: 结束日期 YYYYMMDD

        Returns:
            JSON 格式的日线数据（含涨跌幅）
        """
        try:
            df = ak.stock_board_concept_index_ths(
                symbol=symbol, start_date=start_date, end_date=end_date,
            )
            data = _calc_pct_change(df, "日期", "收盘价")
            return json.dumps({
                "ok": True, "source": "ths:concept", "symbol": symbol,
                "count": len(data), "bars": data,
            }, ensure_ascii=False)
        except Exception as e:
            return json.dumps({"ok": False, "error": f"{type(e).__name__}: {str(e)[:200]}"}, ensure_ascii=False)

    @mcp.tool(description="按日期获取全部行业板块涨跌幅排行（复盘专用）")
    def sector_daily_rank(
        date: str = "",
        top_n: int = 20,
    ) -> str:
        """获取指定日期所有行业板块的涨跌幅排行。

        复盘神器：直接看某一天哪些板块涨、哪些跌。
        注意：需要逐个板块查询，约 90 个，需要 5-10 秒。

        Args:
            date: 日期 YYYYMMDD，默认最新交易日
            top_n: 返回前 N 个和后 N 个

        Returns:
            JSON 格式的涨跌幅排行
        """
        try:
            import datetime
            if not date:
                date = datetime.date.today().strftime("%Y%m%d")

            # 获取板块列表
            df_list = ak.stock_board_industry_name_ths()
            sectors = _df_to_records(df_list)

            # 计算查询日期范围（前后各1天，确保能找到前一日收盘价）
            dt = datetime.datetime.strptime(date, "%Y%m%d")
            start_d = (dt - datetime.timedelta(days=5)).strftime("%Y%m%d")
            end_d = date

            results = []
            for sec in sectors:
                name = sec.get("name", "")
                try:
                    df = ak.stock_board_industry_index_ths(
                        symbol=name, start_date=start_d, end_date=end_d,
                    )
                    if df is None or len(df) < 2:
                        continue
                    data = _df_to_records(df)
                    # 找到目标日期的数据
                    target = None
                    prev_close = None
                    for i, row in enumerate(data):
                        row_date = str(row.get("日期", "")).replace("-", "")
                        if row_date == date:
                            target = row
                            if i > 0:
                                prev_close = data[i-1].get("收盘价", 0)
                            break
                    if target is None:
                        # 取最后一条
                        target = data[-1]
                        if len(data) >= 2:
                            prev_close = data[-2].get("收盘价", 0)

                    close = target.get("收盘价", 0)
                    pct = round((close - prev_close) / prev_close * 100, 2) if prev_close else 0
                    amt = target.get("成交额", 0)

                    results.append({
                        "板块名称": name,
                        "板块代码": sec.get("code", ""),
                        "收盘价": close,
                        "涨跌幅": pct,
                        "成交额": amt,
                    })
                except Exception:
                    continue

            # 按涨跌幅排序
            results.sort(key=lambda x: x["涨跌幅"], reverse=True)

            return json.dumps({
                "ok": True, "source": "ths:industry", "date": date,
                "total": len(results),
                "top_gainers": results[:top_n],
                "top_losers": results[-top_n:][::-1],
            }, ensure_ascii=False)
        except Exception as e:
            return json.dumps({"ok": False, "error": f"{type(e).__name__}: {str(e)[:200]}"}, ensure_ascii=False)

    return [
        "sector_industry_list",
        "sector_concept_list",
        "sector_industry_daily",
        "sector_concept_daily",
        "sector_daily_rank",
    ]
