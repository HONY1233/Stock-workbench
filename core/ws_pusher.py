"""WebSocket 推送模块：定时任务结果实时推送给订阅客户端。

架构：
  - WSPusher 启动独立 WS 服务器（默认端口 8001），与 MCP 服务并行
  - ConnectionManager 管理客户端连接和订阅过滤
  - TaskScheduler 任务执行成功后调用 pusher.broadcast() 推送结果

订阅协议：
  客户端连接后发送 JSON：{"topic": "news|snapshot|all", "task_name": "", "symbol": ""}
  服务端推送 JSON：{"task_name", "task_type", "timestamp", "new_count", "data"}
"""
from __future__ import annotations
import asyncio
import json
import logging
from datetime import datetime
from typing import Optional

logger = logging.getLogger("ws_pusher")


class ConnectionManager:
    """管理 WebSocket 客户端连接和订阅过滤。"""

    def __init__(self):
        # {websocket: {"topic": str, "task_name": str, "symbol": str}}
        self._connections: dict = {}

    def add(self, websocket, subscription: dict) -> None:
        self._connections[websocket] = subscription

    def remove(self, websocket) -> None:
        self._connections.pop(websocket, None)

    def _match(self, subscription: dict, task_name: str, task_type: str,
               data: list) -> bool:
        """检查一条推送是否匹配客户端订阅。"""
        # topic 过滤
        topic = subscription.get("topic", "all")
        if topic != "all":
            type_topic_map = {
                "news_fetch": "news",
                "market_snapshot": "snapshot",
                "custom_call": "custom",
            }
            expected = type_topic_map.get(task_type, "custom")
            if topic != expected:
                return False

        # task_name 过滤
        sub_task = subscription.get("task_name", "")
        if sub_task and task_name != sub_task:
            return False

        # symbol 过滤
        sub_symbol = subscription.get("symbol", "")
        if sub_symbol:
            for item in data:
                item_symbol = str(
                    item.get("symbol") or item.get("代码") or
                    item.get("instrument_id") or ""
                ).lower()
                if sub_symbol.lower() in item_symbol:
                    return True
            return False

        return True

    async def broadcast(self, task_name: str, task_type: str,
                        data: list, new_count: int = 0) -> None:
        """向所有匹配的客户端推送消息。"""
        if not self._connections:
            return

        message = json.dumps({
            "task_name": task_name,
            "task_type": task_type,
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "new_count": new_count,
            "count": len(data),
            "data": data[:50],  # 限制单次推送量，避免消息过大
        }, ensure_ascii=False)

        # 找出匹配的连接
        targets = [
            (ws, sub) for ws, sub in self._connections.items()
            if self._match(sub, task_name, task_type, data)
        ]

        if not targets:
            return

        # 并发推送
        results = await asyncio.gather(
            *[ws.send(message) for ws, _ in targets],
            return_exceptions=True
        )

        # 清理断开的连接
        for (ws, _), result in zip(targets, results):
            if isinstance(result, Exception):
                logger.debug(f"推送失败，移除连接: {result}")
                self._connections.pop(ws, None)

    def stats(self) -> dict:
        """连接统计。"""
        topic_counts = {}
        for sub in self._connections.values():
            t = sub.get("topic", "all")
            topic_counts[t] = topic_counts.get(t, 0) + 1
        return {
            "total_connections": len(self._connections),
            "by_topic": topic_counts,
        }


class WSPusher:
    """WebSocket 推送服务器。

    在独立端口启动 WS 服务，接收客户端订阅，任务执行后推送结果。
    """

    def __init__(self, host: str = "0.0.0.0", port: int = 8001):
        self.host = host
        self.port = port
        self.manager = ConnectionManager()
        self._server: Optional[asyncio.AbstractServer] = None
        self._running = False
        self._loop: Optional[asyncio.AbstractEventLoop] = None  # WS 线程的事件循环

    async def _handler(self, websocket) -> None:
        """处理客户端连接。"""
        # 等待客户端发送订阅消息
        try:
            raw = await asyncio.wait_for(websocket.recv(), timeout=30)
            sub = json.loads(raw) if isinstance(raw, str) else raw
            if not isinstance(sub, dict):
                sub = {"topic": "all"}
        except (asyncio.TimeoutError, json.JSONDecodeError, Exception):
            sub = {"topic": "all"}

        # 规范化订阅
        subscription = {
            "topic": sub.get("topic", "all"),
            "task_name": sub.get("task_name", ""),
            "symbol": sub.get("symbol", ""),
        }
        self.manager.add(websocket, subscription)
        logger.info(f"WS 客户端订阅: {subscription}")

        # 发送确认
        try:
            await websocket.send(json.dumps({
                "type": "subscribed",
                "subscription": subscription,
                "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            }, ensure_ascii=False))
        except Exception:
            pass

        # 保持连接，等待断开
        try:
            async for msg in websocket:
                # 允许客户端更新订阅
                try:
                    new_sub = json.loads(msg) if isinstance(msg, str) else msg
                    if isinstance(new_sub, dict):
                        subscription = {
                            "topic": new_sub.get("topic", "all"),
                            "task_name": new_sub.get("task_name", ""),
                            "symbol": new_sub.get("symbol", ""),
                        }
                        self.manager.add(websocket, subscription)
                        logger.info(f"WS 客户端更新订阅: {subscription}")
                except json.JSONDecodeError:
                    pass
        except Exception:
            pass
        finally:
            self.manager.remove(websocket)
            logger.info("WS 客户端断开")

    async def start_async(self) -> None:
        """异步启动 WS 服务器。"""
        import websockets
        self._loop = asyncio.get_event_loop()  # 保存当前事件循环引用
        self._server = await websockets.serve(
            self._handler, self.host, self.port,
            ping_interval=30, ping_timeout=10,
        )
        self._running = True
        logger.info(f"WS 推送服务启动: ws://{self.host}:{self.port}")

    def start_in_thread(self) -> None:
        """在新线程中启动 WS 服务器（供同步代码调用）。"""
        import threading

        def _run():
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                loop.run_until_complete(self.start_async())
                loop.run_forever()
            except Exception as e:
                logger.error(f"WS 服务器异常: {e}")
            finally:
                loop.close()

        t = threading.Thread(target=_run, daemon=True, name="ws-pusher")
        t.start()

    def broadcast(self, task_name: str, task_type: str,
                  data: list, new_count: int = 0) -> None:
        """推送消息给所有匹配客户端（线程安全，供 TaskScheduler 调用）。

        从非 async 上下文（如 APScheduler 工作线程）调用，
        通过 run_coroutine_threadsafe 投递到 WS 服务器的事件循环。
        """
        if not self._running or not self.manager._connections:
            return
        if self._loop is None or not self._loop.is_running():
            return
        try:
            asyncio.run_coroutine_threadsafe(
                self.manager.broadcast(task_name, task_type, data, new_count),
                self._loop
            )
        except Exception as e:
            logger.debug(f"推送异常: {e}")

    def stats(self) -> dict:
        """获取连接统计。"""
        result = self.manager.stats()
        result["running"] = self._running
        result["host"] = self.host
        result["port"] = self.port
        return result
