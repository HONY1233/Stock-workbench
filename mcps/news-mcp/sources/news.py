"""新闻数据源：财联社电报、新闻联播、财经日历、全球新闻等。"""
from __future__ import annotations
import json
import time
from typing import Optional, Literal

from pydantic import BaseModel, Field, field_validator

import akshare as ak

from core.helpers import _df_to_records
from core.translate import (
    _translate_records, _has_english, _translate_en_to_zh, _FINANCIAL_DICT_EN_ZH,
)


_READ_ONLY = {"readOnlyHint": True}


class _ClsTelegraphInput(BaseModel):
    limit: int = Field(20, ge=1, le=500, description="返回条数")
    keyword: Optional[str] = Field(None, description="关键词过滤")
    level: Optional[str] = Field(None, description="级别过滤，如 A、B、C")
    red_only: bool = Field(False, description="是否只获取标红新闻")
    hours: Optional[float] = Field(None, ge=0, description="只返回最近 N 小时内的新闻")


class _NewsCctvInput(BaseModel):
    date: Optional[str] = Field(None, description="日期，格式 YYYYMMDD 或 YYYY-MM-DD")
    limit: int = Field(20, ge=1, le=500, description="返回条数")

    @field_validator("date")
    @classmethod
    def _clean_date(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        return v.replace("-", "")


class _NewsEconomicCalendarInput(BaseModel):
    limit: int = Field(50, ge=1, le=500, description="返回条数")


class _StockNewsInput(BaseModel):
    symbol: str = Field(..., description="股票代码，如 600519")
    limit: int = Field(20, ge=1, le=500, description="返回条数")

    @field_validator("symbol")
    @classmethod
    def _clean(cls, v: str) -> str:
        return v.replace("sh", "").replace("sz", "").replace(".SH", "").replace(".SZ", "")


class _GlobalNewsInput(BaseModel):
    source: Literal["em", "sina", "ths"] = Field("em", description="数据源：em(东方财富)、sina(新浪)、ths(同花顺)")
    limit: int = Field(20, ge=1, le=500, description="返回条数")
    translate: bool = Field(True, description="是否翻译英文内容为中文")


class _WallstreetNewsInput(BaseModel):
    limit: int = Field(30, ge=1, le=500, description="返回条数")
    translate: bool = Field(True, description="是否翻译英文事件名为中文")


class _FuturesNewsShmetInput(BaseModel):
    limit: int = Field(50, ge=1, le=500, description="返回条数")
    translate: bool = Field(True, description="是否翻译英文内容为中文")


def _translate_text(text: str) -> str:
    """将英文金融文本翻译为中文（内部辅助函数）。"""
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


def register(mcp) -> list[str]:
    """注册新闻类工具，返回工具名列表。"""

    @mcp.tool(
        name="cls_telegraph",
        description="获取财联社电报（7x24小时财经快讯），支持按时间范围、关键词、级别及标红过滤",
        annotations=_READ_ONLY,
    )
    def cls_telegraph(
        limit: int = 20,
        keyword: Optional[str] = None,
        level: Optional[str] = None,
        red_only: bool = False,
        hours: Optional[float] = None,
    ) -> str:
        try:
            params = _ClsTelegraphInput(
                limit=limit, keyword=keyword, level=level, red_only=red_only, hours=hours
            )
            try:
                from curl_cffi import requests
            except ImportError:
                return json.dumps({
                    "ok": False,
                    "data": [],
                    "count": 0,
                    "error": "需要安装 curl_cffi: pip install curl_cffi",
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
            max_pages = 10 if params.red_only else 5

            for page in range(max_pages):
                req_params = {
                    "app": "CailianpressWeb",
                    "os": "web",
                    "sv": "8.7.9",
                    "name": "telegraphList",
                }
                if last_time:
                    req_params["lastTime"] = str(last_time)

                r = requests.get(
                    f"{base_url}/api/cache",
                    params=req_params,
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

                if len(all_items) >= params.limit * 3:
                    break

                last_time = roll_data[-1].get("ctime")
                time.sleep(0.3)

            if params.red_only:
                all_items = [item for item in all_items if item["is_red"]]

            if params.hours:
                now = time.time()
                cutoff = now - params.hours * 3600
                all_items = [item for item in all_items if item.get("ctime", 0) >= cutoff]

            if params.keyword:
                kw = params.keyword.lower()
                all_items = [
                    item for item in all_items
                    if kw in item["title"].lower()
                    or kw in item["brief"].lower()
                    or kw in item["content"].lower()
                ]

            if params.level:
                all_items = [item for item in all_items if item["level"] == params.level.upper()]

            all_items = all_items[: params.limit]

            return json.dumps({
                "ok": True,
                "data": all_items,
                "count": len(all_items),
            }, ensure_ascii=False)
        except Exception as e:
            return json.dumps({
                "ok": False,
                "data": [],
                "count": 0,
                "error": f"{type(e).__name__}: {str(e)[:200]}",
            }, ensure_ascii=False)

    @mcp.tool(
        name="news_cctv",
        description="获取新闻联播文字稿",
        annotations=_READ_ONLY,
    )
    def news_cctv(date: Optional[str] = None, limit: int = 20) -> str:
        try:
            params = _NewsCctvInput(date=date, limit=limit)
            if params.date:
                df = ak.news_cctv(date=params.date)
            else:
                df = ak.news_cctv()
            data = _df_to_records(df, params.limit)
            return json.dumps({"ok": True, "data": data, "count": len(data)}, ensure_ascii=False)
        except Exception as e:
            return json.dumps({
                "ok": False,
                "data": [],
                "count": 0,
                "error": f"{type(e).__name__}: {str(e)[:200]}",
            }, ensure_ascii=False)

    @mcp.tool(
        name="news_economic_calendar",
        description="获取财经日历（全球财经事件日历）",
        annotations=_READ_ONLY,
    )
    def news_economic_calendar(limit: int = 50) -> str:
        try:
            params = _NewsEconomicCalendarInput(limit=limit)
            df = ak.news_economic_baidu()
            data = _df_to_records(df, params.limit)
            return json.dumps({"ok": True, "data": data, "count": len(data)}, ensure_ascii=False)
        except Exception as e:
            return json.dumps({
                "ok": False,
                "data": [],
                "count": 0,
                "error": f"{type(e).__name__}: {str(e)[:200]}",
            }, ensure_ascii=False)

    @mcp.tool(
        name="stock_news",
        description="获取个股相关新闻",
        annotations=_READ_ONLY,
    )
    def stock_news(symbol: str, limit: int = 20) -> str:
        try:
            params = _StockNewsInput(symbol=symbol, limit=limit)
            df = ak.stock_news_em(symbol=params.symbol)
            data = _df_to_records(df, params.limit)
            return json.dumps({"ok": True, "data": data, "count": len(data)}, ensure_ascii=False)
        except Exception as e:
            return json.dumps({
                "ok": False,
                "data": [],
                "count": 0,
                "error": f"{type(e).__name__}: {str(e)[:200]}",
            }, ensure_ascii=False)

    @mcp.tool(
        name="global_news",
        description="获取全球财经新闻（支持东方财富、新浪财经、同花顺数据源），自动翻译英文内容为中文",
        annotations=_READ_ONLY,
    )
    def global_news(
        source: Literal["em", "sina", "ths"] = "em",
        limit: int = 20,
        translate: bool = True,
    ) -> str:
        try:
            params = _GlobalNewsInput(source=source, limit=limit, translate=translate)
            if params.source == "em":
                df = ak.stock_info_global_em()
                fields = ["标题", "摘要"]
            elif params.source == "sina":
                df = ak.stock_info_global_sina()
                fields = ["内容"]
            else:
                df = ak.stock_info_global_ths()
                fields = ["标题", "内容"]
            data = _df_to_records(df, params.limit)
            data = _translate_records(data, fields=fields, translate=params.translate)
            return json.dumps({"ok": True, "data": data, "count": len(data)}, ensure_ascii=False)
        except Exception as e:
            return json.dumps({
                "ok": False,
                "data": [],
                "count": 0,
                "error": f"{type(e).__name__}: {str(e)[:200]}",
            }, ensure_ascii=False)

    @mcp.tool(
        name="wallstreet_news",
        description="获取华尔街见闻财经日历（全球宏观事件），自动翻译英文事件名为中文",
        annotations=_READ_ONLY,
    )
    def wallstreet_news(limit: int = 30, translate: bool = True) -> str:
        try:
            params = _WallstreetNewsInput(limit=limit, translate=translate)
            df = ak.macro_info_ws()
            data = _df_to_records(df, params.limit)
            data = _translate_records(data, fields=["事件", "地区"], translate=params.translate)
            return json.dumps({"ok": True, "data": data, "count": len(data)}, ensure_ascii=False)
        except Exception as e:
            return json.dumps({
                "ok": False,
                "data": [],
                "count": 0,
                "error": f"{type(e).__name__}: {str(e)[:200]}",
            }, ensure_ascii=False)

    @mcp.tool(
        name="futures_news_shmet",
        description="获取上海期货交易所新闻（期货市场要闻），自动翻译英文内容为中文",
        annotations=_READ_ONLY,
    )
    def futures_news_shmet(limit: int = 50, translate: bool = True) -> str:
        try:
            params = _FuturesNewsShmetInput(limit=limit, translate=translate)
            df = ak.futures_news_shmet()
            data = _df_to_records(df, params.limit)
            data = _translate_records(data, fields=["内容"], translate=params.translate)
            return json.dumps({"ok": True, "data": data, "count": len(data)}, ensure_ascii=False)
        except Exception as e:
            return json.dumps({
                "ok": False,
                "data": [],
                "count": 0,
                "error": f"{type(e).__name__}: {str(e)[:200]}",
            }, ensure_ascii=False)

    return [
        "cls_telegraph",
        "news_cctv",
        "news_economic_calendar",
        "stock_news",
        "global_news",
        "wallstreet_news",
        "futures_news_shmet",
    ]
