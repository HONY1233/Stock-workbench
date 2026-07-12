"""APScheduler 调度模块：定时任务管理。

内置任务类型：
  - news_fetch     抓取新闻类数据（财联社电报、全球新闻等）
  - market_snapshot 行情快照（指数/个股实时行情）
  - custom_call    自定义 MCP 工具调用

支持 cron 表达式和间隔分钟两种调度方式。
任务配置持久化在 SQLite 中，启动时自动加载。
"""
from __future__ import annotations
import json
import time
import traceback
from datetime import datetime
from typing import Optional, Callable, Any

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

from core.storage import SQLiteStorage
from core.dedup import RedisDedup


class TaskScheduler:
    """任务调度器封装。"""

    def __init__(self, storage: SQLiteStorage, dedup: RedisDedup,
                 tool_registry: Optional[dict[str, Callable]] = None,
                 pusher=None):
        self.storage = storage
        self.dedup = dedup
        self.tool_registry = tool_registry or {}
        self.pusher = pusher  # WSPusher 实例，可选
        self.scheduler = BackgroundScheduler(timezone="Asia/Shanghai")
        self._task_handlers: dict[str, Callable] = {}
        self._register_default_handlers()
        self._running = False

    def _register_default_handlers(self) -> None:
        """注册内置任务处理器。"""
        self._task_handlers["news_fetch"] = self._handle_news_fetch
        self._task_handlers["market_snapshot"] = self._handle_market_snapshot
        self._task_handlers["custom_call"] = self._handle_custom_call

    def register_handler(self, task_type: str, handler: Callable) -> None:
        """注册自定义任务处理器。"""
        self._task_handlers[task_type] = handler

    # ─────────────── 任务执行包装 ───────────────

    def _run_task(self, task_name: str, task_type: str, params: dict) -> None:
        """任务执行包装：记录日志 + 异常捕获 + WS 推送。"""
        log_id = self.storage.log_task_start(task_name)
        start_ts = time.time()
        try:
            handler = self._task_handlers.get(task_type)
            if not handler:
                raise ValueError(f"未知任务类型: {task_type}")
            result = handler(task_name, params)
            # handler 可返回 int(new_count) 或 (new_count, pushed_data)
            if isinstance(result, tuple) and len(result) == 2:
                new_count, pushed_data = result
            else:
                new_count = result if isinstance(result, int) else 0
                pushed_data = []
            duration = int((time.time() - start_ts) * 1000)
            self.storage.log_task_finish(
                log_id, "success", message="执行成功",
                new_count=new_count, duration_ms=duration
            )
            # WS 推送
            if self.pusher and pushed_data:
                self.pusher.broadcast(task_name, task_type, pushed_data, new_count)
        except Exception as e:
            duration = int((time.time() - start_ts) * 1000)
            err = f"{type(e).__name__}: {str(e)[:500]}\n{traceback.format_exc()[:1000]}"
            self.storage.log_task_finish(
                log_id, "failed", message=err,
                new_count=0, duration_ms=duration
            )

    # ─────────────── 内置任务处理器 ───────────────

    def _handle_news_fetch(self, task_name: str, params: dict):
        """新闻抓取任务：调用指定 MCP 工具，将结果存入 SQLite。

        params:
          tool: 工具名，如 cls_telegraph, global_news_em, stock_news 等
          tool_params: 传递给工具的参数字典
          source_override: 覆盖 source 名称（可选）
          id_field: 作为唯一标识的字段名，默认 id

        Returns:
            (new_count, pushed_items) 元组
        """
        tool_name = params.get("tool", "")
        tool_params = params.get("tool_params", {})
        source = params.get("source_override") or tool_name
        id_field = params.get("id_field", "id")

        if tool_name not in self.tool_registry:
            raise ValueError(f"工具 {tool_name} 未注册")

        result_str = self.tool_registry[tool_name](**tool_params)
        result = json.loads(result_str) if isinstance(result_str, str) else result_str

        if not result.get("ok"):
            raise ValueError(result.get("error", "工具调用失败"))

        data = result.get("data", [])
        new_count = 0
        pushed_items = []
        for item in data:
            item_id = str(item.get(id_field) or item.get("id") or item.get("代码") or
                          item.get("标题", "")[:50])
            if self.dedup.is_duplicate(f"news:{source}", item_id):
                continue

            title = str(item.get("title") or item.get("标题") or item.get("name") or "")
            content = str(item.get("content") or item.get("内容") or item.get("brief") or "")
            brief = str(item.get("brief") or item.get("摘要") or "")
            level = str(item.get("level") or item.get("级别") or "")
            publish_time = str(item.get("datetime") or item.get("发布时间") or
                               item.get("ctime") or datetime.now().strftime("%Y-%m-%d %H:%M:%S"))

            is_new = self.storage.upsert_news(
                source=source,
                item_id=item_id,
                title=title,
                content=content,
                brief=brief,
                level=level,
                publish_time=publish_time,
                extra=item,
            )
            if is_new:
                new_count += 1
                pushed_items.append(item)
                self.dedup.mark_seen(f"news:{source}", [item_id])

        return new_count, pushed_items

    def _handle_market_snapshot(self, task_name: str, params: dict):
        """行情快照任务：保存当前行情快照。

        params:
          tool: 工具名，如 stock_zh_index_spot, stock_zh_a_spot 等
          tool_params: 工具参数
          snapshot_type: 快照类型分类
          symbol: 标的（可选，用于分类）

        Returns:
            (new_count, pushed_data) 元组
        """
        tool_name = params.get("tool", "")
        tool_params = params.get("tool_params", {})
        snapshot_type = params.get("snapshot_type") or tool_name
        symbol = params.get("symbol", "")

        if tool_name not in self.tool_registry:
            raise ValueError(f"工具 {tool_name} 未注册")

        result_str = self.tool_registry[tool_name](**tool_params)
        result = json.loads(result_str) if isinstance(result_str, str) else result_str

        if not result.get("ok"):
            raise ValueError(result.get("error", "工具调用失败"))

        data = result.get("data", [])
        snapshot_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        new_count = 0
        pushed_data = []

        if isinstance(data, list) and len(data) == 1:
            item = data[0]
            is_new = self.storage.save_market_snapshot(
                snapshot_type=snapshot_type,
                symbol=symbol or str(item.get("代码") or item.get("symbol") or ""),
                snapshot_time=snapshot_time,
                data=item,
            )
            if is_new:
                new_count += 1
                pushed_data = [item]
        else:
            is_new = self.storage.save_market_snapshot(
                snapshot_type=snapshot_type,
                symbol=symbol,
                snapshot_time=snapshot_time,
                data={"items": data},
            )
            if is_new:
                new_count += 1
                pushed_data = data if isinstance(data, list) else [data]

        return new_count, pushed_data

    def _handle_custom_call(self, task_name: str, params: dict) -> int:
        """自定义工具调用任务：仅执行工具调用，不存数据。

        params:
          tool: 工具名
          tool_params: 工具参数
          save_result: 是否保存结果到 memory（默认 False）
          memory_key: 保存到 memory 的 key
        """
        tool_name = params.get("tool", "")
        tool_params = params.get("tool_params", {})
        save_result = params.get("save_result", False)
        memory_key = params.get("memory_key", f"custom:{task_name}")

        if tool_name not in self.tool_registry:
            raise ValueError(f"工具 {tool_name} 未注册")

        result_str = self.tool_registry[tool_name](**tool_params)

        if save_result:
            self.storage.set_memory(
                key=memory_key,
                value=result_str if isinstance(result_str, str) else json.dumps(result_str, ensure_ascii=False),
                tags="custom_task",
            )

        return 1

    # ─────────────── 调度管理 ───────────────

    def start(self) -> None:
        """启动调度器，从数据库加载所有启用的任务。"""
        if self._running:
            return
        tasks = self.storage.list_tasks()
        for task in tasks:
            if task["enabled"]:
                self._add_job(task)
        self.scheduler.start()
        self._running = True

    def shutdown(self) -> None:
        """关闭调度器。"""
        if self._running:
            self.scheduler.shutdown(wait=False)
            self._running = False

    def _add_job(self, task: dict) -> None:
        """根据任务配置添加 APScheduler job。"""
        task_name = task["task_name"]
        task_type = task["task_type"]
        params = task.get("params", {})

        if task.get("cron_expr"):
            parts = task["cron_expr"].split()
            if len(parts) == 5:
                minute, hour, day, month, day_of_week = parts
                trigger = CronTrigger(
                    minute=minute, hour=hour, day=day,
                    month=month, day_of_week=day_of_week,
                    timezone="Asia/Shanghai"
                )
            else:
                trigger = CronTrigger.from_crontab(task["cron_expr"], timezone="Asia/Shanghai")
        elif task.get("interval_minutes"):
            trigger = IntervalTrigger(minutes=task["interval_minutes"], timezone="Asia/Shanghai")
        else:
            trigger = IntervalTrigger(minutes=60, timezone="Asia/Shanghai")

        self.scheduler.add_job(
            self._run_task,
            trigger=trigger,
            id=task_name,
            args=[task_name, task_type, params],
            replace_existing=True,
            misfire_grace_time=300,
            coalesce=True,
        )

    def add_task(self, task_name: str, task_type: str,
                 cron_expr: Optional[str] = None,
                 interval_minutes: Optional[int] = None,
                 params: Optional[dict] = None,
                 description: str = "") -> dict:
        """添加一个新任务。"""
        if not cron_expr and not interval_minutes:
            interval_minutes = 60

        self.storage.save_task(
            task_name=task_name,
            task_type=task_type,
            cron_expr=cron_expr,
            interval_minutes=interval_minutes,
            params=params,
            enabled=True,
            description=description,
        )
        task = self.storage.get_task(task_name)
        if task and self._running:
            self._add_job(task)
        return task or {}

    def remove_task(self, task_name: str) -> bool:
        """删除任务。"""
        if self._running:
            try:
                self.scheduler.remove_job(task_name)
            except Exception:
                pass
        return self.storage.delete_task(task_name)

    def pause_task(self, task_name: str) -> bool:
        """暂停任务。"""
        if self._running:
            try:
                self.scheduler.pause_job(task_name)
            except Exception:
                pass
        return self.storage.set_task_enabled(task_name, False)

    def resume_task(self, task_name: str) -> bool:
        """恢复任务。"""
        task = self.storage.get_task(task_name)
        if not task:
            return False
        self.storage.set_task_enabled(task_name, True)
        if self._running:
            if self.scheduler.get_job(task_name):
                try:
                    self.scheduler.resume_job(task_name)
                except Exception:
                    pass
            else:
                self._add_job(task)
        return True

    def run_task_now(self, task_name: str) -> dict:
        """立即执行一次任务。"""
        task = self.storage.get_task(task_name)
        if not task:
            return {"ok": False, "error": f"任务 {task_name} 不存在"}
        try:
            self._run_task(task_name, task["task_type"], task.get("params", {}))
            return {"ok": True, "message": "执行完成"}
        except Exception as e:
            return {"ok": False, "error": f"{type(e).__name__}: {str(e)[:200]}"}

    def list_tasks(self) -> list[dict]:
        """列出所有任务及运行状态。"""
        tasks = self.storage.list_tasks()
        result = []
        for task in tasks:
            info = dict(task)
            if self._running:
                job = self.scheduler.get_job(task["task_name"])
                if job:
                    info["next_run_time"] = str(job.next_run_time) if job.next_run_time else None
                    info["job_status"] = "paused" if job.next_run_time is None and task["enabled"] else "active"
                else:
                    info["job_status"] = "stopped"
            else:
                info["job_status"] = "scheduler_stopped"
            result.append(info)
        return result

    def status(self) -> dict:
        """调度器状态。"""
        return {
            "running": self._running,
            "task_count": len(self.storage.list_tasks()),
            "job_count": len(self.scheduler.get_jobs()) if self._running else 0,
        }
