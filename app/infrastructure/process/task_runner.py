import threading
from collections.abc import Callable
from typing import Any


class BackgroundTaskRunner:
    """统一创建后台线程，便于后续继续收口和观察任务分布。"""

    def __init__(self, prefix: str = "sndcpy-bg"):
        self._prefix = prefix
        self._counter = 0
        self._lock = threading.Lock()
        self._threads: dict[str, threading.Thread] = {}

    def start(
        self,
        *,
        name: str,
        target: Callable[..., Any],
        args: tuple[Any, ...] = (),
        kwargs: dict[str, Any] | None = None,
        daemon: bool = True,
    ) -> threading.Thread:
        with self._lock:
            self._prune_locked()
            self._counter += 1
            thread_name = f"{self._prefix}:{name}:{self._counter}"
            thread = threading.Thread(
                name=thread_name,
                target=target,
                args=args,
                kwargs=kwargs or {},
                daemon=daemon,
            )
            self._threads[thread_name] = thread

        thread.start()
        return thread

    def list_running(self) -> list[str]:
        with self._lock:
            self._prune_locked()
            return sorted(self._threads.keys())

    def _prune_locked(self) -> None:
        completed = [name for name, thread in self._threads.items() if not thread.is_alive()]
        for name in completed:
            del self._threads[name]
