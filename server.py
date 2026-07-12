#!/usr/bin/env python3
"""AKShare MCP Server - 基于 akshare 的金融数据 MCP 服务器。

提供A股、指数等金融数据查询工具，数据来自公开数据源（新浪财经等）。
仅供技术研究与学习使用，不构成投资建议。

架构（L0-L3 等级制度）：
  L0 核心层  — 本地可用，无网络依赖（翻译、接口列表）
  L1 稳定层  — akshare 稳定 API + 腾讯直连（不封 IP）
  L2 限流层  — 东财 datacenter/push2（需限流，可能被封）
  L3 受限层  — 国际源 Reuters/Bloomberg（需翻墙）
  兜底链路：L3 → L2 → L1 → L0
"""
from __future__ import annotations

import json
import sys
from typing import Optional

try:
    from fastmcp import FastMCP
except ImportError:
    print("错误: 未安装 fastmcp，请运行: pip install fastmcp", file=sys.stderr)
    sys.exit(1)

try:
    import akshare as ak
    import pandas as pd
    pd.set_option("string_storage", "python")
except ImportError:
    print("错误: 未安装 akshare，请运行: pip install akshare pandas", file=sys.stderr)
    sys.exit(1)

# 从 core/ 包导入解耦的模块
from core.helpers import _df_to_records, _safe_json, _json_ok, _json_fail
from core.translate import (
    _FINANCIAL_DICT_EN_ZH, _FINANCIAL_DICT_SORTED,
    _has_english, _translate_en_to_zh, _translate_records,
    translate_text_impl,
)
from core.tiers import Tier, TOOL_TIERS, tier_info, get_tier, with_fallback, run_with_fallback


mcp = FastMCP("akshare")


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


def _get_sina_spot(symbols: list[str]) -> list[dict]:
    """从新浪财经获取实时行情。"""
    try:
        from curl_cffi import requests
    except ImportError:
        import requests as requests

    code_list = []
    for sym in symbols:
        s = sym.lower().replace(".sh", "").replace(".sz", "")
        if s.startswith("sh") or s.startswith("sz"):
            code_list.append(s)
        elif len(s) == 6:
            if s[0] in "6" or s[:2] in ("68", "90", "51", "11", "13"):
                code_list.append("sh" + s)
            else:
                code_list.append("sz" + s)
        else:
            code_list.append(sym)

    url = "https://hq.sinajs.cn/list=" + ",".join(code_list)
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124 Safari/537.36",
        "Referer": "https://finance.sina.com.cn/",
    }

    try:
        r = requests.get(url, headers=headers, timeout=10)
    except Exception:
        return []

    results = []
    lines = r.text.strip().split("\n")
    for i, line in enumerate(lines):
        if "=" not in line:
            continue
        code_part, data_part = line.split("=", 1)
        code = code_part.replace("var hq_str_", "").strip()
        data_str = data_part.strip().strip('"')
        if not data_str:
            continue
        fields = data_str.split(",")
        if len(fields) < 32:
            continue

        name = fields[0]
        open_price = float(fields[1]) if fields[1] else 0
        prev_close = float(fields[2]) if fields[2] else 0
        price = float(fields[3]) if fields[3] else 0
        high = float(fields[4]) if fields[4] else 0
        low = float(fields[5]) if fields[5] else 0
        volume = float(fields[8]) if fields[8] else 0
        amount = float(fields[9]) if fields[9] else 0

        change = price - prev_close if prev_close else 0
        change_pct = (change / prev_close * 100) if prev_close else 0

        results.append({
            "代码": code,
            "名称": name,
            "最新价": round(price, 2),
            "涨跌额": round(change, 2),
            "涨跌幅": round(change_pct, 2),
            "今开": round(open_price, 2),
            "最高": round(high, 2),
            "最低": round(low, 2),
            "昨收": round(prev_close, 2),
            "成交量": volume,
            "成交额": amount,
            "source": "sina",
        })

    return results


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


@mcp.tool(description="获取财联社电报（7x24小时财经快讯），支持按时间范围、关键词、级别及标红过滤")
def cls_telegraph(
    limit: int = 20,
    keyword: Optional[str] = None,
    level: Optional[str] = None,
    red_only: bool = False,
    hours: Optional[float] = None,
) -> str:
    """获取财联社电报快讯。

    Args:
        limit: 返回条数，默认 20 条
        keyword: 关键词过滤，可选
        level: 级别过滤，如 'A', 'B', 'C'，可选
        red_only: 是否只获取标红新闻（level 为 A 或 B 的重要新闻），默认 False
        hours: 只返回最近 N 小时内的新闻，可选，如 1 表示最近1小时

    Returns:
        JSON 格式的财联社电报列表
    """
    try:
        import time
        try:
            from curl_cffi import requests
        except ImportError:
            return json.dumps({
                "ok": False,
                "error": "需要安装 curl_cffi: pip install curl_cffi"
            }, ensure_ascii=False)

        base_url = "https://www.cls.cn"
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124 Safari/537.36",
            "Referer": "https://www.cls.cn/telegraph",
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        }

        all_items = []
        last_time = None
        # 标红新闻较少，需要翻更多页才能凑够 limit 条
        max_pages = 10 if red_only else 5

        for page in range(max_pages):
            params = {
                "app": "CailianpressWeb",
                "os": "web",
                "sv": "8.7.9",
                "name": "telegraphList",
            }
            if last_time:
                params["lastTime"] = str(last_time)

            r = requests.get(
                f"{base_url}/api/cache",
                params=params,
                headers=headers,
                impersonate="chrome120",
                timeout=15,
            )
            result = r.json()

            if result.get("errno") != 0:
                break

            roll_data = result.get("data", {}).get("roll_data", [])
            if not roll_data:
                break

            for item in roll_data:
                ctime = item.get("ctime", 0)
                all_items.append({
                    "id": item.get("id"),
                    "title": item.get("title", ""),
                    "brief": item.get("brief", ""),
                    "content": item.get("content", ""),
                    "ctime": ctime,
                    "datetime": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(ctime)) if ctime else "",
                    "level": item.get("level", ""),
                    "is_red": item.get("level", "") in ("A", "B"),
                    "reading_num": item.get("reading_num", 0),
                    "comment_num": item.get("comment_num", 0),
                    "share_num": item.get("share_num", 0),
                    "subjects": item.get("subjects", []),
                    "stock_list": item.get("stock_list", []),
                })

            if len(all_items) >= limit * 3:
                break

            if roll_data:
                last_time = roll_data[-1].get("ctime")
            else:
                break

            time.sleep(0.3)

        # 标红过滤：只保留 level 为 A 或 B 的新闻
        if red_only:
            all_items = [item for item in all_items if item["is_red"]]

        # 时间范围过滤：只保留最近 N 小时内的新闻
        if hours:
            now = time.time()
            cutoff = now - hours * 3600
            all_items = [item for item in all_items if item.get("ctime", 0) >= cutoff]

        if keyword:
            kw = keyword.lower()
            all_items = [
                item for item in all_items
                if kw in item["title"].lower()
                or kw in item["brief"].lower()
                or kw in item["content"].lower()
            ]

        if level:
            all_items = [item for item in all_items if item["level"] == level.upper()]

        all_items = all_items[:limit]

        return json.dumps({
            "ok": True,
            "source": "cls",
            "count": len(all_items),
            "red_only": red_only,
            "data": all_items,
        }, ensure_ascii=False)
    except Exception as e:
        return json.dumps({"ok": False, "error": f"{type(e).__name__}: {str(e)[:200]}"}, ensure_ascii=False)


@mcp.tool(description="获取新闻联播文字稿")
def news_cctv(date: Optional[str] = None, limit: int = 20) -> str:
    """获取新闻联播文字稿。

    Args:
        date: 日期，格式 YYYYMMDD 或 YYYY-MM-DD，可选，默认今天
        limit: 返回条数，默认 20 条

    Returns:
        JSON 格式的新闻联播内容
    """
    try:
        if date:
            date = date.replace("-", "")
            df = ak.news_cctv(date=date)
        else:
            df = ak.news_cctv()
        data = _df_to_records(df, limit)
        return json.dumps({
            "ok": True,
            "source": "cctv",
            "count": len(data),
            "data": data,
        }, ensure_ascii=False)
    except Exception as e:
        return json.dumps({"ok": False, "error": f"{type(e).__name__}: {str(e)[:200]}"}, ensure_ascii=False)


@mcp.tool(description="获取财经日历（全球财经事件日历）")
def news_economic_calendar(limit: int = 50) -> str:
    """获取全球财经事件日历。

    Args:
        limit: 返回条数，默认 50 条

    Returns:
        JSON 格式的财经日历数据
    """
    try:
        df = ak.news_economic_baidu()
        data = _df_to_records(df, limit)
        return json.dumps({
            "ok": True,
            "source": "baidu",
            "count": len(data),
            "data": data,
        }, ensure_ascii=False)
    except Exception as e:
        return json.dumps({"ok": False, "error": f"{type(e).__name__}: {str(e)[:200]}"}, ensure_ascii=False)


@mcp.tool(description="获取个股相关新闻")
def stock_news(symbol: str, limit: int = 20) -> str:
    """获取个股相关新闻。

    Args:
        symbol: 股票代码，如 600519
        limit: 返回条数，默认 20 条

    Returns:
        JSON 格式的新闻列表
    """
    try:
        code = symbol.replace("sh", "").replace("sz", "").replace(".SH", "").replace(".SZ", "")
        df = ak.stock_news_em(symbol=code)
        data = _df_to_records(df, limit)
        return json.dumps({
            "ok": True,
            "source": "eastmoney",
            "symbol": symbol,
            "count": len(data),
            "data": data,
        }, ensure_ascii=False)
    except Exception as e:
        return json.dumps({"ok": False, "error": f"{type(e).__name__}: {str(e)[:200]}"}, ensure_ascii=False)


# ==================== 外围新闻（含英文翻译） ====================


@mcp.tool(description="获取全球财经新闻（东方财富），自动翻译英文内容为中文")
def global_news_em(limit: int = 50, translate: bool = True) -> str:
    """获取全球财经新闻（东方财富数据源）。

    Args:
        limit: 返回条数，默认 50 条
        translate: 是否将英文标题/摘要翻译为中文（基于金融术语词典），默认 True

    Returns:
        JSON 格式的全球新闻列表，含 标题/摘要/发布时间/链接
    """
    try:
        df = ak.stock_info_global_em()
        data = _df_to_records(df, limit)
        data = _translate_records(data, fields=["标题", "摘要"], translate=translate)
        return json.dumps({
            "ok": True,
            "source": "eastmoney",
            "count": len(data),
            "translated": translate,
            "data": data,
        }, ensure_ascii=False)
    except Exception as e:
        return json.dumps({"ok": False, "error": f"{type(e).__name__}: {str(e)[:200]}"}, ensure_ascii=False)


@mcp.tool(description="获取全球财经快讯（新浪财经），自动翻译英文内容为中文")
def global_news_sina(limit: int = 20, translate: bool = True) -> str:
    """获取全球财经快讯（新浪财经数据源）。

    Args:
        limit: 返回条数，默认 20 条
        translate: 是否将英文内容翻译为中文，默认 True

    Returns:
        JSON 格式的全球快讯列表，含 时间/内容
    """
    try:
        df = ak.stock_info_global_sina()
        data = _df_to_records(df, limit)
        data = _translate_records(data, fields=["内容"], translate=translate)
        return json.dumps({
            "ok": True,
            "source": "sina",
            "count": len(data),
            "translated": translate,
            "data": data,
        }, ensure_ascii=False)
    except Exception as e:
        return json.dumps({"ok": False, "error": f"{type(e).__name__}: {str(e)[:200]}"}, ensure_ascii=False)


@mcp.tool(description="获取全球财经新闻（同花顺），自动翻译英文内容为中文")
def global_news_ths(limit: int = 20, translate: bool = True) -> str:
    """获取全球财经新闻（同花顺数据源）。

    Args:
        limit: 返回条数，默认 20 条
        translate: 是否将英文标题/内容翻译为中文，默认 True

    Returns:
        JSON 格式的新闻列表，含 标题/内容/发布时间/链接
    """
    try:
        df = ak.stock_info_global_ths()
        data = _df_to_records(df, limit)
        data = _translate_records(data, fields=["标题", "内容"], translate=translate)
        return json.dumps({
            "ok": True,
            "source": "ths",
            "count": len(data),
            "translated": translate,
            "data": data,
        }, ensure_ascii=False)
    except Exception as e:
        return json.dumps({"ok": False, "error": f"{type(e).__name__}: {str(e)[:200]}"}, ensure_ascii=False)


@mcp.tool(description="获取华尔街见闻财经日历（全球宏观事件），自动翻译英文事件名为中文")
def wallstreet_news(limit: int = 30, translate: bool = True) -> str:
    """获取华尔街见闻财经日历数据。

    包含全球宏观经济数据公布：时间/地区/事件/重要性/今值/预期/前值/链接。
    事件名称可能含英文，开启 translate 会自动翻译为中文。

    Args:
        limit: 返回条数，默认 30 条
        translate: 是否将英文事件名翻译为中文，默认 True

    Returns:
        JSON 格式的财经日历列表
    """
    try:
        df = ak.macro_info_ws()
        data = _df_to_records(df, limit)
        data = _translate_records(data, fields=["事件", "地区"], translate=translate)
        return json.dumps({
            "ok": True,
            "source": "wallstreet",
            "count": len(data),
            "translated": translate,
            "data": data,
        }, ensure_ascii=False)
    except Exception as e:
        return json.dumps({"ok": False, "error": f"{type(e).__name__}: {str(e)[:200]}"}, ensure_ascii=False)


@mcp.tool(description="获取上海期货交易所新闻（期货市场要闻），自动翻译英文内容为中文")
def futures_news_shmet(limit: int = 50, translate: bool = True) -> str:
    """获取上海期货交易所新闻。

    Args:
        limit: 返回条数，默认 50 条
        translate: 是否将英文内容翻译为中文，默认 True

    Returns:
        JSON 格式的上期所新闻列表，含 发布时间/内容
    """
    try:
        df = ak.futures_news_shmet()
        data = _df_to_records(df, limit)
        data = _translate_records(data, fields=["内容"], translate=translate)
        return json.dumps({
            "ok": True,
            "source": "shmet",
            "count": len(data),
            "translated": translate,
            "data": data,
        }, ensure_ascii=False)
    except Exception as e:
        return json.dumps({"ok": False, "error": f"{type(e).__name__}: {str(e)[:200]}"}, ensure_ascii=False)


@mcp.tool(description="获取美股个股新闻（东方财富），自动翻译英文标题/内容为中文")
def stock_us_news(symbol: str, limit: int = 30, translate: bool = True) -> str:
    """获取美股个股新闻。

    Args:
        symbol: 美股代码，如 AAPL（苹果）、TSLA（特斯拉）、MSFT（微软）
        limit: 返回条数，默认 30 条
        translate: 是否将英文标题/内容翻译为中文，默认 True

    Returns:
        JSON 格式的美股新闻列表
    """
    try:
        df = ak.stock_info_global_em()
        data = _df_to_records(df, limit)
        # 客户端过滤：标题/摘要中包含 symbol
        sym_upper = symbol.upper()
        filtered = []
        for item in data:
            title = str(item.get("标题", "")).upper()
            summary = str(item.get("摘要", "")).upper()
            if sym_upper in title or sym_upper in summary:
                filtered.append(item)
            if len(filtered) >= limit:
                break
        filtered = _translate_records(filtered, fields=["标题", "摘要"], translate=translate)
        return json.dumps({
            "ok": True,
            "source": "eastmoney",
            "symbol": symbol,
            "count": len(filtered),
            "translated": translate,
            "data": filtered,
        }, ensure_ascii=False)
    except Exception as e:
        return json.dumps({"ok": False, "error": f"{type(e).__name__}: {str(e)[:200]}"}, ensure_ascii=False)


@mcp.tool(description="翻译英文文本为中文（基于金融术语词典，离线可用）")
def translate_text(text: str) -> str:
    """将英文金融文本翻译为中文。

    基于内置的金融术语词典（约 250 个常用词条），自动检测英文并翻译。
    适合翻译财经新闻、宏观数据事件名、市场评论等。
    未匹配的英文原样保留。

    Args:
        text: 待翻译的英文文本

    Returns:
        JSON 格式的翻译结果
    """
    try:
        if not text:
            return json.dumps({"ok": False, "error": "text 不能为空"}, ensure_ascii=False)
        has_en = _has_english(text)
        translated = _translate_en_to_zh(text)
        return json.dumps({
            "ok": True,
            "original": text,
            "translated": translated,
            "had_english": has_en,
            "dict_size": len(_FINANCIAL_DICT_EN_ZH),
        }, ensure_ascii=False)
    except Exception as e:
        return json.dumps({"ok": False, "error": f"{type(e).__name__}: {str(e)[:200]}"}, ensure_ascii=False)


# ==================== Reuters / Bloomberg 新闻源 ====================
# 通过聚合数据源搜索 Reuters/Bloomberg 相关新闻
# 主渠道：直接抓取 RSS（网络允许时）
# 备用渠道：在现有全球新闻源中搜索关键词 "Reuters"/"路透"/"Bloomberg"/"彭博"


@mcp.tool(description="获取路透社(Reuters)相关财经新闻，自动翻译英文内容为中文")
def reuters_news(limit: int = 30, translate: bool = True) -> str:
    """获取路透社相关财经新闻。

    通过两种方式获取：
    1. 直接抓取 Reuters RSS 订阅源（网络允许时）
    2. 在聚合新闻源中搜索关键词 "Reuters" 或 "路透"

    Args:
        limit: 返回条数，默认 30 条
        translate: 是否将英文内容翻译为中文，默认 True

    Returns:
        JSON 格式的新闻列表
    """
    try:
        data = []
        source = "fallback"

        # 方式1：尝试直接抓取 Reuters RSS
        try:
            import feedparser
            import requests
            rss_urls = [
                "https://feeds.reuters.com/Reuters/topNews",
                "https://feeds.reuters.com/Reuters/businessNews",
                "https://feeds.reuters.com/Reuters/worldNews",
            ]
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            }
            for url in rss_urls:
                try:
                    r = requests.get(url, headers=headers, timeout=10)
                    if r.status_code == 200 and len(r.text) > 1000:
                        feed = feedparser.parse(r.text)
                        for entry in feed.entries[:limit]:
                            item = {
                                "标题": entry.get("title", ""),
                                "摘要": entry.get("summary", "")[:200] if entry.get("summary") else "",
                                "发布时间": entry.get("published", ""),
                                "链接": entry.get("link", ""),
                                "来源": "Reuters",
                            }
                            data.append(item)
                        if data:
                            source = "reuters_rss"
                            break
                except Exception:
                    continue
        except ImportError:
            pass

        # 方式2：在聚合新闻源中搜索 Reuters/路透
        if not data:
            keywords = ["Reuters", "路透"]
            sources = [
                ("东方财富", ak.stock_info_global_em, ["标题", "摘要"]),
                ("新浪", ak.stock_info_global_sina, ["内容"]),
                ("同花顺", ak.stock_info_global_ths, ["标题", "内容"]),
            ]
            for src_name, fn, fields in sources:
                try:
                    df = fn()
                    for _, row in df.iterrows():
                        matched = False
                        for field in fields:
                            val = str(row.get(field, ""))
                            if any(kw.lower() in val.lower() for kw in keywords):
                                matched = True
                                break
                        if matched:
                            item = {
                                "标题": str(row.get("标题", row.get("内容", "")))[:100],
                                "摘要": str(row.get("摘要", row.get("内容", "")))[:200],
                                "发布时间": str(row.get("发布时间", row.get("时间", ""))),
                                "链接": str(row.get("链接", "")),
                                "来源": src_name + "-Reuters",
                            }
                            data.append(item)
                        if len(data) >= limit:
                            break
                    if len(data) >= limit:
                        break
                except Exception:
                    continue

        if not data:
            # Fallback：返回全球新闻概览
            try:
                df = ak.stock_info_global_em()
                for _, row in df.head(limit).iterrows():
                    data.append({
                        "标题": str(row.get("标题", ""))[:100],
                        "摘要": str(row.get("摘要", ""))[:200],
                        "发布时间": str(row.get("发布时间", "")),
                        "链接": str(row.get("链接", "")),
                        "来源": "东方财富-全球新闻",
                    })
                source = "fallback_global"
            except Exception:
                return json.dumps({
                    "ok": False,
                    "error": "未获取到路透社相关新闻，可能是网络限制或暂无相关内容",
                }, ensure_ascii=False)

        data = _translate_records(data, fields=["标题", "摘要"], translate=translate)
        if len(data) > limit:
            data = data[:limit]

        return json.dumps({
            "ok": True,
            "source": source,
            "count": len(data),
            "translated": translate,
            "data": data,
        }, ensure_ascii=False)
    except Exception as e:
        return json.dumps({"ok": False, "error": f"{type(e).__name__}: {str(e)[:200]}"}, ensure_ascii=False)


@mcp.tool(description="获取彭博社(Bloomberg)相关财经新闻，自动翻译英文内容为中文")
def bloomberg_news(limit: int = 30, translate: bool = True) -> str:
    """获取彭博社相关财经新闻。

    通过两种方式获取：
    1. 直接抓取 Bloomberg RSS 订阅源（网络允许时）
    2. 在聚合新闻源中搜索关键词 "Bloomberg" 或 "彭博"

    Args:
        limit: 返回条数，默认 30 条
        translate: 是否将英文内容翻译为中文，默认 True

    Returns:
        JSON 格式的新闻列表
    """
    try:
        data = []
        source = "fallback"

        # 方式1：尝试直接抓取 Bloomberg RSS
        try:
            import feedparser
            import requests
            rss_urls = [
                "https://www.bloomberg.com/news/rss",
                "https://www.bloomberg.com/politics/rss",
                "https://www.bloomberg.com/markets/rss",
            ]
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            }
            for url in rss_urls:
                try:
                    r = requests.get(url, headers=headers, timeout=10)
                    if r.status_code == 200 and len(r.text) > 1000:
                        feed = feedparser.parse(r.text)
                        for entry in feed.entries[:limit]:
                            item = {
                                "标题": entry.get("title", ""),
                                "摘要": entry.get("summary", "")[:200] if entry.get("summary") else "",
                                "发布时间": entry.get("published", ""),
                                "链接": entry.get("link", ""),
                                "来源": "Bloomberg",
                            }
                            data.append(item)
                        if data:
                            source = "bloomberg_rss"
                            break
                except Exception:
                    continue
        except ImportError:
            pass

        # 方式2：在聚合新闻源中搜索 Bloomberg/彭博
        if not data:
            keywords = ["Bloomberg", "彭博"]
            sources = [
                ("东方财富", ak.stock_info_global_em, ["标题", "摘要"]),
                ("新浪", ak.stock_info_global_sina, ["内容"]),
                ("同花顺", ak.stock_info_global_ths, ["标题", "内容"]),
            ]
            for src_name, fn, fields in sources:
                try:
                    df = fn()
                    for _, row in df.iterrows():
                        matched = False
                        for field in fields:
                            val = str(row.get(field, ""))
                            if any(kw.lower() in val.lower() for kw in keywords):
                                matched = True
                                break
                        if matched:
                            item = {
                                "标题": str(row.get("标题", row.get("内容", "")))[:100],
                                "摘要": str(row.get("摘要", row.get("内容", "")))[:200],
                                "发布时间": str(row.get("发布时间", row.get("时间", ""))),
                                "链接": str(row.get("链接", "")),
                                "来源": src_name + "-Bloomberg",
                            }
                            data.append(item)
                        if len(data) >= limit:
                            break
                    if len(data) >= limit:
                        break
                except Exception:
                    continue

        if not data:
            # Fallback：返回全球新闻概览
            try:
                df = ak.stock_info_global_em()
                for _, row in df.head(limit).iterrows():
                    data.append({
                        "标题": str(row.get("标题", ""))[:100],
                        "摘要": str(row.get("摘要", ""))[:200],
                        "发布时间": str(row.get("发布时间", "")),
                        "链接": str(row.get("链接", "")),
                        "来源": "东方财富-全球新闻",
                    })
                source = "fallback_global"
            except Exception:
                return json.dumps({
                    "ok": False,
                    "error": "未获取到彭博社相关新闻，可能是网络限制或暂无相关内容",
                }, ensure_ascii=False)

        data = _translate_records(data, fields=["标题", "摘要"], translate=translate)
        if len(data) > limit:
            data = data[:limit]

        return json.dumps({
            "ok": True,
            "source": source,
            "count": len(data),
            "translated": translate,
            "data": data,
        }, ensure_ascii=False)
    except Exception as e:
        return json.dumps({"ok": False, "error": f"{type(e).__name__}: {str(e)[:200]}"}, ensure_ascii=False)


@mcp.tool(description="获取彭博亿万富豪榜(Bloomberg Billionaires Index)")
def bloomberg_billionaires(limit: int = 50) -> str:
    """获取彭博亿万富豪榜数据。

    返回全球富豪排名、姓名、净资产、财富来源、国籍等信息。

    Args:
        limit: 返回条数，默认 50 条

    Returns:
        JSON 格式的富豪榜数据
    """
    try:
        df = ak.index_bloomberg_billionaires()
        if df is None or df.empty:
            # L3 兜底：Bloomberg 不可用时返回友好提示
            return json.dumps({
                "ok": True,
                "source": "bloomberg",
                "_tier": "L3_unavailable",
                "count": 0,
                "data": [],
                "note": "Bloomberg 数据源不可用（需翻墙访问），此为降级返回。可尝试使用 global_news_search 搜索相关新闻。",
            }, ensure_ascii=False)

        data = _df_to_records(df, limit)
        return json.dumps({
            "ok": True,
            "source": "bloomberg",
            "_tier": "L3",
            "count": len(data),
            "data": data,
        }, ensure_ascii=False)
    except Exception as e:
        # L3 兜底：返回友好降级而非报错
        return json.dumps({
            "ok": True,
            "source": "bloomberg",
            "_tier": "L3_fallback",
            "count": 0,
            "data": [],
            "error": f"{type(e).__name__}: {str(e)[:100]}",
            "note": "Bloomberg 数据源不可用（需翻墙访问），此为降级返回。可尝试使用 global_news_search 搜索相关新闻。",
        }, ensure_ascii=False)


@mcp.tool(description="搜索全球财经新闻（支持 Reuters/Bloomberg 等关键词筛选）")
def global_news_search(
    keyword: str,
    limit: int = 30,
    translate: bool = True,
) -> str:
    """搜索全球财经新闻。

    在多个聚合新闻源中搜索指定关键词，支持中文和英文关键词。
    常用关键词：Reuters, Bloomberg, 路透, 彭博, 美联储, 央行, 美股, 港股, 原油, 黄金等。

    Args:
        keyword: 搜索关键词
        limit: 返回条数，默认 30 条
        translate: 是否翻译英文内容，默认 True

    Returns:
        JSON 格式的搜索结果列表
    """
    try:
        if not keyword:
            return json.dumps({"ok": False, "error": "keyword 不能为空"}, ensure_ascii=False)

        data = []
        sources = [
            ("东方财富", ak.stock_info_global_em, ["标题", "摘要"]),
            ("新浪", ak.stock_info_global_sina, ["内容"]),
            ("同花顺", ak.stock_info_global_ths, ["标题", "内容"]),
            ("华尔街见闻", ak.macro_info_ws, ["事件", "地区"]),
        ]

        kw_lower = keyword.lower()
        for src_name, fn, fields in sources:
            try:
                df = fn()
                for _, row in df.iterrows():
                    matched = False
                    for field in fields:
                        val = str(row.get(field, ""))
                        if kw_lower in val.lower():
                            matched = True
                            break
                    if matched:
                        item = {
                            "标题": str(row.get("标题", row.get("事件", row.get("内容", ""))))[:100],
                            "摘要": str(row.get("摘要", row.get("内容", row.get("事件", ""))))[:200],
                            "发布时间": str(row.get("发布时间", row.get("时间", ""))),
                            "链接": str(row.get("链接", "")),
                            "来源": src_name,
                        }
                        data.append(item)
                    if len(data) >= limit:
                        break
                if len(data) >= limit:
                    break
            except Exception:
                continue

        if not data:
            return json.dumps({
                "ok": False,
                "error": f"未搜索到包含关键词 '{keyword}' 的新闻",
            }, ensure_ascii=False)

        data = _translate_records(data, fields=["标题", "摘要"], translate=translate)

        return json.dumps({
            "ok": True,
            "keyword": keyword,
            "count": len(data),
            "translated": translate,
            "data": data,
        }, ensure_ascii=False)
    except Exception as e:
        return json.dumps({"ok": False, "error": f"{type(e).__name__}: {str(e)[:200]}"}, ensure_ascii=False)


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


# ==================== 期货 ====================


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


# ==================== 外围指数 ====================


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


# ==================== ETF ====================


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


# ==================== AxData 数据源 ====================
# 基于 electkismet/AxData 开源量化数据库框架
# 提供更多数据源接口：东方财富涨停池/板块行情、财联社情绪/风口、
# 开盘红情绪、龙虎榜、期权合约、期货主力等

_axdata_client = None


def _get_axdata_client():
    """获取或初始化 AxData 客户端。"""
    global _axdata_client
    if _axdata_client is None:
        import axdata as ax
        _axdata_client = ax.AxDataClient()
    return _axdata_client


def _axdata_call(interface: str, **params) -> tuple[bool, list[dict]]:
    """调用 AxData 源端直取接口，返回 (是否成功, 数据列表)。"""
    try:
        client = _get_axdata_client()
        df = client.call(interface, **params)
        if df is None or df.empty:
            return True, []
        data = _df_to_records(df)
        return True, data
    except Exception as e:
        return False, [{"error": f"{type(e).__name__}: {str(e)[:200]}"}]


def _axdata_result(ok: bool, data: list[dict], source: str, interface: str, **extra) -> str:
    """构造 AxData 接口的标准返回。"""
    if not ok:
        return json.dumps({
            "ok": False,
            "source": source,
            "interface": interface,
            "error": data[0].get("error", "未知错误") if data else "未知错误",
        }, ensure_ascii=False)
    result = {
        "ok": True,
        "source": source,
        "interface": interface,
        "count": len(data),
        "data": data,
    }
    result.update(extra)
    return json.dumps(result, ensure_ascii=False)


# ---------- 涨停池 / 跌停池 ----------


@mcp.tool(description="获取A股涨停池（东方财富），包含涨停原因、连板数、主力资金等")
def stock_limit_up_pool(limit: int = 50) -> str:
    """获取当日涨停股票池。

    Args:
        limit: 返回条数，默认 50 条

    Returns:
        JSON 格式的涨停股列表，包含价格、涨跌幅、涨停时间、连板数、主力资金等
    """
    ok, data = _axdata_call("eastmoney_limit_up_pool")
    if ok and limit and len(data) > limit:
        data = data[:limit]
    return _axdata_result(ok, data, "eastmoney", "eastmoney_limit_up_pool")


@mcp.tool(description="获取A股跌停池（东方财富），包含跌停原因、开板次数等")
def stock_limit_down_pool(limit: int = 50) -> str:
    """获取当日跌停股票池。

    Args:
        limit: 返回条数，默认 50 条

    Returns:
        JSON 格式的跌停股列表
    """
    ok, data = _axdata_call("eastmoney_limit_down_pool")
    if ok and limit and len(data) > limit:
        data = data[:limit]
    return _axdata_result(ok, data, "eastmoney", "eastmoney_limit_down_pool")


# ---------- 板块行情 ----------


@mcp.tool(description="获取行业/概念板块实时行情（东方财富），包含涨跌幅、主力资金、领涨股等")
def sector_realtime(limit: int = 100) -> str:
    """获取板块实时行情列表。

    Args:
        limit: 返回条数，默认 100 条

    Returns:
        JSON 格式的板块行情列表，包含涨跌幅、成交额、主力净流入、领涨股等
    """
    ok, data = _axdata_call("eastmoney_sector_realtime")
    if ok and limit and len(data) > limit:
        data = data[:limit]
    return _axdata_result(ok, data, "eastmoney", "eastmoney_sector_realtime")


# ---------- 市场情绪 ----------


@mcp.tool(description="获取市场情绪指标（财联社），包含涨跌家数、涨停数、连板率、市场温度等")
def market_emotion_cls() -> str:
    """获取财联社市场情绪数据。

    Returns:
        JSON 格式的市场情绪数据，包含市场温度、涨跌分布、涨停梯队等
    """
    ok, data = _axdata_call("cls_market_emotion")
    return _axdata_result(ok, data, "cls", "cls_market_emotion")


@mcp.tool(description="获取市场情绪指标（开盘红），包含涨跌数、真实涨停数、ST涨跌数等")
def market_emotion_kph() -> str:
    """获取开盘红市场情绪数据。

    Returns:
        JSON 格式的市场情绪数据，包含涨停/跌停/真实涨停/ST涨跌等详细分布
    """
    ok, data = _axdata_call("kph_market_emotion")
    return _axdata_result(ok, data, "kph", "kph_market_emotion")


# ---------- 财联社特色数据 ----------


@mcp.tool(description="获取财联社涨停池，包含涨停原因详解")
def cls_limit_up_pool(limit: int = 50) -> str:
    """获取财联社涨停池（带涨停原因）。

    Args:
        limit: 返回条数，默认 50 条

    Returns:
        JSON 格式的涨停股列表，含详细涨停原因
    """
    ok, data = _axdata_call("cls_limit_up_pool")
    if ok and limit and len(data) > limit:
        data = data[:limit]
    return _axdata_result(ok, data, "cls", "cls_limit_up_pool")


@mcp.tool(description="获取财联社板块热度排行，包含实时热度值、排名变化等")
def cls_sector_heat() -> str:
    """获取财联社板块热度排行。

    Returns:
        JSON 格式的板块热度列表，20个热门板块
    """
    ok, data = _axdata_call("cls_sector_heat")
    return _axdata_result(ok, data, "cls", "cls_sector_heat")


@mcp.tool(description="获取财联社今日风口板块，包含催化原因")
def cls_market_wind() -> str:
    """获取财联社今日风口板块。

    Returns:
        JSON 格式的风口板块列表，含催化原因
    """
    ok, data = _axdata_call("cls_market_wind")
    return _axdata_result(ok, data, "cls", "cls_market_wind")


@mcp.tool(description="获取财联社今日主线机会，包含龙头股和板块详情")
def cls_market_mainline() -> str:
    """获取财联社今日主线机会。

    Returns:
        JSON 格式的主线机会数据，包含板块、龙头股、逻辑等
    """
    ok, data = _axdata_call("cls_market_mainline")
    return _axdata_result(ok, data, "cls", "cls_market_mainline")


# ---------- 龙虎榜 ----------


@mcp.tool(description="获取龙虎榜每日详情（新浪财经），包含上榜原因、买卖金额等")
def stock_lhb_daily(limit: int = 50) -> str:
    """获取龙虎榜每日详情。

    Args:
        limit: 返回条数，默认 50 条

    Returns:
        JSON 格式的龙虎榜数据
    """
    ok, data = _axdata_call("stock_lhb_detail_daily_sina")
    if ok and limit and len(data) > limit:
        data = data[:limit]
    return _axdata_result(ok, data, "sina", "stock_lhb_detail_daily_sina")


@mcp.tool(description="获取龙虎榜机构席位明细（新浪财经），包含机构买卖金额")
def stock_lhb_institution(limit: int = 50) -> str:
    """获取龙虎榜机构席位明细。

    Args:
        limit: 返回条数，默认 50 条

    Returns:
        JSON 格式的机构席位买卖数据
    """
    ok, data = _axdata_call("stock_lhb_jgmx_sina", limit=limit)
    return _axdata_result(ok, data, "sina", "stock_lhb_jgmx_sina")


# ---------- 期货 ----------


@mcp.tool(description="获取期货主力合约行情展示（新浪财经），含成交量/持仓量排行")
def futures_main_display(limit: int = 20) -> str:
    """获取期货主力合约行情展示。

    Args:
        limit: 返回条数，默认 20 条

    Returns:
        JSON 格式的主力期货行情列表
    """
    ok, data = _axdata_call("futures_display_main_sina")
    if ok and limit and len(data) > limit:
        data = data[:limit]
    return _axdata_result(ok, data, "sina", "futures_display_main_sina")


# ---------- 期权 ----------


@mcp.tool(description="获取商品期权品种列表（新浪财经）")
def option_commodity_list() -> str:
    """获取商品期权品种列表。

    Returns:
        JSON 格式的商品期权品种列表
    """
    ok, data = _axdata_call("option_commodity_contract_sina")
    return _axdata_result(ok, data, "sina", "option_commodity_contract_sina")


@mcp.tool(description="获取中金所沪深300期权合约列表（新浪财经）")
def option_cffex_hs300_list() -> str:
    """获取中金所沪深300期权合约列表。

    Returns:
        JSON 格式的期权合约列表
    """
    ok, data = _axdata_call("option_cffex_hs300_list_sina")
    return _axdata_result(ok, data, "sina", "option_cffex_hs300_list_sina")


# ==================== a-stock-data 补充信息源 ====================


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
            # 兜底：直接调用 sector_realtime 工具函数（L1 级别，内部有 axdata→akshare fallback）
            r = sector_realtime(limit=limit)
            d = json.loads(r)
            if d.get("ok") and d.get("data"):
                return json.dumps({
                    "ok": True,
                    "source": "sector_realtime_fallback",
                    "_tier": "L2_fallback_L1",
                    "count": d.get("count", 0),
                    "data": d["data"],
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
            # 兜底：直接调用 sector_realtime 工具函数（L1 级别，内部有 axdata→akshare fallback）
            r = sector_realtime(limit=100)
            d = json.loads(r)
            if d.get("ok") and d.get("data"):
                return json.dumps({
                    "ok": True,
                    "source": "sector_realtime_fallback",
                    "_tier": "L2_fallback_L1",
                    "count": d.get("count", 0),
                    "data": d["data"],
                    "note": "东财概念板块接口被封，已降级为板块实时行情",
                }, ensure_ascii=False)
            raise Exception("板块行情兜底也失败")
    except Exception as e:
        return json.dumps({"ok": False, "error": f"{type(e).__name__}: {str(e)[:200]}"}, ensure_ascii=False)


# ---------- 统一数据查询接口 ----------


def _convert_symbol_sina_to_tdx(symbol: str) -> str:
    """新浪格式(sh600519/sz000001/600519) -> TDX格式(600519.SH/000001.SZ)。"""
    s = symbol.upper().strip()
    if "." in s:
        return s
    s_lower = s.lower()
    if s_lower.startswith("sh"):
        return s[2:] + ".SH"
    if s_lower.startswith("sz"):
        return s[2:] + ".SZ"
    if len(s) == 6:
        if s[0] in "6" or s[:2] in ("68", "90", "51", "11", "13"):
            return s + ".SH"
        return s + ".SZ"
    return s


def _convert_symbol_tdx_to_sina(symbol: str) -> str:
    """TDX格式(600519.SH/000001.SZ) -> 新浪格式(sh600519/sz000001)。"""
    s = symbol.upper().strip()
    if s.endswith(".SH"):
        return "sh" + s[:-3]
    if s.endswith(".SZ"):
        return "sz" + s[:-3]
    s_lower = s.lower()
    if s_lower.startswith("sh") or s_lower.startswith("sz"):
        return s_lower
    if len(s) == 6:
        if s[0] in "6" or s[:2] in ("68", "90", "51", "11", "13"):
            return "sh" + s
        return "sz" + s
    return s


# 接口映射表：统一接口名 -> 配置字典
# 配置：axdata(接口名, 参数映射, 代码转换), akshare(函数名, 参数映射, 代码转换, 过滤字段)
_DATA_INTERFACE_MAP = {
    # ===== 个股 =====
    "stock_daily": {
        "desc": "A股日K线",
        "axdata": {"interface": "stock_zh_a_hist_tx", "param_map": {"symbol": "code"}, "symbol_fmt": "tdx"},
        "akshare": {"func": "stock_zh_a_daily", "param_map": {}, "symbol_fmt": "sina", "extra": {"adjust": "qfq"}},
    },
    "stock_realtime": {
        "desc": "A股实时行情（支持单只或多只代码过滤）",
        "axdata": None,
        "akshare": {"func": "stock_zh_a_spot_em", "param_map": {}, "symbol_fmt": None, "filter_by": "代码", "drop_params": ["symbol", "code"], "sina_fallback": True},
    },
    # ===== 指数 =====
    "index_daily": {
        "desc": "A股指数日K线",
        "axdata": None,
        "akshare": {"func": "stock_zh_index_daily", "param_map": {}, "symbol_fmt": "sina"},
    },
    "index_realtime": {
        "desc": "A股指数实时行情",
        "axdata": {"interface": "stock_zh_index_spot_sina", "param_map": {}, "symbol_fmt": None},
        "akshare": {"func": "stock_zh_index_spot_em", "param_map": {}, "symbol_fmt": None, "drop_params": ["symbol", "code"], "sina_fallback": True},
    },
    # ===== ETF =====
    "etf_daily": {
        "desc": "ETF日K线",
        "axdata": {"interface": "fund_etf_hist_sina", "param_map": {}, "symbol_fmt": "sina"},
        "akshare": {"func": "fund_etf_hist_sina", "param_map": {}, "symbol_fmt": "sina"},
    },
    "etf_realtime": {
        "desc": "ETF实时行情",
        "axdata": None,
        "akshare": {"func": "fund_etf_spot_em", "param_map": {}, "symbol_fmt": None, "filter_by": "代码", "drop_params": ["symbol", "code"], "sina_fallback": True},
    },
    # ===== 期货 =====
    "futures_daily": {
        "desc": "期货日线（主力合约）",
        "axdata": {"interface": "futures_main_sina", "param_map": {}, "symbol_fmt": None},
        "akshare": {"func": "futures_zh_daily_sina", "param_map": {}, "symbol_fmt": None},
    },
    "futures_realtime": {
        "desc": "期货实时行情（主力合约展示）",
        "axdata": {"interface": "futures_display_main_sina", "param_map": {}, "symbol_fmt": None},
        "akshare": {"func": "futures_zh_realtime_sina", "param_map": {}, "symbol_fmt": None, "filter_by": "symbol", "drop_params": ["symbol"]},
    },
    # ===== 外围指数 =====
    "index_us_daily": {
        "desc": "美股指数日线",
        "axdata": {"interface": "index_us_stock_sina", "param_map": {}, "symbol_fmt": None},
        "akshare": None,
    },
    "index_hk_daily": {
        "desc": "港股指数日线",
        "axdata": {"interface": "stock_hk_index_daily_sina", "param_map": {}, "symbol_fmt": None},
        "akshare": None,
    },
    # ===== 涨跌停 / 板块 =====
    "limit_up_pool": {
        "desc": "涨停池（含涨停原因、连板数）",
        "axdata": {"interface": "eastmoney_limit_up_pool", "param_map": {}, "symbol_fmt": None},
        "akshare": None,
    },
    "limit_down_pool": {
        "desc": "跌停池",
        "axdata": {"interface": "eastmoney_limit_down_pool", "param_map": {}, "symbol_fmt": None},
        "akshare": None,
    },
    "sector_realtime": {
        "desc": "板块实时行情（涨跌幅、主力资金、领涨股）",
        "axdata": {"interface": "eastmoney_sector_realtime", "param_map": {}, "symbol_fmt": None},
        "akshare": None,
    },
    "market_index_realtime": {
        "desc": "大盘指数实时行情",
        "axdata": {"interface": "eastmoney_market_index_realtime", "param_map": {}, "symbol_fmt": None},
        "akshare": None,
    },
    # ===== 财联社 =====
    "cls_telegraph": {
        "desc": "财联社电报快讯",
        "axdata": {"interface": "cls_news_telegraph", "param_map": {}, "symbol_fmt": None},
        "akshare": None,
    },
    "cls_market_emotion": {
        "desc": "财联社市场情绪（温度、涨跌分布、涨停梯队）",
        "axdata": {"interface": "cls_market_emotion", "param_map": {}, "symbol_fmt": None},
        "akshare": None,
    },
    "cls_limit_up_pool": {
        "desc": "财联社涨停池（含详细涨停原因）",
        "axdata": {"interface": "cls_limit_up_pool", "param_map": {}, "symbol_fmt": None},
        "akshare": None,
    },
    "cls_sector_heat": {
        "desc": "财联社板块热度排行",
        "axdata": {"interface": "cls_sector_heat", "param_map": {}, "symbol_fmt": None},
        "akshare": None,
    },
    "cls_market_wind": {
        "desc": "财联社今日风口板块（含催化原因）",
        "axdata": {"interface": "cls_market_wind", "param_map": {}, "symbol_fmt": None},
        "akshare": None,
    },
    "cls_market_mainline": {
        "desc": "财联社今日主线机会（含龙头股、逻辑）",
        "axdata": {"interface": "cls_market_mainline", "param_map": {}, "symbol_fmt": None},
        "akshare": None,
    },
    # ===== 开盘红 =====
    "kph_market_emotion": {
        "desc": "开盘红市场情绪（真实涨停、ST涨跌、涨跌分布）",
        "axdata": {"interface": "kph_market_emotion", "param_map": {}, "symbol_fmt": None},
        "akshare": None,
    },
    # ===== 龙虎榜 =====
    "lhb_daily": {
        "desc": "龙虎榜每日详情",
        "axdata": {"interface": "stock_lhb_detail_daily_sina", "param_map": {}, "symbol_fmt": None},
        "akshare": None,
    },
    "lhb_institution": {
        "desc": "龙虎榜机构席位明细",
        "axdata": {"interface": "stock_lhb_jgmx_sina", "param_map": {}, "symbol_fmt": None},
        "akshare": None,
    },
    # ===== 期权 =====
    "option_commodity_list": {
        "desc": "商品期权品种列表",
        "axdata": {"interface": "option_commodity_contract_sina", "param_map": {}, "symbol_fmt": None},
        "akshare": None,
    },
    "option_cffex_hs300_list": {
        "desc": "中金所沪深300期权合约列表",
        "axdata": {"interface": "option_cffex_hs300_list_sina", "param_map": {}, "symbol_fmt": None},
        "akshare": None,
    },
    # ===== 巨潮 =====
    "cninfo_announcements": {
        "desc": "巨潮公告列表",
        "axdata": {"interface": "cninfo_announcements", "param_map": {"symbol": "code"}, "symbol_fmt": None},
        "akshare": None,
    },
    "stock_profile_cninfo": {
        "desc": "公司概况（巨潮）",
        "axdata": {"interface": "stock_profile_cninfo", "param_map": {"symbol": "code"}, "symbol_fmt": None},
        "akshare": None,
    },
    "stock_dividend_cninfo": {
        "desc": "分红配送（巨潮）",
        "axdata": {"interface": "stock_dividend_cninfo", "param_map": {"symbol": "code"}, "symbol_fmt": None},
        "akshare": None,
    },
    # ===== 新闻 =====
    "news_cctv": {
        "desc": "新闻联播文字稿",
        "axdata": None,
        "akshare": {"func": "news_cctv", "param_map": {}, "symbol_fmt": None, "drop_params": ["symbol", "code"]},
    },
    "economic_calendar": {
        "desc": "财经日历（百度）",
        "axdata": None,
        "akshare": {"func": "news_economic_baidu", "param_map": {}, "symbol_fmt": None, "drop_params": ["symbol", "code"]},
    },
    "stock_news": {
        "desc": "个股新闻（东方财富）",
        "axdata": None,
        "akshare": {"func": "stock_news_em", "param_map": {}, "symbol_fmt": None},
    },
    # ===== 外围新闻（含英文翻译） =====
    "global_news_em": {
        "desc": "全球财经新闻（东方财富，含英文翻译）",
        "axdata": None,
        "akshare": {"func": "stock_info_global_em", "param_map": {}, "symbol_fmt": None, "drop_params": ["symbol", "code"], "translate_fields": ["标题", "摘要"]},
    },
    "global_news_sina": {
        "desc": "全球财经快讯（新浪，含英文翻译）",
        "axdata": None,
        "akshare": {"func": "stock_info_global_sina", "param_map": {}, "symbol_fmt": None, "drop_params": ["symbol", "code"], "translate_fields": ["内容"]},
    },
    "global_news_ths": {
        "desc": "全球财经新闻（同花顺，含英文翻译）",
        "axdata": None,
        "akshare": {"func": "stock_info_global_ths", "param_map": {}, "symbol_fmt": None, "drop_params": ["symbol", "code"], "translate_fields": ["标题", "内容"]},
    },
    "wallstreet_news": {
        "desc": "华尔街见闻财经日历（含英文事件名翻译）",
        "axdata": None,
        "akshare": {"func": "macro_info_ws", "param_map": {}, "symbol_fmt": None, "drop_params": ["symbol", "code"], "translate_fields": ["事件", "地区"]},
    },
    "futures_news_shmet": {
        "desc": "上海期货交易所新闻（含英文翻译）",
        "axdata": None,
        "akshare": {"func": "futures_news_shmet", "param_map": {}, "symbol_fmt": None, "drop_params": ["symbol", "code"], "translate_fields": ["内容"]},
    },
    # ===== 外围指数（补充实时行情） =====
    "index_us_daily": {
        "desc": "美股指数日线（道琼斯/纳斯达克/标普500）",
        "axdata": {"interface": "index_us_stock_sina", "param_map": {}, "symbol_fmt": None},
        "akshare": {"func": "index_us_stock_sina", "param_map": {}, "symbol_fmt": None},
    },
    "index_hk_daily": {
        "desc": "港股指数日线（恒生/国企/恒生科技）",
        "axdata": {"interface": "stock_hk_index_daily_sina", "param_map": {}, "symbol_fmt": None},
        "akshare": {"func": "stock_hk_index_daily_sina", "param_map": {}, "symbol_fmt": None},
    },
    "index_global_list": {
        "desc": "全球指数代码表",
        "axdata": None,
        "akshare": {"func": "index_global_name_table", "param_map": {}, "symbol_fmt": None, "drop_params": ["symbol", "code"]},
    },
    "futures_global_spot": {
        "desc": "全球期货实时行情（CBOT/NYMEX/COMEX/LME）",
        "axdata": None,
        "akshare": {"func": "futures_global_spot_em", "param_map": {}, "symbol_fmt": None, "drop_params": ["symbol", "code"]},
    },
    "etf_spot": {
        "desc": "ETF实时行情列表",
        "axdata": None,
        "akshare": {"func": "fund_etf_spot_em", "param_map": {}, "symbol_fmt": None, "drop_params": ["symbol", "code"], "filter_by": "代码"},
    },
    # ===== Reuters / Bloomberg 新闻源 =====
    "reuters_news": {
        "desc": "路透社相关财经新闻（含英文翻译）",
        "axdata": None,
        "akshare": None,
    },
    "bloomberg_news": {
        "desc": "彭博社相关财经新闻（含英文翻译）",
        "axdata": None,
        "akshare": None,
    },
    "bloomberg_billionaires": {
        "desc": "彭博亿万富豪榜",
        "axdata": None,
        "akshare": {"func": "index_bloomberg_billionaires", "param_map": {}, "symbol_fmt": None, "drop_params": ["symbol", "code"]},
    },
    "global_news_search": {
        "desc": "全球财经新闻搜索（支持 Reuters/Bloomberg/关键词）",
        "axdata": None,
        "akshare": None,
    },
    # ===== a-stock-data 补充信息源 =====
    "tencent_realtime_quote": {
        "desc": "腾讯财经实时行情（PE/PB/市值/换手率/涨跌停价，不封IP）",
        "axdata": None,
        "akshare": None,
    },
    "northbound_flow": {
        "desc": "北向资金(沪深港通)实时流向",
        "axdata": None,
        "akshare": {"func": "stock_hsgt_individual_em", "param_map": {}, "symbol_fmt": None, "drop_params": ["symbol", "code"]},
    },
    "stock_fund_flow": {
        "desc": "个股资金流向（主力/大单/中单/小单）",
        "axdata": None,
        "akshare": {"func": "stock_individual_fund_flow", "param_map": {}, "symbol_fmt": None, "drop_params": []},
    },
    "margin_trading": {
        "desc": "融资融券数据（沪市/深市）",
        "axdata": None,
        "akshare": {"func": "stock_margin_sse", "param_map": {}, "symbol_fmt": None, "drop_params": ["symbol", "code"]},
    },
    "block_trade": {
        "desc": "大宗交易数据",
        "axdata": None,
        "akshare": {"func": "stock_dzjy_mrmx", "param_map": {}, "symbol_fmt": None, "drop_params": ["symbol", "code"]},
    },
    "holder_count": {
        "desc": "股东户数变化（筹码集中度）",
        "axdata": None,
        "akshare": {"func": "stock_zh_a_gdhs", "param_map": {}, "symbol_fmt": None, "drop_params": []},
    },
    "lockup_release": {
        "desc": "限售解禁日历",
        "axdata": None,
        "akshare": {"func": "stock_restricted_release_queue_sse", "param_map": {}, "symbol_fmt": None, "drop_params": ["symbol", "code"]},
    },
    "research_report": {
        "desc": "研报列表（个股盈利预测）",
        "axdata": None,
        "akshare": {"func": "stock_profit_forecast_ths", "param_map": {}, "symbol_fmt": None, "drop_params": []},
    },
    "eps_forecast": {
        "desc": "一致预期EPS（同花顺）",
        "axdata": None,
        "akshare": {"func": "stock_profit_forecast_ths", "param_map": {}, "symbol_fmt": None, "drop_params": []},
    },
    "limit_up_broken": {
        "desc": "炸板池（曾涨停又开板）",
        "axdata": None,
        "akshare": {"func": "stock_zt_pool_dtgc_em", "param_map": {}, "symbol_fmt": None, "drop_params": ["symbol", "code"]},
    },
    "limit_up_previous": {
        "desc": "昨日涨停池（今表现）",
        "axdata": None,
        "akshare": {"func": "stock_zt_pool_previous_em", "param_map": {}, "symbol_fmt": None, "drop_params": ["symbol", "code"]},
    },
    "limit_up_strong": {
        "desc": "强势股池（连板等）",
        "axdata": None,
        "akshare": {"func": "stock_zt_pool_strong_em", "param_map": {}, "symbol_fmt": None, "drop_params": ["symbol", "code"]},
    },
    "option_t_quote": {
        "desc": "ETF期权T型报价",
        "axdata": None,
        "akshare": {"func": "option_current_em", "param_map": {}, "symbol_fmt": None, "drop_params": []},
    },
    "hot_rank": {
        "desc": "东财人气排行榜",
        "axdata": None,
        "akshare": {"func": "stock_hot_rank_em", "param_map": {}, "symbol_fmt": None, "drop_params": ["symbol", "code"]},
    },
    "concept_belong": {
        "desc": "个股概念板块归属",
        "axdata": None,
        "akshare": {"func": "stock_board_concept_name_em", "param_map": {}, "symbol_fmt": None, "drop_params": ["symbol", "code"]},
    },
}


def _adapt_params(params: dict, cfg: dict) -> dict:
    """根据配置转换参数名和代码格式。"""
    result = {}
    param_map = cfg.get("param_map", {})
    symbol_fmt = cfg.get("symbol_fmt")
    drop_params = set(cfg.get("drop_params", []))

    for key, val in params.items():
        if key in drop_params:
            continue
        new_key = param_map.get(key, key)
        result[new_key] = val

    # 代码格式转换
    sym = result.get("symbol") or result.get("code") or result.get("instrument_id")
    sym_key = "symbol" if "symbol" in result else ("code" if "code" in result else None)
    if sym and sym_key and symbol_fmt:
        if symbol_fmt == "tdx":
            result[sym_key] = _convert_symbol_sina_to_tdx(sym)
        elif symbol_fmt == "sina":
            result[sym_key] = _convert_symbol_tdx_to_sina(sym)

    # 添加额外参数
    extra = cfg.get("extra", {})
    for k, v in extra.items():
        if k not in result:
            result[k] = v

    # 移除 limit 参数（源端不一定支持）
    result.pop("limit", None)

    return result


def _filter_data(data: list[dict], cfg: dict, params: dict) -> list[dict]:
    """客户端过滤：根据 symbol 参数过滤数据。"""
    filter_by = cfg.get("filter_by")
    sym = params.get("symbol") or params.get("code")
    if not filter_by or not sym:
        return data

    sym_clean = str(sym).lower().replace("sh", "").replace("sz", "").replace(".sh", "").replace(".sz", "")
    sym_list = [s.strip().lower().replace("sh", "").replace("sz", "").replace(".sh", "").replace(".sz", "")
                for s in str(sym).split(",")]

    filtered = []
    for item in data:
        val = str(item.get(filter_by, "")).lower()
        val_clean = val.replace("sh", "").replace("sz", "").replace(".sh", "").replace(".sz", "")
        if val_clean in sym_list or any(s in val_clean for s in sym_list):
            filtered.append(item)
    return filtered


def _call_axdata(cfg: dict, **params) -> tuple[bool, list[dict], str]:
    """调用 axdata 接口。"""
    try:
        client = _get_axdata_client()
        adapted = _adapt_params(params, cfg)
        df = client.call(cfg["interface"], **adapted)
        if df is not None and not df.empty:
            data = _df_to_records(df)
            # 客户端过滤
            data = _filter_data(data, cfg, params)
            return True, data, f"axdata:{cfg['interface']}"
        return False, [], f"axdata:{cfg['interface']}"
    except Exception as e:
        return False, [{"error": f"{type(e).__name__}: {str(e)[:200]}"}], f"axdata:{cfg['interface']}"


def _call_akshare(cfg: dict, **params) -> tuple[bool, list[dict], str]:
    """调用 akshare 接口。"""
    try:
        func = getattr(ak, cfg["func"])
        adapted = _adapt_params(params, cfg)
        df = func(**adapted)
        if df is not None and not df.empty:
            data = _df_to_records(df)
            # 客户端过滤
            data = _filter_data(data, cfg, params)
            return True, data, f"akshare:{cfg['func']}"
        return False, [], f"akshare:{cfg['func']}"
    except Exception as e:
        # 新浪 fallback（针对 push2 域名不可用的情况）
        if cfg.get("sina_fallback"):
            sym = params.get("symbol") or params.get("code")
            if sym:
                sym_list = [s.strip() for s in str(sym).split(",") if s.strip()]
                data = _get_sina_spot(sym_list)
                if data:
                    return True, data, "sina:direct"
        return False, [{"error": f"{type(e).__name__}: {str(e)[:200]}"}], f"akshare:{cfg['func']}"


def _call_unified(interface: str, **params) -> tuple[bool, list[dict], str]:
    """统一数据调用：自动路由到 axdata 或 akshare。

    返回 (是否成功, 数据列表, 实际数据源)。
    路由策略：
    1. 如果在映射表中，优先用 axdata，失败 fallback akshare
    2. 如果不在映射表中，尝试直接调用 axdata
    """
    cfg = _DATA_INTERFACE_MAP.get(interface)

    if cfg:
        axdata_cfg = cfg.get("axdata")
        akshare_cfg = cfg.get("akshare")

        last_error = None
        last_source = "unknown"

        # 优先 axdata
        if axdata_cfg:
            ok, data, source = _call_axdata(axdata_cfg, **params)
            if ok and data:
                return ok, data, source
            if not ok:
                last_error = data[0].get("error", "未知错误") if data else "未知错误"
                last_source = source
            else:
                last_source = source

        # fallback akshare
        if akshare_cfg:
            ok, data, source = _call_akshare(akshare_cfg, **params)
            if ok and data:
                return ok, data, source
            if not ok:
                last_error = data[0].get("error", "未知错误") if data else "未知错误"
                last_source = source
            else:
                last_source = source

        # 都没有数据，返回最后的错误或空结果
        if last_error:
            return False, [{"error": last_error}], last_source
        return True, [], last_source

    # 不在映射表中，尝试直接调 axdata
    try:
        client = _get_axdata_client()
        df = client.call(interface, **params)
        if df is not None and not df.empty:
            return True, _df_to_records(df), f"axdata:{interface}"
        return True, [], f"axdata:{interface}"
    except Exception as e:
        return False, [{"error": f"{type(e).__name__}: {str(e)[:200]}"}], f"axdata:{interface}"


@mcp.tool(description="统一数据查询接口：整合 akshare + axdata 两个数据源，自动路由到最佳来源，支持英文翻译")
def data_query(
    interface: str,
    params_json: Optional[str] = None,
    limit: int = 0,
    translate: bool = True,
) -> str:
    """统一数据查询接口。

    整合 akshare 和 axdata 两个数据源，自动路由到最佳来源。
    优先使用 axdata（字段更规范），失败时自动 fallback 到 akshare。
    自动处理参数名转换、代码格式转换（新浪/TDX 格式互转）。
    对配置了 translate_fields 的接口（外围新闻等）自动翻译英文为中文。

    支持三种调用方式：
    1. 用统一别名（推荐）：interface="limit_up_pool"
    2. 用 axdata 原始接口名：interface="eastmoney_limit_up_pool"
    3. 用 akshare 函数名：interface="stock_zh_a_daily"

    常用统一别名（完整列表用 data_interfaces 工具查看）：
    - stock_daily: A股日K线（symbol 支持 sh600519 / 600519 / 600519.SH）
    - stock_realtime: A股实时行情（支持 symbol 过滤多只）
    - index_daily: 指数日K线
    - index_realtime: 指数实时行情
    - etf_daily: ETF日K线
    - etf_realtime: ETF实时行情
    - futures_daily: 期货日线
    - futures_realtime: 期货实时行情
    - limit_up_pool: 涨停池
    - limit_down_pool: 跌停池
    - sector_realtime: 板块实时行情
    - cls_market_emotion: 财联社市场情绪
    - cls_market_wind: 财联社今日风口
    - cls_market_mainline: 财联社今日主线
    - lhb_daily: 龙虎榜每日详情
    - option_commodity_list: 商品期权品种列表
    - kph_market_emotion: 开盘红市场情绪
    - global_news_em: 全球财经新闻（含英文翻译）
    - global_news_sina: 全球财经快讯（含英文翻译）
    - global_news_ths: 全球财经新闻-同花顺（含英文翻译）
    - wallstreet_news: 华尔街见闻财经日历（含英文翻译）
    - futures_news_shmet: 上海期货所新闻（含英文翻译）
    - index_us_daily: 美股指数日线（道琼斯/纳斯达克/标普500）
    - index_hk_daily: 港股指数日线（恒生/国企/恒生科技）
    - futures_global_spot: 全球期货实时行情（CBOT/NYMEX/COMEX/LME）

    Args:
        interface: 接口名称，可以是统一别名、axdata接口名或akshare函数名
        params_json: JSON 格式的参数字典，如 {"symbol": "600519", "limit": 10}，可选
        limit: 返回条数限制，0 表示不限制
        translate: 是否对英文内容进行翻译（仅对配置了 translate_fields 的接口生效），默认 True

    Returns:
        JSON 格式的查询结果，包含 source 字段标识实际数据源
    """
    try:
        params = {}
        if params_json:
            params = json.loads(params_json)

        ok, data, source = _call_unified(interface, **params)

        if not ok:
            err_msg = data[0].get("error", "未知错误") if data else "未知错误"
            return json.dumps({
                "ok": False,
                "interface": interface,
                "source": source,
                "error": err_msg,
            }, ensure_ascii=False)

        if limit and len(data) > limit:
            data = data[:limit]

        # 自动翻译：查找接口配置中的 translate_fields
        translated = False
        if translate and data:
            cfg = _DATA_INTERFACE_MAP.get(interface)
            if cfg:
                # 合并 axdata 和 akshare 配置中的 translate_fields
                tfields = set()
                for src_key in ("axdata", "akshare"):
                    src_cfg = cfg.get(src_key)
                    if src_cfg and src_cfg.get("translate_fields"):
                        tfields.update(src_cfg["translate_fields"])
                if tfields:
                    _translate_records(data, fields=tfields, translate=True)
                    translated = True

        return json.dumps({
            "ok": True,
            "interface": interface,
            "source": source,
            "count": len(data),
            "translated": translated,
            "data": data,
        }, ensure_ascii=False)
    except Exception as e:
        return json.dumps({
            "ok": False,
            "interface": interface,
            "error": f"{type(e).__name__}: {str(e)[:200]}",
        }, ensure_ascii=False)


@mcp.tool(description="列出所有可用的统一数据接口及其数据源映射")
def data_interfaces() -> str:
    """列出所有可用的统一数据接口。

    返回统一别名、axdata接口名、akshare函数名和说明，
    供用户查询 data_query 工具可用的接口名。

    Returns:
        JSON 格式的接口映射表
    """
    interfaces = []
    for alias, cfg in _DATA_INTERFACE_MAP.items():
        axdata_iface = cfg.get("axdata", {}).get("interface") if cfg.get("axdata") else None
        akshare_func = cfg.get("akshare", {}).get("func") if cfg.get("akshare") else None
        interfaces.append({
            "alias": alias,
            "description": cfg.get("desc", ""),
            "axdata_interface": axdata_iface,
            "akshare_function": akshare_func,
            "priority": "axdata" if axdata_iface else ("akshare" if akshare_func else "none"),
        })
    return json.dumps({
        "ok": True,
        "count": len(interfaces),
        "note": "data_query 支持用 alias、axdata_interface 或 akshare_function 调用，自动路由+自动格式转换",
        "interfaces": interfaces,
    }, ensure_ascii=False)


# ==================== L0-L3 等级制度工具 ====================


@mcp.tool(description="查询工具的数据源等级（L0-L3）和兜底链路")
def tool_tier_info(tool_name: str = "") -> str:
    """查询工具的 L0-L3 等级和兜底信息。

    等级定义：
      L0 核心层  — 本地可用，无网络依赖
      L1 稳定层  — akshare 稳定 API + 腾讯直连（不封 IP）
      L2 限流层  — 东财 datacenter/push2（需限流，可能被封）
      L3 受限层  — 国际源 Reuters/Bloomberg（需翻墙）

    兜底链路：L3 → L2 → L1 → L0

    Args:
        tool_name: 工具名（可选），传入则查询单个工具；不传则列出所有工具的等级

    Returns:
        JSON 格式的工具等级信息
    """
    if tool_name:
        info = tier_info(tool_name)
        return json.dumps({
            "ok": True,
            "tool": tool_name,
            "tier": info["tier_name"],
            "fallback_chain": info["fallback"],
            "description": {
                "L0_CORE": "本地核心，无网络依赖",
                "L1_STABLE": "稳定数据源，不封IP",
                "L2_RATED": "限流数据源，可能被封",
                "L3_RESTRICTED": "国际源，需翻墙",
            }.get(info["tier_name"], "未知"),
        }, ensure_ascii=False)

    # 列出所有工具的等级
    result = {}
    for name in sorted(TOOL_TIERS.keys()):
        info = tier_info(name)
        result[name] = {
            "tier": info["tier_name"],
            "fallback": info["fallback"],
        }
    return json.dumps({
        "ok": True,
        "count": len(result),
        "tiers": {
            "L0_CORE": "本地核心（翻译、接口列表）",
            "L1_STABLE": "稳定数据（akshare核心API + 腾讯直连）",
            "L2_RATED": "限流数据（东财 push2/datacenter）",
            "L3_RESTRICTED": "受限数据（Reuters/Bloomberg 国际源）",
        },
        "tools": result,
    }, ensure_ascii=False)


# ==================== 调度 / 存储 / 记忆 管理模块 ====================
# 集成 APScheduler + SQLite + Redis，提供数据持久化和定时任务能力

_storage = None
_dedup = None
_scheduler = None


def _get_storage():
    """获取或初始化 SQLite 存储。"""
    global _storage
    if _storage is None:
        import os
        from core.storage import SQLiteStorage
        db_path = os.environ.get("AKSHARE_DB_PATH", "data/akshare_memory.db")
        _storage = SQLiteStorage(db_path=db_path)
    return _storage


def _get_dedup():
    """获取或初始化 Redis 去重缓存。"""
    global _dedup
    if _dedup is None:
        import os
        from core.dedup import RedisDedup
        redis_url = os.environ.get("REDIS_URL", "redis://localhost:6379/0")
        _dedup = RedisDedup(redis_url=redis_url)
    return _dedup


def _get_tool_registry():
    """构造工具名 -> 函数 的注册表（供调度器调用）。"""
    import inspect
    registry = {}
    for name, obj in list(globals().items()):
        if callable(obj) and not name.startswith("_") and name != "mcp":
            try:
                sig = inspect.signature(obj)
                if sig.parameters:
                    registry[name] = obj
            except (TypeError, ValueError):
                continue
    return registry


def _get_scheduler():
    """获取或初始化任务调度器。"""
    global _scheduler
    if _scheduler is None:
        from core.scheduler import TaskScheduler
        storage = _get_storage()
        dedup = _get_dedup()
        registry = _get_tool_registry()
        _scheduler = TaskScheduler(storage=storage, dedup=dedup, tool_registry=registry)
    return _scheduler


def _start_scheduler_if_needed():
    """如果尚未启动则启动调度器（首次调用时启动）。"""
    import os
    if os.environ.get("AKSHARE_DISABLE_SCHEDULER", "").lower() in ("1", "true", "yes"):
        return
    sched = _get_scheduler()
    if not sched._running:
        try:
            sched.start()
        except Exception:
            pass


# ─────────────── 记忆/存储管理工具 ───────────────

@mcp.tool(description="查询存储统计：新闻数、行情快照数、记忆数、调度任务数")
def memory_stats() -> str:
    """获取存储层统计信息。"""
    try:
        storage = _get_storage()
        dedup = _get_dedup()
        stats = storage.stats()
        stats["redis_available"] = dedup.available
        return json.dumps({"ok": True, "stats": stats}, ensure_ascii=False)
    except Exception as e:
        return json.dumps({"ok": False, "error": f"{type(e).__name__}: {str(e)[:200]}"}, ensure_ascii=False)


@mcp.tool(description="查询历史新闻数据，支持按来源/关键词过滤")
def memory_query_news(source: Optional[str] = None, keyword: Optional[str] = None,
                      limit: int = 50, offset: int = 0) -> str:
    """从 SQLite 查询已保存的历史新闻数据。

    Args:
        source: 数据源过滤，如 cls_telegraph, global_news_em 等，可选
        keyword: 关键词搜索（标题/内容/摘要），可选
        limit: 返回条数，默认 50
        offset: 分页偏移，默认 0

    Returns:
        JSON 格式的新闻列表
    """
    try:
        storage = _get_storage()
        data = storage.query_news(source=source, keyword=keyword, limit=limit, offset=offset)
        return json.dumps({
            "ok": True,
            "source": source or "all",
            "count": len(data),
            "offset": offset,
            "data": data,
        }, ensure_ascii=False)
    except Exception as e:
        return json.dumps({"ok": False, "error": f"{type(e).__name__}: {str(e)[:200]}"}, ensure_ascii=False)


@mcp.tool(description="写入通用记忆（key-value），供 agent 长期保存信息")
def memory_set(key: str, value: str, tags: str = "") -> str:
    """写入一条通用记忆。

    Args:
        key: 记忆键（唯一）
        value: 记忆值
        tags: 标签（逗号分隔），用于分类检索

    Returns:
        JSON 结果
    """
    try:
        storage = _get_storage()
        storage.set_memory(key=key, value=value, tags=tags)
        return json.dumps({"ok": True, "key": key, "message": "已保存"}, ensure_ascii=False)
    except Exception as e:
        return json.dumps({"ok": False, "error": f"{type(e).__name__}: {str(e)[:200]}"}, ensure_ascii=False)


@mcp.tool(description="读取通用记忆")
def memory_get(key: str) -> str:
    """读取一条通用记忆。

    Args:
        key: 记忆键

    Returns:
        JSON 结果，包含 value 字段
    """
    try:
        storage = _get_storage()
        value = storage.get_memory(key)
        if value is None:
            return json.dumps({"ok": False, "key": key, "error": "未找到"}, ensure_ascii=False)
        return json.dumps({"ok": True, "key": key, "value": value}, ensure_ascii=False)
    except Exception as e:
        return json.dumps({"ok": False, "error": f"{type(e).__name__}: {str(e)[:200]}"}, ensure_ascii=False)


@mcp.tool(description="搜索通用记忆，支持关键词和标签过滤")
def memory_search(keyword: str = "", tag: str = "", limit: int = 50) -> str:
    """搜索通用记忆。

    Args:
        keyword: 关键词（匹配 key 和 value）
        tag: 标签过滤
        limit: 返回条数，默认 50

    Returns:
        JSON 格式的记忆列表
    """
    try:
        storage = _get_storage()
        data = storage.search_memory(keyword=keyword, tag=tag, limit=limit)
        return json.dumps({"ok": True, "count": len(data), "data": data}, ensure_ascii=False)
    except Exception as e:
        return json.dumps({"ok": False, "error": f"{type(e).__name__}: {str(e)[:200]}"}, ensure_ascii=False)


@mcp.tool(description="删除通用记忆")
def memory_delete(key: str) -> str:
    """删除一条通用记忆。

    Args:
        key: 记忆键

    Returns:
        JSON 结果
    """
    try:
        storage = _get_storage()
        ok = storage.delete_memory(key)
        return json.dumps({"ok": ok, "key": key}, ensure_ascii=False)
    except Exception as e:
        return json.dumps({"ok": False, "error": f"{type(e).__name__}: {str(e)[:200]}"}, ensure_ascii=False)


@mcp.tool(description="清理历史新闻数据，可按来源或天数过滤")
def memory_clear_news(source: Optional[str] = None, days: Optional[int] = None) -> str:
    """清理历史新闻数据。

    Args:
        source: 按来源清理，可选
        days: 只保留最近 N 天的数据，可选

    Returns:
        JSON 结果，包含删除条数
    """
    try:
        storage = _get_storage()
        count = storage.clear_news(source=source, days=days)
        return json.dumps({"ok": True, "deleted": count}, ensure_ascii=False)
    except Exception as e:
        return json.dumps({"ok": False, "error": f"{type(e).__name__}: {str(e)[:200]}"}, ensure_ascii=False)


# ─────────────── 调度器管理工具 ───────────────

@mcp.tool(description="列出所有定时调度任务及其状态")
def scheduler_list() -> str:
    """列出所有调度任务。

    Returns:
        JSON 格式的任务列表，包含运行状态、下次执行时间等
    """
    try:
        _start_scheduler_if_needed()
        sched = _get_scheduler()
        tasks = sched.list_tasks()
        return json.dumps({
            "ok": True,
            "scheduler_running": sched._running,
            "count": len(tasks),
            "tasks": tasks,
        }, ensure_ascii=False)
    except Exception as e:
        return json.dumps({"ok": False, "error": f"{type(e).__name__}: {str(e)[:200]}"}, ensure_ascii=False)


@mcp.tool(description="添加定时任务，支持 cron 表达式或间隔分钟")
def scheduler_add(
    task_name: str,
    task_type: str,
    cron_expr: Optional[str] = None,
    interval_minutes: Optional[int] = None,
    params_json: str = "{}",
    description: str = "",
) -> str:
    """添加一个新的定时任务。

    Args:
        task_name: 任务名称（唯一标识）
        task_type: 任务类型：news_fetch（新闻抓取入库）、market_snapshot（行情快照）、custom_call（自定义调用）
        cron_expr: cron 表达式（5 段式：分 时 日 月 周），与 interval_minutes 二选一
        interval_minutes: 间隔分钟数，与 cron_expr 二选一
        params_json: 任务参数字典的 JSON 字符串，根据 task_type 不同而不同
        description: 任务描述

    task_type 对应的 params:
      - news_fetch: {"tool": "工具名", "tool_params": {...}, "source_override": "", "id_field": "id"}
      - market_snapshot: {"tool": "工具名", "tool_params": {...}, "snapshot_type": "", "symbol": ""}
      - custom_call: {"tool": "工具名", "tool_params": {...}, "save_result": false, "memory_key": ""}

    Returns:
        JSON 结果
    """
    try:
        _start_scheduler_if_needed()
        sched = _get_scheduler()
        params = json.loads(params_json) if params_json else {}
        if task_type not in ("news_fetch", "market_snapshot", "custom_call"):
            return json.dumps({"ok": False, "error": f"不支持的任务类型: {task_type}"}, ensure_ascii=False)
        task = sched.add_task(
            task_name=task_name,
            task_type=task_type,
            cron_expr=cron_expr,
            interval_minutes=interval_minutes,
            params=params,
            description=description,
        )
        return json.dumps({"ok": True, "task": task}, ensure_ascii=False)
    except Exception as e:
        return json.dumps({"ok": False, "error": f"{type(e).__name__}: {str(e)[:200]}"}, ensure_ascii=False)


@mcp.tool(description="删除定时任务")
def scheduler_remove(task_name: str) -> str:
    """删除一个定时任务。

    Args:
        task_name: 任务名称

    Returns:
        JSON 结果
    """
    try:
        sched = _get_scheduler()
        ok = sched.remove_task(task_name)
        return json.dumps({"ok": ok, "task_name": task_name}, ensure_ascii=False)
    except Exception as e:
        return json.dumps({"ok": False, "error": f"{type(e).__name__}: {str(e)[:200]}"}, ensure_ascii=False)


@mcp.tool(description="暂停定时任务")
def scheduler_pause(task_name: str) -> str:
    """暂停一个定时任务。

    Args:
        task_name: 任务名称

    Returns:
        JSON 结果
    """
    try:
        sched = _get_scheduler()
        ok = sched.pause_task(task_name)
        return json.dumps({"ok": ok, "task_name": task_name}, ensure_ascii=False)
    except Exception as e:
        return json.dumps({"ok": False, "error": f"{type(e).__name__}: {str(e)[:200]}"}, ensure_ascii=False)


@mcp.tool(description="恢复定时任务")
def scheduler_resume(task_name: str) -> str:
    """恢复一个已暂停的定时任务。

    Args:
        task_name: 任务名称

    Returns:
        JSON 结果
    """
    try:
        _start_scheduler_if_needed()
        sched = _get_scheduler()
        ok = sched.resume_task(task_name)
        return json.dumps({"ok": ok, "task_name": task_name}, ensure_ascii=False)
    except Exception as e:
        return json.dumps({"ok": False, "error": f"{type(e).__name__}: {str(e)[:200]}"}, ensure_ascii=False)


@mcp.tool(description="立即执行一次定时任务（手动触发）")
def scheduler_run_now(task_name: str) -> str:
    """立即手动执行一次任务。

    Args:
        task_name: 任务名称

    Returns:
        JSON 结果
    """
    try:
        sched = _get_scheduler()
        result = sched.run_task_now(task_name)
        return json.dumps(result, ensure_ascii=False)
    except Exception as e:
        return json.dumps({"ok": False, "error": f"{type(e).__name__}: {str(e)[:200]}"}, ensure_ascii=False)


@mcp.tool(description="查询任务执行日志")
def scheduler_logs(task_name: Optional[str] = None, limit: int = 50) -> str:
    """查询任务执行历史日志。

    Args:
        task_name: 按任务名过滤，可选
        limit: 返回条数，默认 50

    Returns:
        JSON 格式的日志列表
    """
    try:
        storage = _get_storage()
        logs = storage.query_task_logs(task_name=task_name, limit=limit)
        return json.dumps({"ok": True, "count": len(logs), "logs": logs}, ensure_ascii=False)
    except Exception as e:
        return json.dumps({"ok": False, "error": f"{type(e).__name__}: {str(e)[:200]}"}, ensure_ascii=False)


def _parse_args():
    """解析命令行参数。"""
    import argparse
    parser = argparse.ArgumentParser(
        description="AKShare MCP Server - 金融数据 MCP 服务器",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  python server.py                          # stdio 模式（默认，供 IDE 集成）
  python server.py --transport sse          # SSE 模式，默认 0.0.0.0:8000
  python server.py --transport sse --port 9000
  python server.py --transport streamable-http --host 127.0.0.1 --port 8080
  python server.py --list                   # 列出所有可用工具
        """,
    )
    parser.add_argument(
        "--transport", "-t",
        choices=["stdio", "sse", "streamable-http"],
        default="stdio",
        help="传输协议：stdio（默认）、sse、streamable-http",
    )
    parser.add_argument(
        "--host",
        default="0.0.0.0",
        help="监听地址，默认 0.0.0.0（所有网卡）",
    )
    parser.add_argument(
        "--port", "-p",
        type=int,
        default=8000,
        help="监听端口，默认 8000",
    )
    parser.add_argument(
        "--list", "-l",
        action="store_true",
        help="列出所有可用工具后退出",
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = _parse_args()

    if args.list:
        import asyncio
        async def _list():
            tools = await mcp.list_tools()
            print(f"=== AKShare MCP Server 共 {len(tools)} 个工具 ===")
            print()
            for t in tools:
                print(f"  {t.name}")
                if t.description:
                    print(f"    {t.description[:80]}")
                print()
        asyncio.run(_list())
        sys.exit(0)

    if args.transport == "stdio":
        mcp.run()
    else:
        # SSE 或 streamable-http 模式
        mcp.run(
            transport=args.transport,
            host=args.host,
            port=args.port,
        )
