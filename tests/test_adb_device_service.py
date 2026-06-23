import unittest
from types import SimpleNamespace
from unittest.mock import patch

from app.services.adb_device_service import ADBDeviceService


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
            "player_path": "player.exe",
            "sndcpy_dir": r"C:\sndcpy",
            "scrcpy_path": "",
            "apk_path": "",
        }
        if values:
            self._values.update(values)

    def get_variable(self, key: str) -> str:
        return self._values.get(key, "")

    def update_variable(self, key: str, value: str) -> None:
        self._values[key] = str(value)

    def get_target_cmd(self, target_key: str, **kwargs):
        if target_key == "refresh_devices_cmd":
            return ["adb", "devices"]
        if target_key == "install_apk_direct_install_cmd":
            return ["adb", "-s", kwargs["device_serial"], "install", "direct"]
        if target_key == "uninstall_apk_cmd":
            return ["adb", "-s", kwargs["device_serial"], "uninstall", "com.rom1v.sndcpy"]
        if target_key == "install_apk_install_cmd":
            return ["adb", "-s", kwargs["device_serial"], "install", "retry"]
        raise AssertionError(f"Unexpected command: {target_key}")


class ADBDeviceServiceTests(unittest.TestCase):
    def test_refresh_devices_queues_one_follow_up_refresh(self):
        task_runner = _QueuedTaskRunner()
        calls: list[str] = []
        service = ADBDeviceService(
            cmd_manager=_FakeCommandManager(),
            run_adb_command=lambda cmd, desc: calls.append(desc) or SimpleNamespace(
                returncode=0,
                stdout="List of devices attached\nserial-1\tdevice\n",
                stderr="",
            ),
            task_runner=task_runner,
        )

        service.refresh_devices()
        service.refresh_devices()

        self.assertEqual(len(task_runner.tasks), 1)

        first_task = task_runner.tasks.pop(0)
        first_task()

        self.assertEqual(len(task_runner.tasks), 1)

        second_task = task_runner.tasks.pop(0)
        second_task()

        self.assertEqual(calls, ["刷新设备列表", "刷新设备列表"])
        self.assertFalse(service._is_refreshing)
        self.assertFalse(service._refresh_pending)

    def test_refresh_devices_does_not_emit_empty_list_when_retry_still_fails(self):
        task_runner = _QueuedTaskRunner()
        emitted_devices: list[list[str]] = []
        logs: list[tuple[str, str]] = []
        service = ADBDeviceService(
            cmd_manager=_FakeCommandManager(),
            run_adb_command=lambda cmd, desc: SimpleNamespace(
                returncode=1,
                stdout="",
                stderr="adb failed",
            ),
            task_runner=task_runner,
        )
        service.devices_updated.connect(lambda devices: emitted_devices.append(devices))
        service.log_message.connect(lambda message, level: logs.append((message, level)))

        service.refresh_devices()

        with patch("app.services.adb_device_service.time.sleep", lambda _: None):
            task_runner.tasks.pop(0)()

        self.assertEqual(emitted_devices, [])
        self.assertTrue(any(level == "error" and "本次结果已忽略" in message for message, level in logs))
        self.assertFalse(service._is_refreshing)

    def test_validate_paths_clears_stale_runtime_paths_when_sndcpy_dir_is_invalid(self):
        task_runner = _QueuedTaskRunner()
        validation_results: list[list[int]] = []
        cmd_manager = _FakeCommandManager(
            values={
                "sndcpy_dir": r"C:\broken-sndcpy",
                "scrcpy_path": "old_scrcpy.exe",
                "apk_path": "old.apk",
            }
        )
        service = ADBDeviceService(
            cmd_manager=cmd_manager,
            run_adb_command=lambda cmd, desc: None,
            task_runner=task_runner,
        )
        service.validation_result.connect(lambda results: validation_results.append(results))

        def _fake_isfile(path: str) -> bool:
            return path in {"adb.exe", "player.exe"}

        with patch("app.services.adb_device_service.os.path.isfile", side_effect=_fake_isfile), patch(
            "app.services.adb_device_service.os.access", return_value=True
        ), patch("app.services.adb_device_service.shutil.which", return_value=None), patch(
            "app.services.adb_device_service.os.path.isdir", return_value=False
        ):
            service.validate_paths()
            task_runner.tasks.pop(0)()

        self.assertEqual(validation_results, [[1, 1, 0]])
        self.assertEqual(cmd_manager.get_variable("scrcpy_path"), "")
        self.assertEqual(cmd_manager.get_variable("apk_path"), "")

    def test_install_apk_retries_when_install_failure_is_reported_in_stderr(self):
        task_runner = _QueuedTaskRunner()
        calls: list[str] = []
        completed: list[tuple[str, bool]] = []
        logs: list[tuple[str, str]] = []
        responses = {
            "直接安装APK (device-1)": SimpleNamespace(
                returncode=1,
                stdout="",
                stderr="Failure [INSTALL_FAILED_UPDATE_INCOMPATIBLE]",
            ),
            "卸载旧版本": SimpleNamespace(returncode=0, stdout="Success", stderr=""),
            "重新安装APK": SimpleNamespace(returncode=0, stdout="Success", stderr=""),
        }
        service = ADBDeviceService(
            cmd_manager=_FakeCommandManager(),
            run_adb_command=lambda cmd, desc: calls.append(desc) or responses[desc],
            task_runner=task_runner,
        )
        service.operation_completed.connect(lambda operation, success: completed.append((operation, success)))
        service.log_message.connect(lambda message, level: logs.append((message, level)))

        service.install_apk("device-1")
        task_runner.tasks.pop(0)()

        self.assertEqual(calls, ["直接安装APK (device-1)", "卸载旧版本", "重新安装APK"])
        self.assertEqual(completed, [("install", True)])
        self.assertTrue(any(level == "warning" and "尝试卸载旧版本并重新安装" in message for message, level in logs))

    def test_install_apk_reports_failure_without_retry_for_generic_adb_error(self):
        task_runner = _QueuedTaskRunner()
        calls: list[str] = []
        completed: list[tuple[str, bool]] = []
        logs: list[tuple[str, str]] = []
        service = ADBDeviceService(
            cmd_manager=_FakeCommandManager(),
            run_adb_command=lambda cmd, desc: calls.append(desc)
            or SimpleNamespace(returncode=1, stdout="", stderr="adb: error: device offline"),
            task_runner=task_runner,
        )
        service.operation_completed.connect(lambda operation, success: completed.append((operation, success)))
        service.log_message.connect(lambda message, level: logs.append((message, level)))

        service.install_apk("device-1")
        task_runner.tasks.pop(0)()

        self.assertEqual(calls, ["直接安装APK (device-1)"])
        self.assertEqual(completed, [("install", False)])
        self.assertTrue(any(level == "error" and "device offline" in message for message, level in logs))


if __name__ == "__main__":
    unittest.main()
