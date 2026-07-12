"""新闻数据源：财联社电报、新闻联播、财经日历、全球新闻等。"""
from __future__ import annotations
import json
import time
from typing import Optional

import akshare as ak

from core.helpers import _df_to_records
from core.translate import (
    _translate_records, _has_english, _translate_en_to_zh, _FINANCIAL_DICT_EN_ZH,
)


def register(mcp) -> list[str]:
    """注册新闻类工具，返回工具名列表。"""

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

    return ["cls_telegraph", "news_cctv", "news_economic_calendar", "stock_news",
            "global_news_em", "global_news_sina", "global_news_ths",
            "wallstreet_news", "futures_news_shmet", "stock_us_news", "translate_text"]
