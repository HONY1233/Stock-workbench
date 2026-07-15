#!/usr/bin/env python3
"""AKShare MCP Server - 金融数据 MCP 服务器。

提供A股、指数等金融数据查询工具，数据来自公开数据源（新浪财经等）。
仅供技术研究与学习使用，不构成投资建议。

架构（解耦设计）：
  data_sources.yaml   — 数据源配置（增删源只改 YAML，不动代码）
  core/registry.py    — SourceRegistry，从 YAML 自动注册 MCP 工具
  sources/            — 自定义复杂源模块（财联社电报、Reuters 等）
  server.py           — 瘦入口：初始化 + 加载源 + 调度/存储管理

L0-L3 等级制度：
  L0 核心层  — 本地可用，无网络依赖
  L1 稳定层  — akshare 稳定 API + 腾讯直连
  L2 限流层  — 东财 datacenter/push2
  L3 受限层  — 国际源 Reuters/Bloomberg
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

from pydantic import BaseModel, Field

from core.helpers import _df_to_records
from core.tiers import Tier, TOOL_TIERS, tier_info
from core.registry import SourceRegistry, load_custom_sources, call_unified
from core.translate import _translate_records

mcp = FastMCP("akshare")
_READ_ONLY = {"readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": True}

# ── 加载数据源 ──────────────────────────────────────────
# 1. 从 YAML 配置自动注册简单源
_registry = SourceRegistry()
_registry.register_auto_tools(mcp)

# 2. 加载 sources/ 目录下的自定义复杂源
_custom_tools = load_custom_sources(mcp)


# ── 统一数据查询接口 ──────────────────────────────────────────

class _DataQueryInput(BaseModel):
    interface: str = Field(..., description="接口名称（统一别名、axdata接口名或akshare函数名），如 stock_daily、limit_up_pool")
    params_json: Optional[str] = Field(None, description="JSON 格式的参数字典，如 '{\"symbol\": \"600519\"}'")
    limit: int = Field(0, ge=0, le=1000, description="返回条数限制，0=不限")
    translate: bool = Field(True, description="是否翻译英文内容")
    source_preference: str = Field("any", description="数据源偏好：any(自动)、axdata_only、akshare_only、或提供商名如 sina/eastmoney/cls")


@mcp.tool(
    name="data_query",
    description="统一数据查询接口：整合 akshare + axdata，自动路由，支持按来源偏好按需调用",
    annotations=_READ_ONLY,
)
def data_query(
    interface: str,
    params_json: Optional[str] = None,
    limit: int = 0,
    translate: bool = True,
    source_preference: str = "any",
) -> str:
    """统一数据查询入口。整合 akshare 和 axdata，自动路由到最佳来源。

    支持通过 source_preference 按需指定数据来源，避免全部跑一遍：
    - "any" — 自动路由（axdata 优先，akshare fallback）
    - "axdata_only" — 只调 axdata
    - "akshare_only" — 只调 akshare
    - "sina"/"eastmoney"/"cls" 等 — 只调该数据商的接口

    三种调用方式：
    1. 统一别名：stock_daily、limit_up_pool、cls_market_emotion
    2. axdata 原始接口名：eastmoney_limit_up_pool
    3. akshare 函数名：stock_zh_a_daily

    Returns:
        JSON: {"ok": true/false, "data": [...], "count": N, "source": "...", "translated": true/false}
    """
    try:
        params = _DataQueryInput(
            interface=interface, params_json=params_json, limit=limit,
            translate=translate, source_preference=source_preference,
        )
        call_params = json.loads(params.params_json) if params.params_json else {}
        ok, data, source = call_unified(
            params.interface, _registry.sources, source_preference=params.source_preference, **call_params
        )

        if not ok:
            err = data[0].get("error", "未知错误") if data else "未知错误"
            return json.dumps({"ok": False, "data": [], "count": 0, "source": source, "error": err}, ensure_ascii=False)

        if params.limit and len(data) > params.limit:
            data = data[:params.limit]

        translated = False
        if params.translate and data:
            cfg = _registry.sources.get(params.interface)
            if cfg:
                tfields = set()
                for src_key in ("axdata", "akshare"):
                    src_cfg = cfg.get(src_key)
                    if src_cfg and src_cfg.get("translate_fields"):
                        tfields.update(src_cfg["translate_fields"])
                if tfields:
                    _translate_records(data, fields=tfields, translate=True)
                    translated = True

        return json.dumps({
            "ok": True, "interface": params.interface, "source": source,
            "count": len(data), "translated": translated, "data": data,
        }, ensure_ascii=False)
    except Exception as e:
        return json.dumps({"ok": False, "data": [], "count": 0, "error": f"{type(e).__name__}: {str(e)[:200]}"}, ensure_ascii=False)


@mcp.tool(
    name="data_interfaces",
    description="列出所有可用的统一数据接口及其描述、数据源配置",
    annotations=_READ_ONLY,
)
def data_interfaces() -> str:
    """列出 YAML 配置中所有可用的统一数据接口。"""
    interfaces = []
    for alias, cfg in _registry.sources.items():
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
        "ok": True, "count": len(interfaces),
        "note": "data_query 支持用 alias、axdata_interface 或 akshare_function 调用",
        "interfaces": interfaces,
    }, ensure_ascii=False)


@mcp.tool(
    name="list_interfaces_by_source",
    description="按数据来源提供商分类列出 YAML 配置的接口",
    annotations=_READ_ONLY,
)
def list_interfaces_by_source(provider: str = "") -> str:
    """按数据来源提供商分类列出接口。provider 为空则返回所有提供商汇总。"""
    try:
        if not provider:
            all_providers = _registry.get_providers()
            summary = {}
            for p in sorted(all_providers):
                yaml_tools = list(_registry.list_by_provider(p).keys())
                summary[p] = {"yaml_interfaces": yaml_tools, "count": len(yaml_tools)}
            return json.dumps({"ok": True, "count": len(summary), "by_provider": summary}, ensure_ascii=False)

        provider_lower = provider.lower()
        yaml_interfaces = _registry.list_by_provider(provider_lower)
        yaml_detail = []
        for alias, cfg in yaml_interfaces.items():
            yaml_detail.append({
                "alias": alias, "description": cfg.get("desc", ""),
                "axdata_interface": cfg.get("axdata", {}).get("interface") if cfg.get("axdata") else None,
                "akshare_function": cfg.get("akshare", {}).get("func") if cfg.get("akshare") else None,
            })
        return json.dumps({
            "ok": True, "provider": provider,
            "yaml_interfaces": yaml_detail, "count": len(yaml_detail),
        }, ensure_ascii=False)
    except Exception as e:
        return json.dumps({"ok": False, "error": f"{type(e).__name__}: {str(e)[:200]}"}, ensure_ascii=False)


@mcp.tool(
    name="tool_tier_info",
    description="查询工具的数据源等级（L0-L3）和兜底链路",
    annotations=_READ_ONLY,
)
def tool_tier_info(tool_name: str = "") -> str:
    """查询工具的 L0-L3 等级和兜底信息。传入 tool_name 查单个，否则列出所有。"""
    if tool_name:
        info = tier_info(tool_name)
        return json.dumps({
            "ok": True,
            "tool": tool_name,
            "tier": info["tier_name"],
            "fallback_chain": info["fallback"],
        }, ensure_ascii=False)

    result = {}
    for name in sorted(TOOL_TIERS.keys()):
        info = tier_info(name)
        result[name] = {"tier": info["tier_name"], "fallback": info["fallback"]}
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


@mcp.tool(
    name="reload_sources",
    description="重新加载数据源配置（热更新，无需重启服务）",
    annotations={"readOnlyHint": False, "destructiveHint": False, "idempotentHint": True, "openWorldHint": False},
)
def reload_sources() -> str:
    """重新加载 data_sources.yaml 配置文件。修改 YAML 后调用即可热更新。"""
    try:
        _registry.reload()
        sources = _registry.list_sources()
        return json.dumps({
            "ok": True,
            "message": "配置已重新加载",
            "source_count": len(sources),
            "sources": sources,
        }, ensure_ascii=False)
    except Exception as e:
        return json.dumps({"ok": False, "error": f"{type(e).__name__}: {str(e)[:200]}"}, ensure_ascii=False)


# ==================== 调度 / 存储 / 记忆 管理模块 ====================

_storage = None
_dedup = None
_scheduler = None
_pusher = None


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


def _get_pusher():
    """获取或初始化 WebSocket 推送服务。"""
    global _pusher
    if _pusher is None:
        import os
        from core.ws_pusher import WSPusher
        ws_host = os.environ.get("WS_HOST", "0.0.0.0")
        ws_port = int(os.environ.get("WS_PORT", "8001"))
        _pusher = WSPusher(host=ws_host, port=ws_port)
        _pusher.start_in_thread()
    return _pusher


def _get_tool_registry():
    """构造工具名 -> 函数 的注册表（供调度器调用）。

    从 FastMCP 的 _local_provider._components 中提取所有工具的原始函数引用，
    这样包含了 sources/ 模块注册的所有自定义工具。
    """
    registry = {}
    # 从 FastMCP 内部获取所有工具函数
    try:
        comps = mcp._local_provider._components
        for key, tool in comps.items():
            if key.startswith("tool:") and hasattr(tool, "fn"):
                # 键格式: tool:{name}@
                name = key.split(":", 1)[1].rstrip("@")
                fn = tool.fn
                if callable(fn):
                    registry[name] = fn
    except Exception:
        pass

    # 兜底：扫描 server.py 全局函数
    import inspect
    for name, obj in list(globals().items()):
        if callable(obj) and not name.startswith("_") and name != "mcp":
            if name not in registry:
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
        pusher = _get_pusher()
        _scheduler = TaskScheduler(
            storage=storage, dedup=dedup,
            tool_registry=registry, pusher=pusher,
        )
    return _scheduler


def _start_scheduler_if_needed():
    """如果尚未启动则启动调度器。"""
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

@mcp.tool(name="memory_stats", description="查询存储统计：新闻数、行情快照数、记忆数、调度任务数", annotations=_READ_ONLY)
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


@mcp.tool(name="memory_query_news", description="查询历史新闻数据，支持按来源/关键词过滤", annotations=_READ_ONLY)
def memory_query_news(source: Optional[str] = None, keyword: Optional[str] = None,
                      limit: int = 50, offset: int = 0) -> str:
    """从 SQLite 查询已保存的历史新闻数据。

    Args:
        source: 数据源过滤，如 cls_telegraph, global_news_em
        keyword: 关键词搜索
        limit: 返回条数，默认 50
        offset: 分页偏移
    """
    try:
        storage = _get_storage()
        data = storage.query_news(source=source, keyword=keyword, limit=limit, offset=offset)
        return json.dumps({"ok": True, "source": source or "all", "count": len(data), "offset": offset, "data": data}, ensure_ascii=False)
    except Exception as e:
        return json.dumps({"ok": False, "error": f"{type(e).__name__}: {str(e)[:200]}"}, ensure_ascii=False)


@mcp.tool(name="memory_set", description="写入通用记忆（key-value），供 agent 长期保存信息", annotations={"readOnlyHint": False, "destructiveHint": False, "idempotentHint": True, "openWorldHint": False})
def memory_set(key: str, value: str, tags: str = "") -> str:
    """写入一条通用记忆。

    Args:
        key: 记忆键（唯一）
        value: 记忆值
        tags: 标签（逗号分隔）
    """
    try:
        storage = _get_storage()
        storage.set_memory(key=key, value=value, tags=tags)
        return json.dumps({"ok": True, "key": key, "message": "已保存"}, ensure_ascii=False)
    except Exception as e:
        return json.dumps({"ok": False, "error": f"{type(e).__name__}: {str(e)[:200]}"}, ensure_ascii=False)


@mcp.tool(name="memory_get", description="读取通用记忆", annotations=_READ_ONLY)
def memory_get(key: str) -> str:
    """读取一条通用记忆。

    Args:
        key: 记忆键
    """
    try:
        storage = _get_storage()
        value = storage.get_memory(key)
        if value is None:
            return json.dumps({"ok": False, "key": key, "error": "未找到"}, ensure_ascii=False)
        return json.dumps({"ok": True, "key": key, "value": value}, ensure_ascii=False)
    except Exception as e:
        return json.dumps({"ok": False, "error": f"{type(e).__name__}: {str(e)[:200]}"}, ensure_ascii=False)


@mcp.tool(name="memory_search", description="搜索通用记忆，支持关键词和标签过滤", annotations=_READ_ONLY)
def memory_search(keyword: str = "", tag: str = "", limit: int = 50) -> str:
    """搜索通用记忆。

    Args:
        keyword: 关键词（匹配 key 和 value）
        tag: 标签过滤
        limit: 返回条数
    """
    try:
        storage = _get_storage()
        data = storage.search_memory(keyword=keyword, tag=tag, limit=limit)
        return json.dumps({"ok": True, "count": len(data), "data": data}, ensure_ascii=False)
    except Exception as e:
        return json.dumps({"ok": False, "error": f"{type(e).__name__}: {str(e)[:200]}"}, ensure_ascii=False)


@mcp.tool(name="memory_delete", description="删除通用记忆", annotations={"readOnlyHint": False, "destructiveHint": True, "idempotentHint": True, "openWorldHint": False})
def memory_delete(key: str) -> str:
    """删除一条通用记忆。

    Args:
        key: 记忆键
    """
    try:
        storage = _get_storage()
        ok = storage.delete_memory(key)
        return json.dumps({"ok": ok, "key": key}, ensure_ascii=False)
    except Exception as e:
        return json.dumps({"ok": False, "error": f"{type(e).__name__}: {str(e)[:200]}"}, ensure_ascii=False)


@mcp.tool(name="memory_clear_news", description="清理历史新闻数据，可按来源或天数过滤", annotations={"readOnlyHint": False, "destructiveHint": True, "idempotentHint": False, "openWorldHint": False})
def memory_clear_news(source: Optional[str] = None, days: Optional[int] = None) -> str:
    """清理历史新闻数据。

    Args:
        source: 按来源清理
        days: 只保留最近 N 天的数据
    """
    try:
        storage = _get_storage()
        count = storage.clear_news(source=source, days=days)
        return json.dumps({"ok": True, "deleted": count}, ensure_ascii=False)
    except Exception as e:
        return json.dumps({"ok": False, "error": f"{type(e).__name__}: {str(e)[:200]}"}, ensure_ascii=False)


# ─────────────── 调度器管理工具 ───────────────

@mcp.tool(name="scheduler_list", description="列出所有定时调度任务及其状态", annotations=_READ_ONLY)
def scheduler_list() -> str:
    """列出所有调度任务。"""
    try:
        _start_scheduler_if_needed()
        sched = _get_scheduler()
        tasks = sched.list_tasks()
        return json.dumps({"ok": True, "scheduler_running": sched._running, "count": len(tasks), "tasks": tasks}, ensure_ascii=False)
    except Exception as e:
        return json.dumps({"ok": False, "error": f"{type(e).__name__}: {str(e)[:200]}"}, ensure_ascii=False)


@mcp.tool(name="scheduler_add", description="添加定时任务，支持 cron 表达式或间隔分钟", annotations={"readOnlyHint": False, "destructiveHint": False, "idempotentHint": True, "openWorldHint": False})
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
        task_type: 任务类型：news_fetch / market_snapshot / custom_call
        cron_expr: cron 表达式（5段式），与 interval_minutes 二选一
        interval_minutes: 间隔分钟数
        params_json: 任务参数 JSON 字符串
        description: 任务描述

    task_type 对应的 params:
      - news_fetch: {"tool": "工具名", "tool_params": {...}}
      - market_snapshot: {"tool": "工具名", "tool_params": {...}, "snapshot_type": "", "symbol": ""}
      - custom_call: {"tool": "工具名", "tool_params": {...}, "save_result": false, "memory_key": ""}
    """
    try:
        _start_scheduler_if_needed()
        sched = _get_scheduler()
        params = json.loads(params_json) if params_json else {}
        if task_type not in ("news_fetch", "market_snapshot", "custom_call"):
            return json.dumps({"ok": False, "error": f"不支持的任务类型: {task_type}"}, ensure_ascii=False)
        task = sched.add_task(task_name=task_name, task_type=task_type, cron_expr=cron_expr,
                              interval_minutes=interval_minutes, params=params, description=description)
        return json.dumps({"ok": True, "task": task}, ensure_ascii=False)
    except Exception as e:
        return json.dumps({"ok": False, "error": f"{type(e).__name__}: {str(e)[:200]}"}, ensure_ascii=False)


@mcp.tool(name="scheduler_remove", description="删除定时任务", annotations={"readOnlyHint": False, "destructiveHint": True, "idempotentHint": True, "openWorldHint": False})
def scheduler_remove(task_name: str) -> str:
    """删除一个定时任务。

    Args:
        task_name: 任务名称
    """
    try:
        sched = _get_scheduler()
        ok = sched.remove_task(task_name)
        return json.dumps({"ok": ok, "task_name": task_name}, ensure_ascii=False)
    except Exception as e:
        return json.dumps({"ok": False, "error": f"{type(e).__name__}: {str(e)[:200]}"}, ensure_ascii=False)


@mcp.tool(name="scheduler_pause", description="暂停定时任务", annotations={"readOnlyHint": False, "destructiveHint": False, "idempotentHint": True, "openWorldHint": False})
def scheduler_pause(task_name: str) -> str:
    """暂停一个定时任务。

    Args:
        task_name: 任务名称
    """
    try:
        sched = _get_scheduler()
        ok = sched.pause_task(task_name)
        return json.dumps({"ok": ok, "task_name": task_name}, ensure_ascii=False)
    except Exception as e:
        return json.dumps({"ok": False, "error": f"{type(e).__name__}: {str(e)[:200]}"}, ensure_ascii=False)


@mcp.tool(name="scheduler_resume", description="恢复定时任务", annotations={"readOnlyHint": False, "destructiveHint": False, "idempotentHint": True, "openWorldHint": False})
def scheduler_resume(task_name: str) -> str:
    """恢复一个已暂停的定时任务。

    Args:
        task_name: 任务名称
    """
    try:
        _start_scheduler_if_needed()
        sched = _get_scheduler()
        ok = sched.resume_task(task_name)
        return json.dumps({"ok": ok, "task_name": task_name}, ensure_ascii=False)
    except Exception as e:
        return json.dumps({"ok": False, "error": f"{type(e).__name__}: {str(e)[:200]}"}, ensure_ascii=False)


@mcp.tool(name="scheduler_run_now", description="立即执行一次定时任务（手动触发）", annotations={"readOnlyHint": False, "destructiveHint": False, "idempotentHint": False, "openWorldHint": True})
def scheduler_run_now(task_name: str) -> str:
    """立即手动执行一次任务。

    Args:
        task_name: 任务名称
    """
    try:
        sched = _get_scheduler()
        result = sched.run_task_now(task_name)
        return json.dumps(result, ensure_ascii=False)
    except Exception as e:
        return json.dumps({"ok": False, "error": f"{type(e).__name__}: {str(e)[:200]}"}, ensure_ascii=False)


@mcp.tool(name="scheduler_logs", description="查询任务执行日志", annotations=_READ_ONLY)
def scheduler_logs(task_name: Optional[str] = None, limit: int = 50) -> str:
    """查询任务执行历史日志。

    Args:
        task_name: 按任务名过滤
        limit: 返回条数
    """
    try:
        storage = _get_storage()
        logs = storage.query_task_logs(task_name=task_name, limit=limit)
        return json.dumps({"ok": True, "count": len(logs), "logs": logs}, ensure_ascii=False)
    except Exception as e:
        return json.dumps({"ok": False, "error": f"{type(e).__name__}: {str(e)[:200]}"}, ensure_ascii=False)


# ─────────────── WebSocket 推送管理工具 ───────────────

@mcp.tool(name="ws_status", description="查询 WebSocket 推送服务状态：连接数、订阅分布、服务地址", annotations=_READ_ONLY)
def ws_status() -> str:
    """获取 WebSocket 推送服务状态。

    Returns:
        JSON 格式的 WS 服务状态，包含连接数、订阅分布、监听地址
    """
    try:
        pusher = _get_pusher()
        stats = pusher.stats()
        return json.dumps({
            "ok": True,
            "ws_url": f"ws://{stats['host']}:{stats['port']}",
            "running": stats["running"],
            "total_connections": stats["total_connections"],
            "by_topic": stats["by_topic"],
            "subscribe_protocol": {
                "url": f"ws://{stats['host']}:{stats['port']}",
                "step1": "连接后发送 JSON 订阅消息",
                "message": '{"topic": "news|snapshot|custom|all", "task_name": "", "symbol": ""}',
                "step2": "服务端返回 {type: subscribed} 确认",
                "step3": "定时任务执行后自动推送结果",
                "push_format": '{"task_name", "task_type", "timestamp", "new_count", "data"}',
            },
        }, ensure_ascii=False)
    except Exception as e:
        return json.dumps({"ok": False, "error": f"{type(e).__name__}: {str(e)[:200]}"}, ensure_ascii=False)


# ─────────────── 命令行入口 ───────────────

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
    parser.add_argument("--transport", "-t", choices=["stdio", "sse", "streamable-http"], default="stdio", help="传输协议")
    parser.add_argument("--host", default="0.0.0.0", help="监听地址")
    parser.add_argument("--port", "-p", type=int, default=8000, help="监听端口")
    parser.add_argument("--list", "-l", action="store_true", help="列出所有可用工具后退出")
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
        mcp.run(transport=args.transport, host=args.host, port=args.port)
