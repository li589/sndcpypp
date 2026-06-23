import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Literal


TaskStatus = Literal["starting", "running", "completed", "failed"]


@dataclass(frozen=True)
class TaskSnapshot:
    name: str
    display_name: str
    group: str
    daemon: bool
    status: TaskStatus
    is_alive: bool
    started_at: float | None
    finished_at: float | None
    error_text: str | None


class BackgroundTaskRunner:
    """统一创建后台线程，便于后续继续收口和观察任务分布。"""

    def __init__(self, prefix: str = "sndcpy-bg"):
        self._prefix = prefix
        self._counter = 0
        self._lock = threading.Lock()
        self._threads: dict[str, threading.Thread] = {}
        self._tasks: dict[str, dict[str, Any]] = {}
        self._failed_task_names: list[str] = []
        self._listeners: list[Callable[[TaskSnapshot], None]] = []

    def start(
        self,
        *,
        name: str,
        group: str = "default",
        target: Callable[..., Any],
        args: tuple[Any, ...] = (),
        kwargs: dict[str, Any] | None = None,
        daemon: bool = True,
    ) -> threading.Thread:
        with self._lock:
            self._prune_locked()
            self._counter += 1
            thread_name = f"{self._prefix}:{name}:{self._counter}"
            task_state = {
                "name": thread_name,
                "display_name": name,
                "group": group,
                "daemon": daemon,
                "status": "starting",
                "started_at": None,
                "finished_at": None,
                "error_text": None,
                "last_notified_status": None,
            }
            self._tasks[thread_name] = task_state
            thread = threading.Thread(
                name=thread_name,
                target=self._run_task,
                args=(thread_name, target, args, kwargs or {}),
                daemon=daemon,
            )
            self._threads[thread_name] = thread

        thread.start()
        self._notify_listeners_for_task(thread_name)
        return thread

    def list_running(self) -> list[str]:
        return [task.name for task in self.snapshot(include_completed=False)]

    def snapshot(self, *, include_completed: bool = True) -> list[TaskSnapshot]:
        with self._lock:
            self._prune_locked()
            snapshots: list[TaskSnapshot] = []
            for name in sorted(self._tasks.keys()):
                state = self._tasks[name]
                thread = self._threads.get(name)
                is_alive = bool(thread and thread.is_alive())
                if not include_completed and not is_alive:
                    continue
                snapshots.append(
                    TaskSnapshot(
                        name=name,
                        display_name=str(state["display_name"]),
                        group=str(state["group"]),
                        daemon=bool(state["daemon"]),
                        status=state["status"],
                        is_alive=is_alive,
                        started_at=state["started_at"],
                        finished_at=state["finished_at"],
                        error_text=state["error_text"],
                    )
                )
            return snapshots

    def get_task(self, name: str) -> TaskSnapshot | None:
        for task in self.snapshot(include_completed=True):
            if task.name == name:
                return task
        return None

    def add_listener(self, listener: Callable[[TaskSnapshot], None]) -> None:
        with self._lock:
            if listener not in self._listeners:
                self._listeners.append(listener)

    def remove_listener(self, listener: Callable[[TaskSnapshot], None]) -> None:
        with self._lock:
            self._listeners = [current for current in self._listeners if current != listener]

    def snapshot_by_group(self, *, include_completed: bool = True) -> dict[str, list[TaskSnapshot]]:
        grouped: dict[str, list[TaskSnapshot]] = {}
        for task in self.snapshot(include_completed=include_completed):
            grouped.setdefault(task.group, []).append(task)
        return grouped

    def recent_failed_tasks(self, limit: int = 10) -> list[TaskSnapshot]:
        with self._lock:
            self._prune_locked()
            failed_names = list(self._failed_task_names[-limit:])

        tasks: list[TaskSnapshot] = []
        for name in reversed(failed_names):
            task = self.get_task(name)
            if task is not None:
                tasks.append(task)
        return tasks

    def clear_history(
        self,
        *,
        group: str | None = None,
        keep_failed: bool = True,
        only_completed: bool = False,
    ) -> int:
        with self._lock:
            self._prune_locked()
            removable_names: list[str] = []
            for name, state in self._tasks.items():
                thread = self._threads.get(name)
                is_alive = bool(thread and thread.is_alive())
                if is_alive:
                    continue
                if group is not None and state["group"] != group:
                    continue
                if keep_failed and state["status"] == "failed":
                    continue
                if only_completed and state["status"] != "completed":
                    continue
                removable_names.append(name)

            for name in removable_names:
                self._tasks.pop(name, None)

            removable_name_set = set(removable_names)
            if removable_name_set:
                self._failed_task_names = [
                    name for name in self._failed_task_names if name not in removable_name_set
                ]
            return len(removable_names)

    def wait_all(self, timeout: float | None = None) -> bool:
        deadline = None if timeout is None else time.monotonic() + timeout
        while True:
            with self._lock:
                self._prune_locked()
                threads = [thread for thread in self._threads.values() if thread.is_alive()]

            if not threads:
                return True

            for thread in threads:
                remaining = None if deadline is None else max(0.0, deadline - time.monotonic())
                if remaining == 0:
                    return False
                thread.join(timeout=remaining)

            if deadline is not None and time.monotonic() >= deadline:
                with self._lock:
                    self._prune_locked()
                    return not any(thread.is_alive() for thread in self._threads.values())

    def _run_task(
        self,
        thread_name: str,
        target: Callable[..., Any],
        args: tuple[Any, ...],
        kwargs: dict[str, Any],
    ) -> None:
        self._set_task_state(
            thread_name,
            status="running",
            started_at=time.time(),
            finished_at=None,
            error_text=None,
        )
        self._notify_listeners_for_task(thread_name)
        try:
            target(*args, **kwargs)
        except Exception as exc:
            self._set_task_state(
                thread_name,
                status="failed",
                finished_at=time.time(),
                error_text=f"{type(exc).__name__}: {exc}",
            )
            with self._lock:
                self._failed_task_names.append(thread_name)
            self._notify_listeners_for_task(thread_name)
            raise
        else:
            self._set_task_state(
                thread_name,
                status="completed",
                finished_at=time.time(),
                error_text=None,
            )
            self._notify_listeners_for_task(thread_name)

    def _set_task_state(self, thread_name: str, **updates: Any) -> None:
        with self._lock:
            task_state = self._tasks.get(thread_name)
            if task_state is None:
                return
            task_state.update(updates)

    def _prune_locked(self) -> None:
        completed = [name for name, thread in self._threads.items() if not thread.is_alive()]
        for name in completed:
            del self._threads[name]

    def _notify_listeners_for_task(self, thread_name: str) -> None:
        with self._lock:
            state = self._tasks.get(thread_name)
            if state is None:
                return
            current_status = state["status"]
            if state.get("last_notified_status") == current_status:
                return
            state["last_notified_status"] = current_status
            listeners = list(self._listeners)
        snapshot = self.get_task(thread_name)
        if snapshot is None:
            return
        for listener in listeners:
            try:
                listener(snapshot)
            except Exception:
                continue
