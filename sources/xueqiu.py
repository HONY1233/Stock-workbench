"""雪球网数据源：热帖、个股讨论、帖子评论。

需要设置环境变量 XUEQIU_TOKEN，值为从雪球浏览器 cookie 中获取的 xq_a_token。
获取方式：登录 xueqiu.com，F12 -> Application -> Cookies -> 复制 xq_a_token 的值。

接口：
  - 热门动态：/v4/statuses/public_timeline_by_category.json
  - 个股讨论：/v4/statuses/public_timeline_by_symbol.json
  - 帖子评论：/statuses/comments.json
"""
from __future__ import annotations
import json
import os
import re

from pydantic import BaseModel, Field

XQ_BASE = "https://xueqiu.com"
XQ_API = "https://xueqiu.com/v4/statuses"
XQ_COMMENT_API = "https://xueqiu.com/statuses"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Referer": "https://xueqiu.com/",
    "Accept": "application/json, text/plain, */*",
}

# 分类映射
CATEGORY_MAP = {
    "全部": -1,
    "沪深": 6,
    "港美股": 105,
    "基金": 104,
    "房产": 111,
    "港股": 102,
    "美股": 101,
    "私募": 113,
    "保险": 114,
}

_READ_ONLY = {"readOnlyHint": True}


class _XueqiuHotPostsInput(BaseModel):
    category: str = Field("全部", description="分类：全部、沪深、港美股、基金、房产、港股、美股、私募、保险")
    count: int = Field(20, ge=1, le=500, description="返回条数，默认 20")
    max_id: int = Field(-1, description="翻页游标，-1 表示第一页")


class _XueqiuStockPostsInput(BaseModel):
    symbol: str = Field("SH600519", description="股票代码，雪球格式 SH600519 / SZ000001")
    count: int = Field(20, ge=1, le=500, description="返回条数，默认 20")
    max_id: int = Field(-1, description="翻页游标，-1 表示第一页")


class _XueqiuCommentsInput(BaseModel):
    post_id: str = Field("", description="帖子ID（从热帖或个股讨论接口返回的 id 字段）")
    count: int = Field(20, ge=1, le=500, description="每页条数，默认 20")
    page: int = Field(1, ge=1, description="页码，默认 1")


class _XueqiuStatusInput(BaseModel):
    pass


def _get_session():
    """获取带 cookie 的 session。"""
    try:
        from curl_cffi import requests
    except ImportError:
        import requests

    token = os.environ.get("XUEQIU_TOKEN", "").strip()
    if not token:
        return None, "未设置 XUEQIU_TOKEN 环境变量"

    # 构造 cookie
    try:
        resp = requests.get(XQ_BASE, headers=HEADERS, timeout=15)
        cookies = dict(resp.cookies) if hasattr(resp, "cookies") else {}
        cookies["xq_a_token"] = token
        return requests, cookies
    except Exception:
        return requests, {"xq_a_token": token}


def _clean_html(text: str) -> str:
    """清理 HTML 标签。"""
    if not text:
        return ""
    text = re.sub(r"<[^>]+>", "", text)
    text = text.replace("&nbsp;", " ").replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">").replace("&quot;", '"')
    return text.strip()


def _normalize_item(item: dict) -> dict:
    """标准化帖子字段。"""
    if not isinstance(item, dict):
        return {}
    if "data" in item and isinstance(item["data"], dict):
        item = item["data"]
    user = item.get("user", {}) or {}
    return {
        "id": item.get("id"),
        "user_id": user.get("id"),
        "用户名": user.get("screen_name", ""),
        "头像": user.get("profile_image_url", ""),
        "粉丝数": user.get("followers_count", 0),
        "标题": _clean_html(item.get("title", "")),
        "正文": _clean_html(item.get("text", "")),
        "摘要": _clean_html(item.get("description", "")),
        "目标股票": item.get("target", ""),
        "评论数": item.get("reply_count", 0),
        "转发数": item.get("retweet_count", 0),
        "点赞数": item.get("like_count", 0),
        "收藏数": item.get("fav_count", 0),
        "发布时间": item.get("created_at", ""),
        "来源": "雪球",
    }


def _normalize_comment(c: dict) -> dict:
    """标准化评论字段。"""
    if not isinstance(c, dict):
        return {}
    user = c.get("user", {}) or {}
    return {
        "id": c.get("id"),
        "user_id": user.get("id"),
        "用户名": user.get("screen_name", ""),
        "头像": user.get("profile_image_url", ""),
        "内容": _clean_html(c.get("text", "")),
        "点赞数": c.get("like_count", 0),
        "发布时间": c.get("created_at", ""),
        "来源": "雪球",
    }


def register(mcp) -> list[str]:
    """注册雪球相关 MCP 工具。"""

    @mcp.tool(
        name="xueqiu_hot_posts",
        description="雪球热门动态：全平台/各分类热帖排行，需设置 XUEQIU_TOKEN 环境变量",
        annotations=_READ_ONLY,
    )
    def xueqiu_hot_posts(
        category: str = "全部",
        count: int = 20,
        max_id: int = -1,
    ) -> str:
        try:
            params = _XueqiuHotPostsInput(category=category, count=count, max_id=max_id)
            requests, cookies = _get_session()
            if requests is None:
                return json.dumps(
                    {"ok": False, "data": [], "count": 0, "error": cookies},
                    ensure_ascii=False,
                )

            cat = CATEGORY_MAP.get(params.category, -1)
            url = f"{XQ_API}/public_timeline_by_category.json"
            req_params = {
                "since_id": -1,
                "max_id": params.max_id,
                "count": params.count,
                "category": cat,
            }
            resp = requests.get(url, headers=HEADERS, cookies=cookies, params=req_params, timeout=15)
            data = resp.json()

            if isinstance(data, dict) and data.get("error_code") and data["error_code"] != 0:
                return json.dumps(
                    {
                        "ok": False,
                        "data": [],
                        "count": 0,
                        "error": f"雪球API错误: {data.get('error_description', data['error_code'])}",
                    },
                    ensure_ascii=False,
                )

            items = data.get("list", []) if isinstance(data, dict) else []
            results = [_normalize_item(item) for item in items]
            results = [r for r in results if r.get("id")]

            return json.dumps(
                {"ok": True, "data": results, "count": len(results)},
                ensure_ascii=False,
            )
        except Exception as e:
            return json.dumps(
                {"ok": False, "data": [], "count": 0, "error": f"{type(e).__name__}: {str(e)[:200]}"},
                ensure_ascii=False,
            )

    @mcp.tool(
        name="xueqiu_stock_posts",
        description="雪球个股讨论：某只股票的用户发帖讨论，需设置 XUEQIU_TOKEN 环境变量",
        annotations=_READ_ONLY,
    )
    def xueqiu_stock_posts(
        symbol: str = "SH600519",
        count: int = 20,
        max_id: int = -1,
    ) -> str:
        try:
            params = _XueqiuStockPostsInput(symbol=symbol, count=count, max_id=max_id)
            requests, cookies = _get_session()
            if requests is None:
                return json.dumps(
                    {"ok": False, "data": [], "count": 0, "error": cookies},
                    ensure_ascii=False,
                )

            # 转换代码格式
            s = params.symbol.upper().strip()
            if not s.startswith("SH") and not s.startswith("SZ") and not s.startswith("HK"):
                if len(s) == 6:
                    if s[0] in ("6", "9") or s[:2] in ("68", "90"):
                        s = "SH" + s
                    else:
                        s = "SZ" + s

            url = f"{XQ_API}/public_timeline_by_symbol.json"
            req_params = {
                "symbol": s,
                "since_id": -1,
                "max_id": params.max_id,
                "count": params.count,
            }
            resp = requests.get(url, headers=HEADERS, cookies=cookies, params=req_params, timeout=15)
            data = resp.json()

            if isinstance(data, dict) and data.get("error_code") and data["error_code"] != 0:
                return json.dumps(
                    {
                        "ok": False,
                        "data": [],
                        "count": 0,
                        "error": f"雪球API错误: {data.get('error_description', data['error_code'])}",
                    },
                    ensure_ascii=False,
                )

            items = data.get("list", []) if isinstance(data, dict) else []
            results = [_normalize_item(item) for item in items]
            results = [r for r in results if r.get("id")]

            return json.dumps(
                {"ok": True, "data": results, "count": len(results)},
                ensure_ascii=False,
            )
        except Exception as e:
            return json.dumps(
                {"ok": False, "data": [], "count": 0, "error": f"{type(e).__name__}: {str(e)[:200]}"},
                ensure_ascii=False,
            )

    @mcp.tool(
        name="xueqiu_comments",
        description="雪球帖子评论：获取某条帖子的用户评论，需设置 XUEQIU_TOKEN 环境变量",
        annotations=_READ_ONLY,
    )
    def xueqiu_comments(
        post_id: str = "",
        count: int = 20,
        page: int = 1,
    ) -> str:
        try:
            params = _XueqiuCommentsInput(post_id=post_id, count=count, page=page)
            if not params.post_id:
                return json.dumps(
                    {"ok": False, "data": [], "count": 0, "error": "缺少 post_id 参数"},
                    ensure_ascii=False,
                )

            requests, cookies = _get_session()
            if requests is None:
                return json.dumps(
                    {"ok": False, "data": [], "count": 0, "error": cookies},
                    ensure_ascii=False,
                )

            url = f"{XQ_COMMENT_API}/comments.json"
            req_params = {
                "id": params.post_id,
                "count": params.count,
                "page": params.page,
                "type": "status",
            }
            resp = requests.get(url, headers=HEADERS, cookies=cookies, params=req_params, timeout=15)
            data = resp.json()

            if isinstance(data, dict) and data.get("error_code") and data["error_code"] != 0:
                return json.dumps(
                    {
                        "ok": False,
                        "data": [],
                        "count": 0,
                        "error": f"雪球API错误: {data.get('error_description', data['error_code'])}",
                    },
                    ensure_ascii=False,
                )

            comments = data.get("comments", []) if isinstance(data, dict) else []
            results = [_normalize_comment(c) for c in comments]
            results = [r for r in results if r.get("id")]

            return json.dumps(
                {"ok": True, "data": results, "count": len(results)},
                ensure_ascii=False,
            )
        except Exception as e:
            return json.dumps(
                {"ok": False, "data": [], "count": 0, "error": f"{type(e).__name__}: {str(e)[:200]}"},
                ensure_ascii=False,
            )

    @mcp.tool(
        name="xueqiu_status",
        description="检查雪球 token 配置状态及有效性",
        annotations=_READ_ONLY,
    )
    def xueqiu_status() -> str:
        try:
            _ = _XueqiuStatusInput()
            token = os.environ.get("XUEQIU_TOKEN", "")
            if not token:
                data = [
                    {
                        "configured": False,
                        "valid": False,
                        "message": "未设置 XUEQIU_TOKEN 环境变量",
                        "how_to": "登录 xueqiu.com → F12 → Application → Cookies → 复制 xq_a_token 值 → 设置环境变量 XUEQIU_TOKEN",
                    }
                ]
                return json.dumps(
                    {"ok": True, "data": data, "count": len(data)},
                    ensure_ascii=False,
                )

            requests, cookies = _get_session()
            if requests is None:
                data = [{"configured": True, "valid": False, "message": cookies}]
                return json.dumps(
                    {"ok": True, "data": data, "count": len(data)},
                    ensure_ascii=False,
                )

            url = f"{XQ_API}/public_timeline_by_category.json"
            resp = requests.get(
                url,
                headers=HEADERS,
                cookies=cookies,
                params={"since_id": -1, "max_id": -1, "count": 1, "category": -1},
                timeout=15,
            )
            data = resp.json()
            if isinstance(data, dict) and data.get("error_code") and data["error_code"] != 0:
                result_data = [
                    {
                        "configured": True,
                        "valid": False,
                        "message": f"token无效: {data.get('error_description', data['error_code'])}",
                    }
                ]
                return json.dumps(
                    {"ok": True, "data": result_data, "count": len(result_data)},
                    ensure_ascii=False,
                )

            count = len(data.get("list", [])) if isinstance(data, dict) else 0
            result_data = [
                {
                    "configured": True,
                    "valid": True,
                    "message": f"token有效，成功获取 {count} 条热门动态",
                }
            ]
            return json.dumps(
                {"ok": True, "data": result_data, "count": len(result_data)},
                ensure_ascii=False,
            )
        except Exception as e:
            return json.dumps(
                {"ok": False, "data": [], "count": 0, "error": f"{type(e).__name__}: {str(e)[:200]}"},
                ensure_ascii=False,
            )

    return ["xueqiu_hot_posts", "xueqiu_stock_posts", "xueqiu_comments", "xueqiu_status"]
