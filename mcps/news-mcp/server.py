#!/usr/bin/env python3
"""news-mcp - 金融数据 MCP 服务器。

数据来自公开数据源，仅供技术研究与学习使用，不构成投资建议。
"""
from __future__ import annotations

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

from core.registry import SourceRegistry

mcp = FastMCP("news-mcp")
_READ_ONLY = {"readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": True}

_registry = SourceRegistry()
_registry.register_auto_tools(mcp)


# 加载自定义源
from sources.news import register as register_news

_ = register_news(mcp)



def _parse_args():
    import argparse
    parser = argparse.ArgumentParser(
        description="news-mcp MCP Server",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  python server.py
  python server.py --transport sse
  python server.py --list
        """,
    )
    parser.add_argument("--transport", "-t", choices=["stdio", "sse", "streamable-http"], default="stdio", help="传输协议")
    parser.add_argument("--host", default="0.0.0.0", help="监听地址")
    parser.add_argument("--port", "-p", type=int, default=8002, help="监听端口")
    parser.add_argument("--list", "-l", action="store_true", help="列出所有可用工具后退出")
    return parser.parse_args()


if __name__ == "__main__":
    args = _parse_args()

    if args.list:
        import asyncio
        async def _list():
            tools = await mcp.list_tools()
            print(f"=== news-mcp 共 {len(tools)} 个工具 ===")
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
        mcp.run(transport=args.transport, host=args.host, port=args.port)
