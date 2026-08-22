"""Cache com TTL para absorver rajadas da UI (NFR-014).

O relógio é injetável para que os testes não durmam.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Generic, TypeVar

T = TypeVar("T")


@dataclass(frozen=True)
class CacheEntry(Generic[T]):
    value: T
    stored_at: float

    def age(self, now: float) -> float:
        return now - self.stored_at


class TTLCache:
    """Cache simples chave/valor com expiração por tempo."""

    def __init__(self, ttl_seconds: float, clock: Callable[[], float] = time.monotonic) -> None:
        self._ttl = ttl_seconds
        self._clock = clock
        self._entries: dict[str, CacheEntry[Any]] = {}

    def get(self, key: str) -> Any | None:
        entry = self._entries.get(key)
        if entry is None:
            return None
        if entry.age(self._clock()) > self._ttl:
            del self._entries[key]
            return None
        return entry.value

    def get_with_age(self, key: str) -> tuple[Any, float] | None:
        """Devolve valor mesmo expirado, junto da idade — permite marcar STALE."""
        entry = self._entries.get(key)
        if entry is None:
            return None
        return entry.value, entry.age(self._clock())

    def set(self, key: str, value: Any) -> None:
        self._entries[key] = CacheEntry(value=value, stored_at=self._clock())

    def invalidate(self, key: str) -> None:
        self._entries.pop(key, None)

    def invalidate_prefix(self, prefix: str) -> None:
        for key in [k for k in self._entries if k.startswith(prefix)]:
            del self._entries[key]

    def clear(self) -> None:
        self._entries.clear()

    def is_stale(self, key: str) -> bool:
        entry = self._entries.get(key)
        return entry is not None and entry.age(self._clock()) > self._ttl


class NullCache(TTLCache):
    """Não guarda nada. Usado em teste, para exercitar sempre o caminho real."""

    def __init__(self) -> None:
        super().__init__(ttl_seconds=0.0)

    def get(self, key: str) -> Any | None:
        return None

    def set(self, key: str, value: Any) -> None:
        return None
