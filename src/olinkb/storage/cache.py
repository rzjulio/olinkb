from __future__ import annotations

from collections import OrderedDict
from dataclasses import dataclass
from time import monotonic
from typing import Any


@dataclass
class CacheEntry:
    value: Any
    expires_at: float


class ReadCache:
    def __init__(self, max_size: int = 256, ttl_seconds: int = 300) -> None:
        self._cache: OrderedDict[str, CacheEntry] = OrderedDict()
        self._max_size = max_size
        self._ttl_seconds = ttl_seconds

    def get(self, key: str) -> Any | None:
        entry = self._cache.get(key)
        if entry is None:
            return None
        if entry.expires_at <= monotonic():
            self._cache.pop(key, None)
            return None

        self._cache.move_to_end(key)
        return entry.value

    def set(self, key: str, value: Any) -> None:
        self._cache[key] = CacheEntry(value=value, expires_at=monotonic() + self._ttl_seconds)
        self._cache.move_to_end(key)
        while len(self._cache) > self._max_size:
            self._cache.popitem(last=False)

    def invalidate(self, key: str) -> None:
        self._cache.pop(key, None)

    def invalidate_prefix(self, prefix: str) -> None:
        keys = [key for key in self._cache if key.startswith(prefix)]
        for key in keys:
            self._cache.pop(key, None)
