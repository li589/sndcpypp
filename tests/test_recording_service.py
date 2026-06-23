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


class RecordingServiceTests(unittest.TestCase):
    def test_recording_always_uses_background_no_playback_flag(self):
        registry = ProcessRegistry()
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
            start_audio_route=lambda device, port: None,
            stop_audio=lambda device: None,
        )
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


if __name__ == "__main__":
    unittest.main()
