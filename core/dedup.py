"""Redis 去重缓存层：快速去重判断 + 热数据缓存。

Redis 不可用时自动降级为内存 set 缓存，保证服务可用。
"""
from __future__ import annotations
import hashlib
import time
from typing import Optional, Iterable


class RedisDedup:
    """Redis 去重缓存封装，支持自动降级到内存。"""

    def __init__(self, redis_url: str = "redis://localhost:6379/0",
                 key_prefix: str = "akshare:dedup",
                 default_ttl: int = 86400 * 7):
        self.key_prefix = key_prefix
        self.default_ttl = default_ttl
        self._client = None
        self._fallback = {}
        self._available = False
        self._init_redis(redis_url)

    def _init_redis(self, redis_url: str) -> None:
        try:
            import redis
            self._client = redis.Redis.from_url(redis_url, decode_responses=True, socket_timeout=2)
            self._client.ping()
            self._available = True
        except Exception:
            self._available = False
            self._client = None

    @property
    def available(self) -> bool:
        return self._available

    def _key(self, category: str) -> str:
        return f"{self.key_prefix}:{category}"

    def _hash(self, item_id: str) -> str:
        return hashlib.md5(item_id.encode("utf-8")).hexdigest()

    def is_duplicate(self, category: str, item_id: str) -> bool:
        """判断 item_id 是否已存在（True=重复）。"""
        h = self._hash(item_id)
        key = self._key(category)
        if self._available:
            try:
                return bool(self._client.sismember(key, h))
            except Exception:
                pass
        s = self._fallback.setdefault(key, set())
        return h in s

    def mark_seen(self, category: str, item_ids: Iterable[str], ttl: Optional[int] = None) -> int:
        """标记一批 item_id 为已见，返回新增数量。"""
        key = self._key(category)
        if ttl is None:
            ttl = self.default_ttl
        hashes = [self._hash(i) for i in item_ids]
        if self._available:
            try:
                pipe = self._client.pipeline()
                for h in hashes:
                    pipe.sadd(key, h)
                pipe.expire(key, ttl)
                results = pipe.execute()
                return sum(int(r) for r in results[:-1])
            except Exception:
                pass
        s = self._fallback.setdefault(key, set())
        new_count = 0
        for h in hashes:
            if h not in s:
                s.add(h)
                new_count += 1
        return new_count

    def filter_new(self, category: str, item_ids: list[str]) -> list[str]:
        """过滤出未见过的 item_id。"""
        return [i for i in item_ids if not self.is_duplicate(category, i)]

    def clear(self, category: str) -> int:
        """清空某个分类的去重缓存，返回清除的条数。"""
        key = self._key(category)
        if self._available:
            try:
                return self._client.delete(key)
            except Exception:
                pass
        if key in self._fallback:
            n = len(self._fallback[key])
            del self._fallback[key]
            return n
        return 0

    def count(self, category: str) -> int:
        key = self._key(category)
        if self._available:
            try:
                return self._client.scard(key)
            except Exception:
                pass
        return len(self._fallback.get(key, set()))

    # ─────────────── 缓存（string 类型） ───────────────

    def cache_get(self, cache_key: str) -> Optional[str]:
        full_key = f"{self.key_prefix}:cache:{cache_key}"
        if self._available:
            try:
                val = self._client.get(full_key)
                return val if val is not None else None
            except Exception:
                return None
        return self._fallback.get(f"__cache__:{cache_key}")

    def cache_set(self, cache_key: str, value: str, ttl: Optional[int] = None) -> None:
        full_key = f"{self.key_prefix}:cache:{cache_key}"
        if ttl is None:
            ttl = self.default_ttl
        if self._available:
            try:
                self._client.setex(full_key, ttl, value)
                return
            except Exception:
                pass
        self._fallback[f"__cache__:{cache_key}"] = value

    def info(self) -> dict:
        return {
            "available": self._available,
            "key_prefix": self.key_prefix,
            "default_ttl": self.default_ttl,
        }
