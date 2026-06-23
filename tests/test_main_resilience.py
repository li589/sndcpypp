import unittest
from datetime import datetime, timedelta
from types import SimpleNamespace

from app.domain.models.operation_requests import (
    ConsoleTargetKind,
    RecordingState,
    RecordingStateEvent,
)
from main import RecordingSessionState, SndcpyGUI


class MainResilienceTests(unittest.TestCase):
    def test_startup_routine_keeps_running_when_usb_monitor_start_fails(self):
        logs: list[tuple[str, str]] = []
        calls: list[str] = []

        class _UsbMonitor:
            def start_monitoring(self):
                raise RuntimeError("usb-start-failed")

        window = SimpleNamespace(
            usb_monitor=_UsbMonitor(),
            log_to_console=lambda message, level: logs.append((message, level)),
            validate_paths=lambda: calls.append("validate"),
        )

        SndcpyGUI.startup_routine(window)

        self.assertEqual(calls, ["validate"])
        self.assertIsNone(window.usb_monitor)
        self.assertTrue(any(level == "warning" and "usb-start-failed" in message for message, level in logs))

    def test_refresh_recording_status_shows_elapsed_time(self):
        statuses: list[str] = []
        window = SimpleNamespace(
            _recording_sessions={
                "device-1": RecordingSessionState(
                    save_path="D:/capture.mp4",
                    started_at=datetime.now() - timedelta(seconds=65),
                )
            },
            status_label=SimpleNamespace(setText=statuses.append),
        )
        window._format_elapsed_seconds = lambda seconds: SndcpyGUI._format_elapsed_seconds(window, seconds)

        SndcpyGUI._refresh_recording_status(window)

        self.assertEqual(len(statuses), 1)
        self.assertIn("device-1", statuses[0])
        self.assertIn("00:01", statuses[0])

    def test_long_recording_reminder_only_fires_when_not_fullscreen(self):
        notifications: list[tuple[str, str, object, int]] = []
        session = RecordingSessionState(
            save_path="D:/capture.mp4",
            started_at=datetime.now() - timedelta(minutes=31),
        )
        window = SimpleNamespace(
            _recording_sessions={"device-1": session},
            LONG_RECORDING_REMINDER_SECONDS=30 * 60,
            _is_foreground_fullscreen=lambda: False,
            _show_tray_notification=lambda title, message, icon, timeout: notifications.append(
                (title, message, icon, timeout)
            ),
        )
        window._format_elapsed_seconds = lambda seconds: SndcpyGUI._format_elapsed_seconds(window, seconds)

        SndcpyGUI._check_long_recording_reminders(window)

        self.assertEqual(len(notifications), 1)
        self.assertTrue(session.reminder_sent)

    def test_long_recording_reminder_skips_fullscreen(self):
        notifications: list[tuple[str, str, object, int]] = []
        session = RecordingSessionState(
            save_path="D:/capture.mp4",
            started_at=datetime.now() - timedelta(minutes=31),
        )
        window = SimpleNamespace(
            _recording_sessions={"device-1": session},
            LONG_RECORDING_REMINDER_SECONDS=30 * 60,
            _is_foreground_fullscreen=lambda: True,
            _show_tray_notification=lambda title, message, icon, timeout: notifications.append(
                (title, message, icon, timeout)
            ),
        )
        window._format_elapsed_seconds = lambda seconds: SndcpyGUI._format_elapsed_seconds(window, seconds)

        SndcpyGUI._check_long_recording_reminders(window)

        self.assertEqual(notifications, [])
        self.assertFalse(session.reminder_sent)

    def test_build_console_command_request_maps_explicit_target_kind(self):
        window = SimpleNamespace(
            device_combo=SimpleNamespace(currentText=lambda: "device-1"),
        )

        request = SndcpyGUI._build_console_command_request(window, "shell id")

        self.assertEqual(request.command_str, "shell id")
        self.assertEqual(request.target_kind, ConsoleTargetKind.ADB_DEVICE)
        self.assertEqual(request.device_serial, "device-1")

    def test_handle_recording_state_change_uses_event_object(self):
        statuses: list[str] = []
        started_timer = []
        reminder_timer = []
        window = SimpleNamespace(
            _recording_sessions={},
            recording_status_timer=SimpleNamespace(
                isActive=lambda: False,
                start=lambda: started_timer.append("status"),
            ),
            recording_reminder_timer=SimpleNamespace(
                isActive=lambda: False,
                start=lambda: reminder_timer.append("reminder"),
            ),
            _refresh_recording_status=lambda: statuses.append("refresh"),
            _stop_recording_timers_if_idle=lambda: None,
            status_label=SimpleNamespace(setText=statuses.append),
        )

        SndcpyGUI.handle_recording_state_change(
            window,
            RecordingStateEvent(RecordingState.STARTED, "device-1", "D:/capture.mp4"),
        )

        self.assertIn("device-1", window._recording_sessions)
        self.assertEqual(started_timer, ["status"])
        self.assertEqual(reminder_timer, ["reminder"])
        self.assertEqual(statuses, ["refresh"])


if __name__ == "__main__":
    unittest.main()
