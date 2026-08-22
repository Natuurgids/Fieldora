"""Bounded asynchronous thumbnail request coordinator."""

from __future__ import annotations

from collections import OrderedDict
from collections.abc import Callable
from concurrent.futures import Future, ThreadPoolExecutor
from pathlib import Path
from threading import Lock

ThumbnailCallback = Callable[[str, bytes | None], None]


class ThumbnailCoordinator:
    def __init__(self, *, max_workers: int = 4, max_cache_bytes: int = 64 * 1024 * 1024) -> None:
        self._pool = ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="thumbnail-ui")
        self._max = max_cache_bytes
        self._bytes = 0
        self._cache: OrderedDict[str, bytes] = OrderedDict()
        self._pending: dict[str, list[ThumbnailCallback]] = {}
        self._lock = Lock()
        self._generation = 0

    def new_generation(self) -> int:
        with self._lock:
            self._generation += 1
            return self._generation

    def request(
        self, key: str, path: Path | None, generation: int, callback: ThumbnailCallback
    ) -> None:
        with self._lock:
            cached = self._cache.get(key)
            if cached is not None:
                self._cache.move_to_end(key)
                callback(key, cached)
                return
            if key in self._pending:
                self._pending[key].append(callback)
                return
            self._pending[key] = [callback]
        future = self._pool.submit(lambda: None if path is None else path.read_bytes())
        future.add_done_callback(lambda f: self._complete(key, generation, f))

    def _complete(self, key: str, generation: int, future: Future[bytes | None]) -> None:
        try:
            data = future.result()
        except OSError:
            data = None
        with self._lock:
            callbacks = self._pending.pop(key, [])
            current = generation == self._generation
            if current and data is not None:
                self._cache[key] = data
                self._bytes += len(data)
                while self._bytes > self._max and self._cache:
                    _, old = self._cache.popitem(last=False)
                    self._bytes -= len(old)
        if current:
            for callback in callbacks:
                callback(key, data)

    def close(self) -> None:
        self._pool.shutdown(wait=True, cancel_futures=True)
