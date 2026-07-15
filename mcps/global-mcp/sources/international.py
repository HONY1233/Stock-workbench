"""国际新闻数据源：Reuters、Bloomberg 财经新闻。"""
from __future__ import annotations
import json
from typing import Optional

from pydantic import BaseModel, Field

import akshare as ak

from core.helpers import _df_to_records
from core.translate import _translate_records


_READ_ONLY = {"readOnlyHint": True}


class _ReutersNewsInput(BaseModel):
    limit: int = Field(default=30, ge=1, description="返回条数，默认 30 条")
    translate: bool = Field(default=True, description="是否将英文内容翻译为中文，默认 True")


class _BloombergNewsInput(BaseModel):
    limit: int = Field(default=30, ge=1, description="返回条数，默认 30 条")
    translate: bool = Field(default=True, description="是否将英文内容翻译为中文，默认 True")


class _BloombergBillionairesInput(BaseModel):
    limit: int = Field(default=50, ge=1, description="返回条数，默认 50 条")


class _GlobalNewsSearchInput(BaseModel):
    keyword: str = Field(..., description="搜索关键词")
    limit: int = Field(default=30, ge=1, description="返回条数，默认 30 条")
    translate: bool = Field(default=True, description="是否翻译英文内容，默认 True")


def register(mcp) -> list[str]:
    """注册国际新闻工具，返回工具名列表。"""

    @mcp.tool(
        name="reuters_news",
        description="获取路透社(Reuters)相关财经新闻，自动翻译英文内容为中文",
        annotations=_READ_ONLY,
    )
    def reuters_news(limit: int = 30, translate: bool = True) -> str:
        try:
            params = _ReutersNewsInput(limit=limit, translate=translate)
            data = []

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
                            for entry in feed.entries[:params.limit]:
                                item = {
                                    "标题": entry.get("title", ""),
                                    "摘要": entry.get("summary", "")[:200] if entry.get("summary") else "",
                                    "发布时间": entry.get("published", ""),
                                    "链接": entry.get("link", ""),
                                    "来源": "Reuters",
                                }
                                data.append(item)
                            if data:
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
                            if len(data) >= params.limit:
                                break
                        if len(data) >= params.limit:
                            break
                    except Exception:
                        continue

            if not data:
                # Fallback：返回全球新闻概览
                try:
                    df = ak.stock_info_global_em()
                    for _, row in df.head(params.limit).iterrows():
                        data.append({
                            "标题": str(row.get("标题", ""))[:100],
                            "摘要": str(row.get("摘要", ""))[:200],
                            "发布时间": str(row.get("发布时间", "")),
                            "链接": str(row.get("链接", "")),
                            "来源": "东方财富-全球新闻",
                        })
                except Exception:
                    return json.dumps({
                        "ok": False,
                        "data": [],
                        "count": 0,
                        "error": "未获取到路透社相关新闻，可能是网络限制或暂无相关内容",
                    }, ensure_ascii=False)

            data = _translate_records(data, fields=["标题", "摘要"], translate=params.translate)
            if len(data) > params.limit:
                data = data[:params.limit]

            return json.dumps({
                "ok": True,
                "data": data,
                "count": len(data),
            }, ensure_ascii=False)
        except Exception as e:
            return json.dumps({
                "ok": False,
                "data": [],
                "count": 0,
                "error": f"{type(e).__name__}: {str(e)[:200]}",
            }, ensure_ascii=False)

    @mcp.tool(
        name="bloomberg_news",
        description="获取彭博社(Bloomberg)相关财经新闻，自动翻译英文内容为中文",
        annotations=_READ_ONLY,
    )
    def bloomberg_news(limit: int = 30, translate: bool = True) -> str:
        try:
            params = _BloombergNewsInput(limit=limit, translate=translate)
            data = []

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
                            for entry in feed.entries[:params.limit]:
                                item = {
                                    "标题": entry.get("title", ""),
                                    "摘要": entry.get("summary", "")[:200] if entry.get("summary") else "",
                                    "发布时间": entry.get("published", ""),
                                    "链接": entry.get("link", ""),
                                    "来源": "Bloomberg",
                                }
                                data.append(item)
                            if data:
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
                            if len(data) >= params.limit:
                                break
                        if len(data) >= params.limit:
                            break
                    except Exception:
                        continue

            if not data:
                # Fallback：返回全球新闻概览
                try:
                    df = ak.stock_info_global_em()
                    for _, row in df.head(params.limit).iterrows():
                        data.append({
                            "标题": str(row.get("标题", ""))[:100],
                            "摘要": str(row.get("摘要", ""))[:200],
                            "发布时间": str(row.get("发布时间", "")),
                            "链接": str(row.get("链接", "")),
                            "来源": "东方财富-全球新闻",
                        })
                except Exception:
                    return json.dumps({
                        "ok": False,
                        "data": [],
                        "count": 0,
                        "error": "未获取到彭博社相关新闻，可能是网络限制或暂无相关内容",
                    }, ensure_ascii=False)

            data = _translate_records(data, fields=["标题", "摘要"], translate=params.translate)
            if len(data) > params.limit:
                data = data[:params.limit]

            return json.dumps({
                "ok": True,
                "data": data,
                "count": len(data),
            }, ensure_ascii=False)
        except Exception as e:
            return json.dumps({
                "ok": False,
                "data": [],
                "count": 0,
                "error": f"{type(e).__name__}: {str(e)[:200]}",
            }, ensure_ascii=False)

    @mcp.tool(
        name="bloomberg_billionaires",
        description="获取彭博亿万富豪榜(Bloomberg Billionaires Index)",
        annotations=_READ_ONLY,
    )
    def bloomberg_billionaires(limit: int = 50) -> str:
        try:
            params = _BloombergBillionairesInput(limit=limit)
            df = ak.index_bloomberg_billionaires()
            if df is None or df.empty:
                return json.dumps({
                    "ok": True,
                    "data": [],
                    "count": 0,
                }, ensure_ascii=False)

            data = _df_to_records(df, params.limit)
            return json.dumps({
                "ok": True,
                "data": data,
                "count": len(data),
            }, ensure_ascii=False)
        except Exception as e:
            return json.dumps({
                "ok": False,
                "data": [],
                "count": 0,
                "error": f"{type(e).__name__}: {str(e)[:200]}",
            }, ensure_ascii=False)

    @mcp.tool(
        name="global_news_search",
        description="搜索全球财经新闻（支持 Reuters/Bloomberg 等关键词筛选）",
        annotations=_READ_ONLY,
    )
    def global_news_search(
        keyword: str,
        limit: int = 30,
        translate: bool = True,
    ) -> str:
        try:
            params = _GlobalNewsSearchInput(keyword=keyword, limit=limit, translate=translate)
            if not params.keyword.strip():
                return json.dumps({
                    "ok": False,
                    "data": [],
                    "count": 0,
                    "error": "keyword 不能为空",
                }, ensure_ascii=False)

            data = []
            sources = [
                ("东方财富", ak.stock_info_global_em, ["标题", "摘要"]),
                ("新浪", ak.stock_info_global_sina, ["内容"]),
                ("同花顺", ak.stock_info_global_ths, ["标题", "内容"]),
                ("华尔街见闻", ak.macro_info_ws, ["事件", "地区"]),
            ]

            kw_lower = params.keyword.lower()
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
                        if len(data) >= params.limit:
                            break
                    if len(data) >= params.limit:
                        break
                except Exception:
                    continue

            if not data:
                return json.dumps({
                    "ok": False,
                    "data": [],
                    "count": 0,
                    "error": f"未搜索到包含关键词 '{params.keyword}' 的新闻",
                }, ensure_ascii=False)

            data = _translate_records(data, fields=["标题", "摘要"], translate=params.translate)

            return json.dumps({
                "ok": True,
                "data": data,
                "count": len(data),
            }, ensure_ascii=False)
        except Exception as e:
            return json.dumps({
                "ok": False,
                "data": [],
                "count": 0,
                "error": f"{type(e).__name__}: {str(e)[:200]}",
            }, ensure_ascii=False)

    return ["reuters_news", "bloomberg_news", "bloomberg_billionaires", "global_news_search"]
