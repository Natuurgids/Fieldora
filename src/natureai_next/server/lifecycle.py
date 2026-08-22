"""Coordinated SIGTERM/SIGINT handling for rolling upgrades."""

from __future__ import annotations

import signal
import threading
from collections.abc import Callable, Iterator
from contextlib import contextmanager


class ShutdownCoordinator:
    def __init__(self, callbacks: tuple[Callable[[], None], ...] = ()) -> None:
        self._callbacks = callbacks
        self._requested = threading.Event()
        self._lock = threading.Lock()

    @property
    def requested(self) -> bool:
        return self._requested.is_set()

    def wait(self, timeout: float) -> bool:
        return self._requested.wait(timeout)

    def request(self) -> None:
        with self._lock:
            if self._requested.is_set():
                return
            self._requested.set()
            for callback in self._callbacks:
                callback()

    @contextmanager
    def installed(self) -> Iterator[ShutdownCoordinator]:
        if threading.current_thread() is not threading.main_thread():
            yield self
            return
        previous = {
            signum: signal.getsignal(signum)
            for signum in (signal.SIGTERM, signal.SIGINT)
        }

        def handle(_signum, _frame) -> None:
            self.request()

        try:
            for signum in previous:
                signal.signal(signum, handle)
            yield self
        finally:
            for signum, handler in previous.items():
                signal.signal(signum, handler)
