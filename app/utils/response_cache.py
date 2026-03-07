"""响应缓存服务

提供API响应缓存功能，减少重复请求的上游调用。
目前仅对 embeddings 接口启用，因为 completions/chat 结果不固定。
"""
import asyncio
import hashlib
import json
import time
from typing import Dict, Optional, Any
from collections import OrderedDict

from app.utils.logging_config import get_logger

logger = get_logger(__name__)


class ResponseCache:
    """响应缓存服务

    使用内存缓存存储API响应，支持LRU淘汰和TTL过期。

    特性：
    - LRU淘汰策略
    - TTL过期机制
    - 线程安全
    - 仅缓存特定接口（embeddings）
    """

    def __init__(self, max_size: int = 1000, ttl: int = 300):
        """初始化响应缓存

        Args:
            max_size: 最大缓存条目数
            ttl: 缓存有效期（秒）
        """
        self._cache: OrderedDict[str, Dict[str, Any]] = OrderedDict()
        self._max_size = max_size
        self._ttl = ttl
        self._lock = asyncio.Lock()
        self._stats = {
            "hits": 0,
            "misses": 0,
            "evictions": 0,
        }

    def _generate_key(self, request_data: Dict[str, Any]) -> str:
        """生成缓存键

        基于请求数据生成唯一键，用于查找缓存。

        Args:
            request_data: 请求数据

        Returns:
            缓存键（SHA256哈希）
        """
        # 标准化请求数据（排序键以确保一致性）
        normalized = json.dumps(request_data, sort_keys=True, ensure_ascii=False)
        return hashlib.sha256(normalized.encode()).hexdigest()

    async def get(self, request_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """获取缓存响应

        Args:
            request_data: 请求数据

        Returns:
            缓存的响应数据，未命中返回 None
        """
        key = self._generate_key(request_data)

        async with self._lock:
            cached = self._cache.get(key)
            if cached:
                # 检查是否过期
                if time.time() - cached["timestamp"] < self._ttl:
                    # 命中，移动到末尾（LRU）
                    self._cache.move_to_end(key)
                    self._stats["hits"] += 1
                    logger.debug(f"Response cache hit | key={key[:16]}...")
                    return cached["data"]
                else:
                    # 过期，删除
                    del self._cache[key]

            self._stats["misses"] += 1
            logger.debug(f"Response cache miss | key={key[:16]}...")
            return None

    async def set(self, request_data: Dict[str, Any], response_data: Dict[str, Any]) -> None:
        """设置缓存

        Args:
            request_data: 请求数据
            response_data: 响应数据
        """
        key = self._generate_key(request_data)

        async with self._lock:
            # LRU淘汰
            if len(self._cache) >= self._max_size:
                oldest_key, _ = self._cache.popitem(last=False)
                self._stats["evictions"] += 1
                logger.debug(f"Response cache eviction | key={oldest_key[:16]}...")

            self._cache[key] = {
                "data": response_data,
                "timestamp": time.time(),
            }
            self._cache.move_to_end(key)
            logger.debug(f"Response cache set | key={key[:16]}...")

    async def invalidate(self, request_data: Dict[str, Any]) -> None:
        """使指定请求的缓存失效

        Args:
            request_data: 请求数据
        """
        key = self._generate_key(request_data)

        async with self._lock:
            if key in self._cache:
                del self._cache[key]
                logger.debug(f"Response cache invalidated | key={key[:16]}...")

    async def clear(self) -> None:
        """清空所有缓存"""
        async with self._lock:
            self._cache.clear()
            logger.info("Response cache cleared")

    def get_stats(self) -> Dict[str, int]:
        """获取缓存统计信息

        Returns:
            统计信息字典
        """
        total = self._stats["hits"] + self._stats["misses"]
        hit_rate = self._stats["hits"] / total if total > 0 else 0

        return {
            "hits": self._stats["hits"],
            "misses": self._stats["misses"],
            "evictions": self._stats["evictions"],
            "hit_rate": round(hit_rate, 4),
            "size": len(self._cache),
            "max_size": self._max_size,
            "ttl": self._ttl,
        }


# 全局响应缓存实例
response_cache = ResponseCache(max_size=1000, ttl=300)
