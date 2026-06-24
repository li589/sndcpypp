import unittest
from types import SimpleNamespace
from unittest.mock import patch

from app.domain.models.operation_requests import RecordingState
from app.infrastructure.process.registry import ProcessRegistry
from app.infrastructure.process.supervisor import ProcessSupervisor
from app.services.recording_service import RecordingService


class _ImmediateTaskRunner:
    def start(self, name, group=None, target=None, args=()):
        del group
        if target is not None:
            target(*args)
        return SimpleNamespace(name=name)


class _DeferredMonitorTaskRunner:
    def __init__(self):
        self._deferred: list[tuple[object, tuple]] = []

    def start(self, name, group=None, target=None, args=()):
        del group
        if target is None:
            return SimpleNamespace(name=name)
        if name == "record-monitor-and-restore":
            self._deferred.append((target, args))
        else:
            target(*args)
        return SimpleNamespace(name=name)

    def run_deferred(self):
        queued = list(self._deferred)
        self._deferred.clear()
        for target, args in queued:
            target(*args)


class _FakeCommandManager:
    def __init__(self):
        self._values = {
            "scrcpy_path": "scrcpy.exe",
            "scrcpy_extra": "",
        }

    def get_variable(self, key: str) -> str:
        return self._values.get(key, "")


class _FakeProc:
    def __init__(self):
        self.pid = 4321
        self._returncode = None

    def poll(self):
        return self._returncode

    def wait(self):
        self._returncode = 0
        return 0


class _FailingProc(_FakeProc):
    def __init__(self, returncode=1, on_wait=None):
        super().__init__()
        self._failing_returncode = returncode
        self._on_wait = on_wait

    def wait(self):
        if self._on_wait is not None:
            self._on_wait()
        self._returncode = self._failing_returncode
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


class RecordingServiceTests(unittest.TestCase):
    def _build_service(self, registry: ProcessRegistry) -> RecordingService:
        return RecordingService(
            cmd_manager=_FakeCommandManager(),
            process_registry=registry,
            process_supervisor=ProcessSupervisor(registry),
            task_runner=_ImmediateTaskRunner(),
            probe_scrcpy_features=lambda: {
                "record_ori": False,
                "capture_ori": False,
                "lock_video_ori": False,
                "degrees": False,
                "no_playback": "--no-playback",
            },
            start_audio_route=lambda device, port: None,
            stop_audio=lambda device: None,
            is_running=lambda: True,
        )

    def test_recording_always_uses_background_no_playback_flag(self):
        registry = ProcessRegistry()
        service = self._build_service(registry)
        states: list[tuple[RecordingState, str, str]] = []
        service.recording_state_changed.connect(
            lambda event: states.append((event.state, event.device_serial, event.payload))
        )

        launched_commands: list[list[str]] = []

        def _fake_popen(command, creationflags=0):
            del creationflags
            launched_commands.append(command)
            return _FakeProc()

        with patch("subprocess.Popen", side_effect=_fake_popen):
            service.start_recording(
                device_serial="device-1",
                save_path="D:/capture.mp4",
                bg_mode=False,
                record_video=True,
                record_audio=False,
            )

        self.assertEqual(len(launched_commands), 1)
        self.assertIn("--record", launched_commands[0])
        self.assertIn("D:/capture.mp4", launched_commands[0])
        self.assertIn("--no-playback", launched_commands[0])
        self.assertEqual(states[0], (RecordingState.STARTED, "device-1", "D:/capture.mp4"))
        self.assertEqual(states[-1], (RecordingState.STOPPED, "device-1", "D:/capture.mp4"))

    def test_recording_unexpected_exit_emits_failed(self):
        registry = ProcessRegistry()
        service = self._build_service(registry)
        states: list[tuple[RecordingState, str, str]] = []
        service.recording_state_changed.connect(
            lambda event: states.append((event.state, event.device_serial, event.payload))
        )

        with patch("subprocess.Popen", return_value=_FailingProc(returncode=1)):
            service.start_recording(
                device_serial="device-1",
                save_path="D:/capture.mp4",
                bg_mode=False,
                record_video=True,
                record_audio=False,
            )

        self.assertEqual(states[0], (RecordingState.STARTED, "device-1", "D:/capture.mp4"))
        self.assertEqual(states[-1][0], RecordingState.FAILED)
        self.assertIn("返回码: 1", states[-1][2])

    def test_recording_intentional_stop_still_emits_stopped(self):
        registry = ProcessRegistry()
        service = self._build_service(registry)
        states: list[tuple[RecordingState, str, str]] = []
        service.recording_state_changed.connect(
            lambda event: states.append((event.state, event.device_serial, event.payload))
        )

        def _simulate_stop():
            registry.ensure("device-1").setdefault("intentional_record_stop_pids", set()).add(4321)

        with patch("subprocess.Popen", return_value=_FailingProc(returncode=1, on_wait=_simulate_stop)):
            service.start_recording(
                device_serial="device-1",
                save_path="D:/capture.mp4",
                bg_mode=False,
                record_video=True,
                record_audio=False,
            )

        self.assertEqual(states[0], (RecordingState.STARTED, "device-1", "D:/capture.mp4"))
        self.assertEqual(states[-1], (RecordingState.STOPPED, "device-1", "D:/capture.mp4"))

    def test_recording_does_not_restore_audio_when_app_is_stopping(self):
        registry = ProcessRegistry()
        restored_audio: list[tuple[str, int]] = []
        registry.register("device-1", "audio", _FakeProc())
        service = RecordingService(
            cmd_manager=_FakeCommandManager(),
            process_registry=registry,
            process_supervisor=ProcessSupervisor(registry),
            task_runner=_ImmediateTaskRunner(),
            probe_scrcpy_features=lambda: {
                "record_ori": False,
                "capture_ori": False,
                "lock_video_ori": False,
                "degrees": False,
                "no_playback": "--no-playback",
            },
            start_audio_route=lambda device, port: restored_audio.append((device, port)),
            stop_audio=lambda device: None,
            is_running=lambda: False,
        )

        with patch("subprocess.Popen", return_value=_FakeProc()), patch(
            "app.services.recording_service.time.sleep",
            lambda _: None,
        ):
            service.start_recording(
                device_serial="device-1",
                save_path="D:/capture.mp4",
                bg_mode=False,
                record_video=True,
                record_audio=True,
            )

        self.assertEqual(restored_audio, [])

    def test_stop_recording_marks_process_as_intentional_stop(self):
        registry = ProcessRegistry()
        task_runner = _DeferredMonitorTaskRunner()
        service = RecordingService(
            cmd_manager=_FakeCommandManager(),
            process_registry=registry,
            process_supervisor=_StopAwareSupervisor(registry),
            task_runner=task_runner,
            probe_scrcpy_features=lambda: {
                "record_ori": False,
                "capture_ori": False,
                "lock_video_ori": False,
                "degrees": False,
                "no_playback": "--no-playback",
            },
            start_audio_route=lambda device, port: None,
            stop_audio=lambda device: None,
            is_running=lambda: True,
        )
        states: list[tuple[RecordingState, str, str]] = []
        service.recording_state_changed.connect(
            lambda event: states.append((event.state, event.device_serial, event.payload))
        )
        proc = _FailingProc(returncode=1)

        with patch("subprocess.Popen", return_value=proc):
            service.start_recording(
                device_serial="device-1",
                save_path="D:/capture.mp4",
                bg_mode=False,
                record_video=True,
                record_audio=False,
            )

        service.stop_recording("device-1")
        task_runner.run_deferred()

        self.assertEqual(states[0], (RecordingState.STARTED, "device-1", "D:/capture.mp4"))
        self.assertEqual(states[-1], (RecordingState.STOPPED, "device-1", "D:/capture.mp4"))


if __name__ == "__main__":
    unittest.main()
