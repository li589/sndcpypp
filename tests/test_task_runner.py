import threading
import time
import unittest
from unittest.mock import patch

from app.infrastructure.process.task_runner import BackgroundTaskRunner


class BackgroundTaskRunnerTests(unittest.TestCase):
    def _wait_for_status(self, runner: BackgroundTaskRunner, task_name: str, expected: str, timeout: float = 1.0):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            snapshot = runner.get_task(task_name)
            if snapshot is not None and snapshot.status == expected:
                return snapshot
            time.sleep(0.01)
        self.fail(f"Task {task_name} did not reach status {expected!r}")

    def test_snapshot_tracks_running_and_completed_task(self):
        runner = BackgroundTaskRunner(prefix="test-bg")
        release_event = threading.Event()

        thread = runner.start(name="demo", group="demo-group", target=release_event.wait)

        running = self._wait_for_status(runner, thread.name, "running")
        self.assertTrue(running.is_alive)
        self.assertEqual(running.display_name, "demo")
        self.assertEqual(running.group, "demo-group")

        release_event.set()
        self.assertTrue(runner.wait_all(timeout=1))

        completed = self._wait_for_status(runner, thread.name, "completed")
        self.assertFalse(completed.is_alive)
        self.assertIsNotNone(completed.started_at)
        self.assertIsNotNone(completed.finished_at)
        self.assertIsNone(completed.error_text)

    def test_wait_all_returns_false_when_timeout_expires(self):
        runner = BackgroundTaskRunner(prefix="test-bg")
        release_event = threading.Event()

        runner.start(name="slow", target=release_event.wait)

        self.assertFalse(runner.wait_all(timeout=0.05))
        release_event.set()
        self.assertTrue(runner.wait_all(timeout=1))

    def test_snapshot_tracks_failed_task(self):
        runner = BackgroundTaskRunner(prefix="test-bg")

        def _boom():
            raise RuntimeError("boom")

        with patch("threading.excepthook", lambda args: None):
            thread = runner.start(name="boom", target=_boom)
            self.assertTrue(runner.wait_all(timeout=1))

        failed = self._wait_for_status(runner, thread.name, "failed")
        self.assertFalse(failed.is_alive)
        self.assertIn("RuntimeError: boom", failed.error_text or "")

    def test_recent_failed_tasks_and_clear_history(self):
        runner = BackgroundTaskRunner(prefix="test-bg")

        def _boom():
            raise RuntimeError("boom")

        with patch("threading.excepthook", lambda args: None):
            ok_thread = runner.start(name="ok", group="alpha", target=lambda: None)
            fail_thread = runner.start(name="boom", group="alpha", target=_boom)
            self.assertTrue(runner.wait_all(timeout=1))

        grouped = runner.snapshot_by_group()
        self.assertIn("alpha", grouped)
        self.assertEqual({task.name for task in grouped["alpha"]}, {ok_thread.name, fail_thread.name})

        recent_failed = runner.recent_failed_tasks(limit=5)
        self.assertEqual(len(recent_failed), 1)
        self.assertEqual(recent_failed[0].name, fail_thread.name)

        removed = runner.clear_history(group="alpha", only_completed=True)
        self.assertEqual(removed, 1)
        self.assertIsNone(runner.get_task(ok_thread.name))
        self.assertIsNotNone(runner.get_task(fail_thread.name))

    def test_listener_receives_failed_task_snapshot(self):
        runner = BackgroundTaskRunner(prefix="test-bg")
        observed: list[tuple[str, str, str | None]] = []

        def _listener(task):
            if task.status == "failed":
                observed.append((task.group, task.display_name, task.error_text))

        runner.add_listener(_listener)

        def _boom():
            raise ValueError("listener-boom")

        with patch("threading.excepthook", lambda args: None):
            runner.start(name="boom", group="observer", target=_boom)
            self.assertTrue(runner.wait_all(timeout=1))

        self.assertEqual(len(observed), 1)
        self.assertEqual(observed[0][0], "observer")
        self.assertEqual(observed[0][1], "boom")
        self.assertIn("ValueError: listener-boom", observed[0][2] or "")


if __name__ == "__main__":
    unittest.main()
