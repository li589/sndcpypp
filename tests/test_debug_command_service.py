import unittest
from types import SimpleNamespace
from unittest.mock import patch

from app.infrastructure.adb.adb_client import ADBClient
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

    def test_unknown_command_type_emits_error_log(self):
        task_runner = _QueuedTaskRunner()
        cmd_manager = _FakeCommandManager()
        adb_client = _FakeADBClient()
        service = DebugCommandService(cmd_manager, adb_client, task_runner)
        logs: list[tuple[str, str]] = []
        service.log_message.connect(lambda message, level: logs.append((message, level)))

        service.execute_custom_cmd("", "echo hi", "unknown")
        task_runner.tasks.pop(0)()

        self.assertEqual(adb_client.calls, [])
        self.assertTrue(any(level == "error" and "未知命令类型" in message for message, level in logs))

    def test_invalid_shell_syntax_emits_error_log(self):
        task_runner = _QueuedTaskRunner()
        cmd_manager = _FakeCommandManager()
        adb_client = _FakeADBClient()
        service = DebugCommandService(cmd_manager, adb_client, task_runner)
        logs: list[tuple[str, str]] = []
        service.log_message.connect(lambda message, level: logs.append((message, level)))

        service.execute_custom_cmd("", "\"unterminated", "adb")
        task_runner.tasks.pop(0)()

        self.assertEqual(adb_client.calls, [])
        self.assertTrue(any(level == "error" and "命令解析失败" in message for message, level in logs))


class ADBClientTests(unittest.TestCase):
    def test_run_logged_resolves_cwd_from_path_executable(self):
        logs: list[tuple[str, str]] = []
        client = ADBClient(lambda message, level: logs.append((message, level)))
        completed = SimpleNamespace(returncode=0, stdout="", stderr="")

        with patch(
            "app.infrastructure.adb.adb_client.os.path.isfile",
            side_effect=lambda path: path == r"C:\tools\adb\adb.exe",
        ), patch(
            "app.infrastructure.adb.adb_client.shutil.which",
            return_value=r"C:\tools\adb\adb.exe",
        ), patch(
            "app.infrastructure.adb.adb_client.subprocess.run",
            return_value=completed,
        ) as mock_run:
            result = client.run_logged(["adb", "version"], "测试命令")

        self.assertIs(result, completed)
        self.assertEqual(mock_run.call_args.kwargs["cwd"], r"C:\tools\adb")


if __name__ == "__main__":
    unittest.main()
