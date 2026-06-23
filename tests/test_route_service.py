import unittest
from types import SimpleNamespace
from unittest.mock import patch

from app.infrastructure.process.registry import ProcessRegistry
from app.infrastructure.process.supervisor import ProcessSupervisor
from app.services.route_service import RouteService


class _ImmediateTaskRunner:
    def start(self, name, group=None, target=None, args=()):
        del name, group
        if target is not None:
            target(*args)
        return SimpleNamespace()


class _DeferredVideoWatcherTaskRunner:
    def __init__(self):
        self._deferred: list[tuple[object, tuple]] = []

    def start(self, name, group=None, target=None, args=()):
        del group
        if target is None:
            return SimpleNamespace()
        if name == "route-watch-video":
            self._deferred.append((target, args))
        else:
            target(*args)
        return SimpleNamespace()

    def run_deferred(self):
        queued = list(self._deferred)
        self._deferred.clear()
        for target, args in queued:
            target(*args)


class _FakeCommandManager:
    def __init__(self):
        self._values = {"port": "28200"}

    def get_variable(self, key: str) -> str:
        return self._values.get(key, "")

    def get_target_cmd(self, target_key: str, **kwargs):
        if target_key == "start_audio_forward_cmd":
            return ["adb", "forward", f"tcp:{kwargs['port']}"]
        if target_key == "remove_audio_forward_cmd":
            return ["adb", "forward", "--remove", f"tcp:{kwargs['port']}"]
        if target_key == "start_audio_start_cmd":
            return ["adb", "shell", "am", "start"]
        if target_key == "stop_audio_app_cmd":
            return ["adb", "shell", "am", "force-stop"]
        if target_key == "start_audio_player_cmd":
            return ["vlc", f"tcp://localhost:{kwargs['port']}"]
        if target_key == "start_video_scrcpy_cmd":
            return ["scrcpy", "-s", kwargs["device_serial"]]
        raise AssertionError(f"Unexpected target_key: {target_key}")


class _ExitedProc:
    def __init__(self, returncode=1):
        self.pid = 5678
        self._returncode = returncode

    def poll(self):
        return self._returncode

    def wait(self):
        return self._returncode


class _ManagedProc(_ExitedProc):
    def __init__(self):
        super().__init__(returncode=None)

    def wait(self):
        if self._returncode is None:
            self._returncode = 1
        return self._returncode


class _StopAwareSupervisor:
    def __init__(self, registry: ProcessRegistry):
        self._registry = registry

    def kill_group(self, device_serial: str, group: str):
        reg = self._registry.ensure(device_serial)
        for proc in reg.get(group, []):
            proc._returncode = 1
        reg[group].clear()

    def remove_if_present(self, device_serial: str, group: str, proc):
        reg = self._registry.ensure(device_serial)
        if proc in reg.get(group, []):
            reg[group].remove(proc)


class RouteServiceTests(unittest.TestCase):
    def _build_service(self, registry: ProcessRegistry, run_calls: list[tuple[list[str], str]]) -> RouteService:
        return RouteService(
            cmd_manager=_FakeCommandManager(),
            process_registry=registry,
            process_supervisor=ProcessSupervisor(registry),
            task_runner=_ImmediateTaskRunner(),
            run_adb_command=lambda cmd, desc: run_calls.append((cmd, desc)) or SimpleNamespace(
                returncode=0,
                stdout="",
                stderr="",
            ),
            probe_scrcpy_features=lambda: {
                "display_ori": False,
                "capture_ori": False,
                "lock_video_ori": False,
                "degrees": False,
            },
            is_running=lambda: True,
        )

    def test_start_audio_route_reports_failure_when_player_exits_immediately(self):
        registry = ProcessRegistry()
        run_calls: list[tuple[list[str], str]] = []
        service = self._build_service(registry, run_calls)
        operations: list[tuple[str, bool]] = []
        service.operation_completed.connect(lambda operation, success: operations.append((operation, success)))

        with patch("app.services.route_service.subprocess.Popen", return_value=_ExitedProc()), patch(
            "app.services.route_service.time.sleep",
            lambda _: None,
        ):
            service.start_audio_route("device-1", port=28200)

        self.assertEqual(operations[-1], ("audio_route", False))

    def test_start_video_route_reports_failure_when_scrcpy_exits_immediately(self):
        registry = ProcessRegistry()
        run_calls: list[tuple[list[str], str]] = []
        service = self._build_service(registry, run_calls)
        operations: list[tuple[str, bool]] = []
        service.operation_completed.connect(lambda operation, success: operations.append((operation, success)))

        with patch("app.services.route_service.subprocess.Popen", return_value=_ExitedProc()), patch(
            "app.services.route_service.time.sleep",
            lambda _: None,
        ):
            service.start_video_route("device-1")

        self.assertEqual(operations[-1], ("video_route", False))

    def test_stop_audio_internal_uses_device_specific_saved_port(self):
        registry = ProcessRegistry()
        run_calls: list[tuple[list[str], str]] = []
        service = self._build_service(registry, run_calls)
        registry.ensure("device-1")["audio_port"] = 29000

        service._stop_audio_internal("device-1")

        self.assertIn("tcp:29000", run_calls[-1][0])

    def test_stop_streaming_does_not_warn_for_intentional_video_stop(self):
        registry = ProcessRegistry()
        task_runner = _DeferredVideoWatcherTaskRunner()
        logs: list[tuple[str, str]] = []
        service = RouteService(
            cmd_manager=_FakeCommandManager(),
            process_registry=registry,
            process_supervisor=_StopAwareSupervisor(registry),
            task_runner=task_runner,
            run_adb_command=lambda cmd, desc: SimpleNamespace(returncode=0, stdout="", stderr=""),
            probe_scrcpy_features=lambda: {
                "display_ori": False,
                "capture_ori": False,
                "lock_video_ori": False,
                "degrees": False,
            },
            is_running=lambda: True,
        )
        service.log_message.connect(lambda message, level: logs.append((message, level)))
        proc = _ManagedProc()

        with patch("app.services.route_service.subprocess.Popen", return_value=proc), patch(
            "app.services.route_service.time.sleep",
            lambda _: None,
        ):
            service.start_video_route("device-1")

        service.stop_streaming("device-1")
        task_runner.run_deferred()

        self.assertFalse(any("异常退出" in message for message, _level in logs))


if __name__ == "__main__":
    unittest.main()
