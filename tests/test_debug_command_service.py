import unittest
from types import SimpleNamespace

from app.services.debug_command_service import DebugCommandService


class _QueuedTaskRunner:
    def __init__(self):
        self.tasks: list[callable] = []

    def start(self, name, group=None, target=None, args=()):
        del name, group
        if target is not None:
            self.tasks.append(lambda: target(*args))
        return SimpleNamespace()


class _FakeCommandManager:
    def __init__(self, values=None):
        self._values = {
            "adb_path": "adb.exe",
            "adb_extra": "",
            "sndcpy_dir": r"C:\sndcpy",
            "scrcpy_path": r"C:\scrcpy\scrcpy.exe",
        }
        if values:
            self._values.update(values)

    def get_variable(self, key: str) -> str:
        return self._values.get(key, "")


class _FakeADBClient:
    def __init__(self):
        self.calls: list[tuple] = []

    def run_logged(
        self,
        command: list,
        description: str = "",
        cwd: str = None,
        timeout_seconds: float | None = 15,
    ):
        self.calls.append((command, description, cwd, timeout_seconds))
        return SimpleNamespace(returncode=0, stdout="", stderr="")


class DebugCommandServiceTests(unittest.TestCase):
    def test_execute_custom_adb_command_passes_no_timeout(self):
        task_runner = _QueuedTaskRunner()
        cmd_manager = _FakeCommandManager()
        adb_client = _FakeADBClient()
        service = DebugCommandService(cmd_manager, adb_client, task_runner)

        service.execute_custom_cmd("device-1", "shell ls -la", "adb")

        self.assertEqual(len(task_runner.tasks), 1)
        task_runner.tasks.pop(0)()

        self.assertEqual(len(adb_client.calls), 1)
        cmd, desc, cwd, timeout = adb_client.calls[0]
        self.assertEqual(desc, "自定义命令")
        self.assertEqual(timeout, None)

    def test_execute_custom_scrcpy_command_passes_no_timeout(self):
        task_runner = _QueuedTaskRunner()
        cmd_manager = _FakeCommandManager()
        adb_client = _FakeADBClient()
        service = DebugCommandService(cmd_manager, adb_client, task_runner)

        service.execute_custom_cmd("", "--window-title test", "scrcpy")

        self.assertEqual(len(task_runner.tasks), 1)
        task_runner.tasks.pop(0)()

        self.assertEqual(len(adb_client.calls), 1)
        cmd, desc, cwd, timeout = adb_client.calls[0]
        self.assertEqual(desc, "[scrcpy命令]")
        self.assertEqual(timeout, None)

    def test_internal_compatibility_layer_uses_default_timeout(self):
        adb_client = _FakeADBClient()
        adb_client.run_logged(["echo", "test"], "测试")
        self.assertEqual(adb_client.calls[0][3], 15)


if __name__ == "__main__":
    unittest.main()
