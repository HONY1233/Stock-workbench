#!/usr/bin/env python3
"""财联社电报抓取工具。

使用 curl_cffi 模拟浏览器访问财联社电报API，无需签名验证。
数据仅供技术研究与学习使用，不构成投资建议。
"""
from __future__ import annotations

import json
import time
from typing import Optional


def fetch_cls_telegraph(
    limit: int = 20,
    keyword: Optional[str] = None,
    level: Optional[str] = None,
) -> dict:
    """获取财联社电报。

    Args:
        limit: 返回条数，默认 20 条
        keyword: 关键词过滤，可选
        level: 等级过滤，如 'A', 'B', 'C'，可选

    Returns:
        dict: 包含 ok/count/data 的结果
    """
    try:
        from curl_cffi import requests
    except ImportError:
        return {"ok": False, "error": "需要安装 curl_cffi: pip install curl_cffi"}

    base_url = "https://www.cls.cn"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124 Safari/537.36",
        "Referer": "https://www.cls.cn/telegraph",
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    }

    all_items = []
    last_time = None
    max_pages = 5

    try:
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
                    "reading_num": item.get("reading_num", 0),
                    "comment_num": item.get("comment_num", 0),
                    "share_num": item.get("share_num", 0),
                    "subjects": item.get("subjects", []),
                    "stock_list": item.get("stock_list", []),
                })

            if len(all_items) >= limit * 2:
                break

            if roll_data:
                last_time = roll_data[-1].get("ctime")
            else:
                break

            time.sleep(0.3)

    except Exception as e:
        if not all_items:
            return {"ok": False, "error": f"{type(e).__name__}: {str(e)[:200]}"}

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

    return {
        "ok": True,
        "source": "cls",
        "count": len(all_items),
        "data": all_items,
    }


if __name__ == "__main__":
    import sys

    limit = 20
    if len(sys.argv) > 1:
        try:
            limit = int(sys.argv[1])
        except ValueError:
            pass

    result = fetch_cls_telegraph(limit=limit)
    if result["ok"]:
        print(f"获取到 {result['count']} 条财联社电报")
        print()
        for i, item in enumerate(result["data"]):
            print(f"{i+1}. [{item['datetime']}] [级别:{item['level']}] {item['title']}")
            print(f"   {item['brief'][:80]}...")
            print(f"   阅读:{item['reading_num']} 评论:{item['comment_num']} 分享:{item['share_num']}")
            print()
    else:
        print("失败:", result.get("error"))
