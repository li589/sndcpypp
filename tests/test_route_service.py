import os
import sys
import tempfile
import types
import unittest
from types import SimpleNamespace
from unittest.mock import patch

if "PyQt6" not in sys.modules:
    qtcore = types.ModuleType("PyQt6.QtCore")

    class QObject:
        def __init__(self, *args, **kwargs):
            pass

    class _Signal:
        def __init__(self, *args, **kwargs):
            self._slots = []

        def connect(self, slot):
            self._slots.append(slot)

        def emit(self, *args, **kwargs):
            for slot in list(self._slots):
                slot(*args, **kwargs)

    def pyqtSignal(*args, **kwargs):
        del args, kwargs
        return _Signal()

    qtcore.QObject = QObject
    qtcore.pyqtSignal = pyqtSignal
    pyqt6 = types.ModuleType("PyQt6")
    pyqt6.QtCore = qtcore
    sys.modules["PyQt6"] = pyqt6
    sys.modules["PyQt6.QtCore"] = qtcore

from app.domain.models.operation_requests import RoutingRequest
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
        self.started_names: list[str] = []

    def start(self, name, group=None, target=None, args=()):
        del group
        self.started_names.append(name)
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
    def __init__(self, values=None):
        self._values = {
            "port": "28200",
            "adb_path": r"D:\tools\adb\adb.exe",
            "player_path": "vlc.exe",
            "player_extra": "",
            "scrcpy_path": r"D:\tools\scrcpy\scrcpy.exe",
        }
        if values:
            self._values.update(values)

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
        if target_key == "restart_adb_start_cmd":
            return ["adb", "start-server"]
        if target_key == "restart_adb_kill_cmd":
            return ["adb", "kill-server"]
        if target_key == "start_video_scrcpy_cmd":
            return ["scrcpy", "-s", kwargs["device_serial"]]
        raise AssertionError(f"Unexpected target_key: {target_key}")


class _RecordingVideoCommandManager(_FakeCommandManager):
    def __init__(self):
        super().__init__()
        self.video_cmds: list[list[str]] = []

    def get_target_cmd(self, target_key: str, **kwargs):
        if target_key == "start_video_scrcpy_cmd":
            cmd = [
                "scrcpy",
                "-s",
                kwargs["device_serial"],
                "--video-bit-rate",
                str(kwargs["video_bitrate"]),
            ]
            if kwargs.get("max_size_flag"):
                cmd.extend([kwargs["max_size_flag"], kwargs["max_size_val"]])
            self.video_cmds.append(cmd)
            return cmd
        return super().get_target_cmd(target_key, **kwargs)


class _ExitedProc:
    def __init__(self, returncode=1):
        self.pid = 5678
        self._returncode = returncode
        self.returncode = returncode

    def poll(self):
        self.returncode = self._returncode
        return self._returncode

    def wait(self):
        self.returncode = self._returncode
        return self._returncode


class _ManagedProc(_ExitedProc):
    def __init__(self):
        super().__init__(returncode=None)

    def wait(self):
        if self._returncode is None:
            self._returncode = 1
        self.returncode = self._returncode
        return self._returncode


class _LogBackedProc(_ManagedProc):
    def __init__(self, stdout_log_path=None, stderr_log_path=None):
        super().__init__()
        self._debug_stdout_log_path = stdout_log_path
        self._debug_stderr_log_path = stderr_log_path


class _TransientRunningProc(_ExitedProc):
    def __init__(self):
        super().__init__(returncode=None)
        self._poll_count = 0

    def poll(self):
        self._poll_count += 1
        if self._poll_count < 4:
            self.returncode = None
            return None
        self._returncode = 0
        self.returncode = self._returncode
        return self._returncode

    def wait(self):
        self._returncode = 0
        self.returncode = self._returncode
        return self._returncode


class _StopAwareSupervisor:
    def __init__(self, registry: ProcessRegistry):
        self._registry = registry

    def kill_group(self, device_serial: str, group: str):
        reg = self._registry.ensure(device_serial)
        for proc in reg.get(group, []):
            proc._returncode = 1
            proc.returncode = 1
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

    def test_start_audio_route_aborts_when_adb_forward_fails(self):
        registry = ProcessRegistry()
        operations: list[tuple[str, bool]] = []
        logs: list[tuple[str, str]] = []
        service = RouteService(
            cmd_manager=_FakeCommandManager(),
            process_registry=registry,
            process_supervisor=ProcessSupervisor(registry),
            task_runner=_ImmediateTaskRunner(),
            run_adb_command=lambda cmd, desc: SimpleNamespace(
                returncode=1,
                stdout="",
                stderr="adb: error: cannot bind socket",
            ),
            probe_scrcpy_features=lambda: {
                "display_ori": False,
                "capture_ori": False,
                "lock_video_ori": False,
                "degrees": False,
            },
            is_running=lambda: True,
        )
        service.operation_completed.connect(lambda operation, success: operations.append((operation, success)))
        service.log_message.connect(lambda message, level: logs.append((message, level)))

        with patch.object(service, "_cleanup_audio_player_processes", return_value=[]), patch(
            "app.services.route_service.subprocess.Popen"
        ) as popen_mock, patch(
            "app.services.route_service.time.sleep",
            lambda _: None,
        ):
            service.start_audio_route("device-1", port=28200)

        popen_mock.assert_not_called()
        self.assertEqual(operations[-1], ("audio_route", False))
        self.assertTrue(any(level == "error" and "cannot bind socket" in message for message, level in logs))

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

    def test_build_video_attempt_plan_adds_fallback_for_original_size_and_high_bitrate(self):
        registry = ProcessRegistry()
        run_calls: list[tuple[list[str], str]] = []
        service = self._build_service(registry, run_calls)

        attempts = service._build_video_attempt_plan(8000, "原始", True)

        self.assertEqual(len(attempts), 2)
        self.assertEqual(attempts[0]["bitrate"], 8000)
        self.assertEqual(attempts[0]["max_size"], "原始")
        self.assertEqual(attempts[1]["bitrate"], 4000)
        self.assertEqual(attempts[1]["max_size"], "1280")
        self.assertEqual(attempts[1]["turn_screen_off"], False)

    def test_start_video_route_retries_with_second_command_after_retryable_failure(self):
        registry = ProcessRegistry()
        run_calls: list[tuple[list[str], str]] = []
        cmd_manager = _RecordingVideoCommandManager()
        task_runner = _DeferredVideoWatcherTaskRunner()
        service = RouteService(
            cmd_manager=cmd_manager,
            process_registry=registry,
            process_supervisor=ProcessSupervisor(registry),
            task_runner=task_runner,
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
        operations: list[tuple[str, bool]] = []
        service.operation_completed.connect(lambda operation, success: operations.append((operation, success)))

        first_proc = _ExitedProc()
        second_proc = _ManagedProc()
        popen_calls: list[list[str]] = []

        def fake_popen(cmd, **kwargs):
            del kwargs
            popen_calls.append(cmd)
            if len(popen_calls) == 1:
                return first_proc
            return second_proc

        with patch("app.services.route_service.subprocess.Popen", side_effect=fake_popen), patch(
            "app.services.route_service.time.sleep",
            lambda _: None,
        ), patch.object(
            service,
            "_build_video_attempt_plan",
            return_value=[
                {"bitrate": 8000, "max_size": "原始", "turn_screen_off": True, "reason": "requested"},
                {"bitrate": 4000, "max_size": "1280", "turn_screen_off": False, "reason": "fallback"},
            ],
        ), patch.object(
            service,
            "_wait_until_process_ready",
            side_effect=[False, True],
        ), patch.object(
            service,
            "_should_retry_video_launch",
            return_value=True,
        ), patch.object(
            service,
            "_read_debug_file",
            return_value="ERROR: Server connection failed",
        ):
            service.start_video_route("device-1", bitrate=8000, max_size="原始")

        self.assertIn(("video_route", True), operations)
        self.assertEqual(len(cmd_manager.video_cmds), 2)
        self.assertIn("--video-bit-rate", cmd_manager.video_cmds[0])
        self.assertIn("8000000", cmd_manager.video_cmds[0])
        self.assertIn("4000000", cmd_manager.video_cmds[1])
        self.assertIn("-m", cmd_manager.video_cmds[1])
        self.assertIn("1280", cmd_manager.video_cmds[1])

    def test_start_audio_route_uses_default_player_args_when_extra_is_empty(self):
        registry = ProcessRegistry()
        popen_calls: list[list[str]] = []
        service = RouteService(
            cmd_manager=_FakeCommandManager(),
            process_registry=registry,
            process_supervisor=ProcessSupervisor(registry),
            task_runner=_ImmediateTaskRunner(),
            run_adb_command=lambda cmd, desc: SimpleNamespace(returncode=0, stdout="", stderr=""),
            probe_scrcpy_features=lambda: {
                "display_ori": False,
                "capture_ori": False,
                "lock_video_ori": False,
                "degrees": False,
            },
            is_running=lambda: True,
        )

        with patch("app.services.route_service.subprocess.Popen", side_effect=lambda cmd, creationflags=0: popen_calls.append(cmd) or _TransientRunningProc()), patch(
            "app.services.route_service.time.sleep",
            lambda _: None,
        ):
            service.start_audio_route("device-1", port=28200)

        self.assertIn("-Idummy", popen_calls[0])
        self.assertEqual(popen_calls[0].count("-Idummy"), 1)
        self.assertEqual(popen_calls[0][-1], "tcp://localhost:28200")

    def test_start_audio_route_uses_custom_player_extra_without_duplicating_defaults(self):
        registry = ProcessRegistry()
        popen_calls: list[list[str]] = []
        service = RouteService(
            cmd_manager=_FakeCommandManager(
                values={"player_extra": "-Idummy --demux rawaud --network-caching=200 --play-and-exit"}
            ),
            process_registry=registry,
            process_supervisor=ProcessSupervisor(registry),
            task_runner=_ImmediateTaskRunner(),
            run_adb_command=lambda cmd, desc: SimpleNamespace(returncode=0, stdout="", stderr=""),
            probe_scrcpy_features=lambda: {
                "display_ori": False,
                "capture_ori": False,
                "lock_video_ori": False,
                "degrees": False,
            },
            is_running=lambda: True,
        )

        with patch("app.services.route_service.subprocess.Popen", side_effect=lambda cmd, creationflags=0: popen_calls.append(cmd) or _TransientRunningProc()), patch(
            "app.services.route_service.time.sleep",
            lambda _: None,
        ):
            service.start_audio_route("device-1", port=28200)

        self.assertEqual(popen_calls[0].count("-Idummy"), 1)
        self.assertEqual(popen_calls[0].count("--demux"), 1)

    def test_stop_audio_internal_uses_device_specific_saved_port(self):
        registry = ProcessRegistry()
        run_calls: list[tuple[list[str], str]] = []
        service = self._build_service(registry, run_calls)
        registry.ensure("device-1")["audio_port"] = 29000

        with patch.object(service, "_cleanup_audio_player_processes", return_value=[]):
            service._stop_audio_internal("device-1")

        self.assertIn("tcp:29000", run_calls[-1][0])

    def test_stop_audio_internal_cleans_fallback_audio_player_for_saved_port(self):
        registry = ProcessRegistry()
        run_calls: list[tuple[list[str], str]] = []
        logs: list[tuple[str, str]] = []
        service = self._build_service(registry, run_calls)
        service.log_message.connect(lambda message, level: logs.append((message, level)))
        registry.ensure("device-1")["audio_port"] = 29000

        with patch.object(service, "_cleanup_audio_player_processes", return_value=[4321]):
            service._stop_audio_internal("device-1")

        self.assertTrue(any(level == "warning" and "4321" in message for message, level in logs))

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

    def test_watch_video_process_cleans_debug_logs_after_exit(self):
        registry = ProcessRegistry()
        service = self._build_service(registry, [])
        proc = _ManagedProc()

        with tempfile.NamedTemporaryFile("w", delete=False, encoding="utf-8") as stdout_file, tempfile.NamedTemporaryFile(
            "w", delete=False, encoding="utf-8"
        ) as stderr_file:
            stdout_file.write("Renderer: direct3d11")
            stderr_file.write("")
            proc._debug_stdout_log_path = stdout_file.name
            proc._debug_stderr_log_path = stderr_file.name

        registry.register("device-1", "video", proc)
        service._watch_video_process("device-1", proc)

        self.assertFalse(os.path.exists(stdout_file.name))
        self.assertFalse(os.path.exists(stderr_file.name))

    def test_start_video_route_logs_record_permission_hint_before_success(self):
        registry = ProcessRegistry()
        task_runner = _DeferredVideoWatcherTaskRunner()
        logs: list[tuple[str, str]] = []
        operations: list[tuple[str, bool]] = []
        service = RouteService(
            cmd_manager=_FakeCommandManager(),
            process_registry=registry,
            process_supervisor=ProcessSupervisor(registry),
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
        service.operation_completed.connect(lambda operation, success: operations.append((operation, success)))

        with patch("app.services.route_service.subprocess.Popen", return_value=_ManagedProc()), patch(
            "app.services.route_service.time.sleep",
            lambda _: None,
        ):
            service.start_video_route("device-1")

        self.assertIn(("video_route", True), operations)
        self.assertTrue(any(level == "info" and "录屏授权" in message for message, level in logs))

    def test_start_video_route_uses_scrcpy_directory_as_cwd(self):
        registry = ProcessRegistry()
        popen_kwargs: list[dict] = []
        service = RouteService(
            cmd_manager=_FakeCommandManager(),
            process_registry=registry,
            process_supervisor=ProcessSupervisor(registry),
            task_runner=_DeferredVideoWatcherTaskRunner(),
            run_adb_command=lambda cmd, desc: SimpleNamespace(returncode=0, stdout="", stderr=""),
            probe_scrcpy_features=lambda: {
                "display_ori": False,
                "capture_ori": False,
                "lock_video_ori": False,
                "degrees": False,
            },
            is_running=lambda: True,
        )

        def _capture_popen(cmd, **kwargs):
            popen_kwargs.append(kwargs)
            return _ManagedProc()

        with patch.object(service, "_cleanup_stale_scrcpy_processes", return_value=[]), patch(
            "app.services.route_service.subprocess.Popen",
            side_effect=_capture_popen,
        ), patch(
            "app.services.route_service.time.sleep",
            lambda _: None,
        ), patch("app.services.route_service.os.path.isfile", return_value=True):
            service.start_video_route("device-1")

        self.assertEqual(popen_kwargs[0]["cwd"], r"D:\tools\scrcpy")

    def test_start_video_route_passes_configured_adb_via_env(self):
        registry = ProcessRegistry()
        popen_kwargs: list[dict] = []
        service = RouteService(
            cmd_manager=_FakeCommandManager(),
            process_registry=registry,
            process_supervisor=ProcessSupervisor(registry),
            task_runner=_DeferredVideoWatcherTaskRunner(),
            run_adb_command=lambda cmd, desc: SimpleNamespace(returncode=0, stdout="", stderr=""),
            probe_scrcpy_features=lambda: {
                "display_ori": False,
                "capture_ori": False,
                "lock_video_ori": False,
                "degrees": False,
            },
            is_running=lambda: True,
        )

        def _capture_popen(cmd, **kwargs):
            popen_kwargs.append(kwargs)
            return _ManagedProc()

        with patch.object(service, "_cleanup_stale_scrcpy_processes", return_value=[]), patch(
            "app.services.route_service.subprocess.Popen",
            side_effect=_capture_popen,
        ), patch(
            "app.services.route_service.time.sleep",
            lambda _: None,
        ), patch("app.services.route_service.os.path.isfile", return_value=True):
            service.start_video_route("device-1")

        self.assertEqual(popen_kwargs[0]["env"]["ADB"], r"D:\tools\adb\adb.exe")

    def test_start_video_route_cleans_stale_scrcpy_binary_before_spawn(self):
        registry = ProcessRegistry()
        service = RouteService(
            cmd_manager=_FakeCommandManager(),
            process_registry=registry,
            process_supervisor=ProcessSupervisor(registry),
            task_runner=_DeferredVideoWatcherTaskRunner(),
            run_adb_command=lambda cmd, desc: SimpleNamespace(returncode=0, stdout="", stderr=""),
            probe_scrcpy_features=lambda: {
                "display_ori": False,
                "capture_ori": False,
                "lock_video_ori": False,
                "degrees": False,
            },
            is_running=lambda: True,
        )
        cleaned: list[str] = []

        with patch.object(service, "_cleanup_stale_scrcpy_processes", side_effect=lambda path: cleaned.append(path) or [1234]), patch(
            "app.services.route_service.subprocess.Popen",
            return_value=_ManagedProc(),
        ), patch(
            "app.services.route_service.time.sleep",
            lambda _: None,
        ), patch("app.services.route_service.os.path.isfile", return_value=True):
            service.start_video_route("device-1")

        self.assertEqual(cleaned, [r"D:\tools\scrcpy\scrcpy.exe"])

    def test_start_video_route_prewarms_adb_server_before_spawn(self):
        registry = ProcessRegistry()
        run_calls: list[tuple[list[str], str]] = []
        popen_calls: list[list[str]] = []
        service = self._build_service(registry, run_calls)

        def _capture_popen(cmd, **kwargs):
            del kwargs
            popen_calls.append(cmd)
            return _ManagedProc()

        with patch.object(service, "_cleanup_stale_scrcpy_processes", return_value=[]), patch(
            "app.services.route_service.subprocess.Popen",
            side_effect=_capture_popen,
        ), patch(
            "app.services.route_service.time.sleep",
            lambda _: None,
        ), patch("app.services.route_service.os.path.isfile", return_value=True):
            service.start_video_route("device-1")

        self.assertEqual(run_calls[0][0], ["adb", "start-server"])
        self.assertEqual(popen_calls[0], ["scrcpy", "-s", "device-1"])

    def test_start_routing_session_runs_video_before_audio_in_single_background_task(self):
        registry = ProcessRegistry()
        task_runner = _DeferredVideoWatcherTaskRunner()
        service = RouteService(
            cmd_manager=_FakeCommandManager(),
            process_registry=registry,
            process_supervisor=ProcessSupervisor(registry),
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
        call_order: list[str] = []

        with patch.object(
            service,
            "_start_video_route_task",
            side_effect=lambda *args, **kwargs: call_order.append("video")
            or registry.register("device-1", "video", _LogBackedProc())
            or True,
        ), patch.object(
            service,
            "_wait_for_video_renderer",
            side_effect=lambda proc, device_serial: call_order.append(f"wait:{device_serial}") or True,
        ), patch.object(
            service,
            "_start_audio_route_task",
            side_effect=lambda *args, **kwargs: call_order.append("audio") or True,
        ):
            service.start_routing_session(
                RoutingRequest(
                    device_serial="device-1",
                    enable_audio=True,
                    enable_video=True,
                    audio_port=28200,
                )
            )

        self.assertEqual(task_runner.started_names[0], "route-start-routing-session")
        self.assertEqual(call_order, ["video", "wait:device-1", "audio"])

    def test_start_routing_session_skips_audio_until_video_renderer_is_detected(self):
        registry = ProcessRegistry()
        task_runner = _DeferredVideoWatcherTaskRunner()
        service = RouteService(
            cmd_manager=_FakeCommandManager(),
            process_registry=registry,
            process_supervisor=ProcessSupervisor(registry),
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
        logs: list[tuple[str, str]] = []
        service.log_message.connect(lambda message, level: logs.append((message, level)))

        with patch.object(
            service,
            "_start_video_route_task",
            side_effect=lambda *args, **kwargs: registry.register("device-1", "video", _LogBackedProc()) or True,
        ), patch.object(
            service,
            "_wait_for_video_renderer",
            return_value=False,
        ), patch.object(
            service,
            "_start_audio_route_task",
        ) as audio_mock:
            service.start_routing_session(
                RoutingRequest(
                    device_serial="device-1",
                    enable_audio=True,
                    enable_video=True,
                    audio_port=28200,
                )
            )

        audio_mock.assert_not_called()
        self.assertTrue(any(level == "warning" and "暂停自动启动音频" in message for message, level in logs))


if __name__ == "__main__":
    unittest.main()
