"""SQLite 存储层：长期记忆 + 调度配置 + 任务日志。

表结构：
  - news_items     新闻/公告类数据（按 source + item_id 去重）
  - market_snapshots 行情快照（按 symbol + timestamp 去重）
  - memory_items   通用记忆（agent 可读写的键值记忆）
  - scheduler_tasks 调度任务配置
  - task_logs      任务执行日志
"""
from __future__ import annotations
import sqlite3
import json
import os
import threading
from datetime import datetime
from typing import Optional, Any


def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


class SQLiteStorage:
    """SQLite 存储封装，线程安全。"""

    def __init__(self, db_path: str = "data/akshare_memory.db"):
        os.makedirs(os.path.dirname(db_path) or ".", exist_ok=True)
        self.db_path = db_path
        self._lock = threading.Lock()
        self._init_db()

    def _get_conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        with self._lock, self._get_conn() as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS news_items (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    source TEXT NOT NULL,
                    item_id TEXT NOT NULL,
                    title TEXT,
                    content TEXT,
                    brief TEXT,
                    category TEXT,
                    level TEXT,
                    publish_time TEXT,
                    extra_json TEXT,
                    created_at TEXT DEFAULT (datetime('now','localtime')),
                    UNIQUE(source, item_id)
                );
                CREATE INDEX IF NOT EXISTS idx_news_source ON news_items(source);
                CREATE INDEX IF NOT EXISTS idx_news_publish_time ON news_items(publish_time);

                CREATE TABLE IF NOT EXISTS market_snapshots (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    snapshot_type TEXT NOT NULL,
                    symbol TEXT,
                    snapshot_time TEXT NOT NULL,
                    data_json TEXT NOT NULL,
                    created_at TEXT DEFAULT (datetime('now','localtime')),
                    UNIQUE(snapshot_type, symbol, snapshot_time)
                );
                CREATE INDEX IF NOT EXISTS idx_market_type ON market_snapshots(snapshot_type);
                CREATE INDEX IF NOT EXISTS idx_market_time ON market_snapshots(snapshot_time);

                CREATE TABLE IF NOT EXISTS memory_items (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    memory_key TEXT NOT NULL UNIQUE,
                    memory_value TEXT NOT NULL,
                    tags TEXT,
                    created_at TEXT DEFAULT (datetime('now','localtime')),
                    updated_at TEXT DEFAULT (datetime('now','localtime'))
                );
                CREATE INDEX IF NOT EXISTS idx_memory_tags ON memory_items(tags);

                CREATE TABLE IF NOT EXISTS scheduler_tasks (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    task_name TEXT NOT NULL UNIQUE,
                    task_type TEXT NOT NULL,
                    cron_expr TEXT,
                    interval_minutes INTEGER,
                    params_json TEXT,
                    enabled INTEGER DEFAULT 1,
                    description TEXT,
                    created_at TEXT DEFAULT (datetime('now','localtime')),
                    updated_at TEXT DEFAULT (datetime('now','localtime'))
                );

                CREATE TABLE IF NOT EXISTS task_logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    task_name TEXT NOT NULL,
                    status TEXT NOT NULL,
                    message TEXT,
                    new_count INTEGER DEFAULT 0,
                    duration_ms INTEGER,
                    started_at TEXT DEFAULT (datetime('now','localtime')),
                    finished_at TEXT
                );
                CREATE INDEX IF NOT EXISTS idx_task_logs_name ON task_logs(task_name);
                CREATE INDEX IF NOT EXISTS idx_task_logs_time ON task_logs(started_at);
            """)
            conn.commit()

    # ─────────────── 新闻数据 ───────────────

    def upsert_news(self, source: str, item_id: str, title: str = "",
                    content: str = "", brief: str = "", category: str = "",
                    level: str = "", publish_time: str = "",
                    extra: Optional[dict] = None) -> bool:
        """插入或更新一条新闻，返回是否为新插入（True=新增）。"""
        extra_json = json.dumps(extra, ensure_ascii=False) if extra else None
        with self._lock, self._get_conn() as conn:
            try:
                conn.execute(
                    """INSERT INTO news_items (source, item_id, title, content, brief, category, level, publish_time, extra_json)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (source, item_id, title, content, brief, category, level, publish_time, extra_json)
                )
                conn.commit()
                return True
            except sqlite3.IntegrityError:
                conn.execute(
                    """UPDATE news_items SET title=?, content=?, brief=?, category=?, level=?, publish_time=?, extra_json=?
                       WHERE source=? AND item_id=?""",
                    (title, content, brief, category, level, publish_time, extra_json, source, item_id)
                )
                conn.commit()
                return False

    def query_news(self, source: Optional[str] = None, keyword: Optional[str] = None,
                   limit: int = 50, offset: int = 0) -> list[dict]:
        """查询新闻数据。"""
        sql = "SELECT * FROM news_items WHERE 1=1"
        params: list[Any] = []
        if source:
            sql += " AND source = ?"
            params.append(source)
        if keyword:
            sql += " AND (title LIKE ? OR content LIKE ? OR brief LIKE ?)"
            kw = f"%{keyword}%"
            params.extend([kw, kw, kw])
        sql += " ORDER BY publish_time DESC, id DESC LIMIT ? OFFSET ?"
        params.extend([limit, offset])
        with self._lock, self._get_conn() as conn:
            rows = conn.execute(sql, params).fetchall()
            return [dict(r) for r in rows]

    def news_count(self, source: Optional[str] = None) -> int:
        sql = "SELECT COUNT(*) FROM news_items"
        params = []
        if source:
            sql += " WHERE source = ?"
            params.append(source)
        with self._lock, self._get_conn() as conn:
            return conn.execute(sql, params).fetchone()[0]

    def clear_news(self, source: Optional[str] = None, days: Optional[int] = None) -> int:
        sql = "DELETE FROM news_items"
        params = []
        conditions = []
        if source:
            conditions.append("source = ?")
            params.append(source)
        if days:
            conditions.append("created_at < datetime('now','localtime',?)")
            params.append(f"-{days} days")
        if conditions:
            sql += " WHERE " + " AND ".join(conditions)
        with self._lock, self._get_conn() as conn:
            cur = conn.execute(sql, params)
            conn.commit()
            return cur.rowcount

    # ─────────────── 行情快照 ───────────────

    def save_market_snapshot(self, snapshot_type: str, symbol: str,
                             snapshot_time: str, data: dict) -> bool:
        """保存行情快照，返回是否为新增。"""
        data_json = json.dumps(data, ensure_ascii=False)
        with self._lock, self._get_conn() as conn:
            try:
                conn.execute(
                    "INSERT INTO market_snapshots (snapshot_type, symbol, snapshot_time, data_json) VALUES (?, ?, ?, ?)",
                    (snapshot_type, symbol, snapshot_time, data_json)
                )
                conn.commit()
                return True
            except sqlite3.IntegrityError:
                conn.execute(
                    "UPDATE market_snapshots SET data_json=? WHERE snapshot_type=? AND symbol=? AND snapshot_time=?",
                    (data_json, snapshot_type, symbol, snapshot_time)
                )
                conn.commit()
                return False

    def query_market_snapshots(self, snapshot_type: str, symbol: Optional[str] = None,
                               limit: int = 100) -> list[dict]:
        sql = "SELECT * FROM market_snapshots WHERE snapshot_type = ?"
        params: list[Any] = [snapshot_type]
        if symbol:
            sql += " AND symbol = ?"
            params.append(symbol)
        sql += " ORDER BY snapshot_time DESC LIMIT ?"
        params.append(limit)
        with self._lock, self._get_conn() as conn:
            rows = conn.execute(sql, params).fetchall()
            return [dict(r) for r in rows]

    # ─────────────── 通用记忆 ───────────────

    def set_memory(self, key: str, value: str, tags: str = "") -> None:
        with self._lock, self._get_conn() as conn:
            conn.execute(
                """INSERT INTO memory_items (memory_key, memory_value, tags)
                   VALUES (?, ?, ?)
                   ON CONFLICT(memory_key) DO UPDATE SET
                     memory_value=excluded.memory_value,
                     tags=excluded.tags,
                     updated_at=datetime('now','localtime')""",
                (key, value, tags)
            )
            conn.commit()

    def get_memory(self, key: str) -> Optional[str]:
        with self._lock, self._get_conn() as conn:
            row = conn.execute("SELECT memory_value FROM memory_items WHERE memory_key=?", (key,)).fetchone()
            return row["memory_value"] if row else None

    def search_memory(self, keyword: str = "", tag: str = "", limit: int = 50) -> list[dict]:
        sql = "SELECT * FROM memory_items WHERE 1=1"
        params: list[Any] = []
        if keyword:
            sql += " AND (memory_key LIKE ? OR memory_value LIKE ?)"
            kw = f"%{keyword}%"
            params.extend([kw, kw])
        if tag:
            sql += " AND tags LIKE ?"
            params.append(f"%{tag}%")
        sql += " ORDER BY updated_at DESC LIMIT ?"
        params.append(limit)
        with self._lock, self._get_conn() as conn:
            rows = conn.execute(sql, params).fetchall()
            return [dict(r) for r in rows]

    def delete_memory(self, key: str) -> bool:
        with self._lock, self._get_conn() as conn:
            cur = conn.execute("DELETE FROM memory_items WHERE memory_key=?", (key,))
            conn.commit()
            return cur.rowcount > 0

    def memory_stats(self) -> dict:
        with self._lock, self._get_conn() as conn:
            total = conn.execute("SELECT COUNT(*) FROM memory_items").fetchone()[0]
            return {"total": total}

    # ─────────────── 调度任务配置 ───────────────

    def save_task(self, task_name: str, task_type: str, cron_expr: Optional[str] = None,
                  interval_minutes: Optional[int] = None, params: Optional[dict] = None,
                  enabled: bool = True, description: str = "") -> None:
        params_json = json.dumps(params, ensure_ascii=False) if params else None
        with self._lock, self._get_conn() as conn:
            conn.execute(
                """INSERT INTO scheduler_tasks (task_name, task_type, cron_expr, interval_minutes, params_json, enabled, description)
                   VALUES (?, ?, ?, ?, ?, ?, ?)
                   ON CONFLICT(task_name) DO UPDATE SET
                     task_type=excluded.task_type,
                     cron_expr=excluded.cron_expr,
                     interval_minutes=excluded.interval_minutes,
                     params_json=excluded.params_json,
                     enabled=excluded.enabled,
                     description=excluded.description,
                     updated_at=datetime('now','localtime')""",
                (task_name, task_type, cron_expr, interval_minutes, params_json, 1 if enabled else 0, description)
            )
            conn.commit()

    def list_tasks(self) -> list[dict]:
        with self._lock, self._get_conn() as conn:
            rows = conn.execute("SELECT * FROM scheduler_tasks ORDER BY id").fetchall()
            result = []
            for r in rows:
                d = dict(r)
                if d.get("params_json"):
                    d["params"] = json.loads(d["params_json"])
                    del d["params_json"]
                else:
                    d["params"] = {}
                d["enabled"] = bool(d["enabled"])
                result.append(d)
            return result

    def get_task(self, task_name: str) -> Optional[dict]:
        with self._lock, self._get_conn() as conn:
            row = conn.execute("SELECT * FROM scheduler_tasks WHERE task_name=?", (task_name,)).fetchone()
            if not row:
                return None
            d = dict(row)
            if d.get("params_json"):
                d["params"] = json.loads(d["params_json"])
                del d["params_json"]
            else:
                d["params"] = {}
            d["enabled"] = bool(d["enabled"])
            return d

    def delete_task(self, task_name: str) -> bool:
        with self._lock, self._get_conn() as conn:
            cur = conn.execute("DELETE FROM scheduler_tasks WHERE task_name=?", (task_name,))
            conn.commit()
            return cur.rowcount > 0

    def set_task_enabled(self, task_name: str, enabled: bool) -> bool:
        with self._lock, self._get_conn() as conn:
            cur = conn.execute(
                "UPDATE scheduler_tasks SET enabled=?, updated_at=datetime('now','localtime') WHERE task_name=?",
                (1 if enabled else 0, task_name)
            )
            conn.commit()
            return cur.rowcount > 0

    # ─────────────── 任务日志 ───────────────

    def log_task_start(self, task_name: str) -> int:
        with self._lock, self._get_conn() as conn:
            cur = conn.execute(
                "INSERT INTO task_logs (task_name, status) VALUES (?, 'running')",
                (task_name,)
            )
            conn.commit()
            return cur.lastrowid

    def log_task_finish(self, log_id: int, status: str, message: str = "",
                        new_count: int = 0, duration_ms: int = 0) -> None:
        with self._lock, self._get_conn() as conn:
            conn.execute(
                """UPDATE task_logs SET status=?, message=?, new_count=?, duration_ms=?,
                   finished_at=datetime('now','localtime') WHERE id=?""",
                (status, message, new_count, duration_ms, log_id)
            )
            conn.commit()

    def query_task_logs(self, task_name: Optional[str] = None, limit: int = 50) -> list[dict]:
        sql = "SELECT * FROM task_logs"
        params: list[Any] = []
        if task_name:
            sql += " WHERE task_name = ?"
            params.append(task_name)
        sql += " ORDER BY id DESC LIMIT ?"
        params.append(limit)
        with self._lock, self._get_conn() as conn:
            rows = conn.execute(sql, params).fetchall()
            return [dict(r) for r in rows]

    # ─────────────── 全局统计 ───────────────

    def stats(self) -> dict:
        with self._lock, self._get_conn() as conn:
            news_total = conn.execute("SELECT COUNT(*) FROM news_items").fetchone()[0]
            market_total = conn.execute("SELECT COUNT(*) FROM market_snapshots").fetchone()[0]
            memory_total = conn.execute("SELECT COUNT(*) FROM memory_items").fetchone()[0]
            task_total = conn.execute("SELECT COUNT(*) FROM scheduler_tasks").fetchone()[0]
            news_sources = [r[0] for r in conn.execute(
                "SELECT DISTINCT source FROM news_items ORDER BY source"
            ).fetchall()]
            return {
                "news_total": news_total,
                "market_snapshots": market_total,
                "memory_items": memory_total,
                "scheduler_tasks": task_total,
                "news_sources": news_sources,
                "db_path": self.db_path,
            }
