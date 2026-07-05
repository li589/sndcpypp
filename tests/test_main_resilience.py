import unittest
from types import SimpleNamespace
from unittest.mock import patch

import app.ui.main_window as main_window

from app.ui.dialogs import ExitAction
from app.ui.main_window import SndcpyGUI
from core import CoreController


class MainResilienceTests(unittest.TestCase):
    def test_resolve_app_base_dir_uses_pyinstaller_meipass_when_frozen(self):
        with patch.object(main_window.sys, "frozen", True, create=True), patch.object(
            main_window.sys,
            "_MEIPASS",
            "D:/Temp/_MEI123",
            create=True,
        ):
            self.assertEqual(main_window._resolve_app_base_dir(), "D:\\Temp\\_MEI123")

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

    def test_close_event_waits_for_core_cleanup_before_exit(self):
        calls: list[tuple[str, object]] = []

        class _Event:
            def accept(self):
                calls.append(("event", "accept"))

            def ignore(self):
                calls.append(("event", "ignore"))

        window = SimpleNamespace(
            force_quit=True,
            save_settings=lambda: calls.append(("window", "save")),
            usb_monitor=None,
            core_controller=SimpleNamespace(
                request_shutdown_and_wait=lambda timeout=0: calls.append(("shutdown", timeout)) or True,
            ),
            log_to_console=lambda message, level: calls.append(("log", level, message)),
            scan_timer=SimpleNamespace(isActive=lambda: False),
            tray_icon=SimpleNamespace(hide=lambda: calls.append(("tray", "hide"))),
            popups=SimpleNamespace(confirm_exit_action=lambda: ExitAction.EXIT),
            close_only_action=lambda: calls.append(("window", "hide_to_tray")),
        )

        SndcpyGUI.closeEvent(window, _Event())

        self.assertIn(("shutdown", 8), calls)
        self.assertIn(("event", "accept"), calls)
        shutdown_index = calls.index(("shutdown", 8))
        accept_index = calls.index(("event", "accept"))
        self.assertLess(shutdown_index, accept_index)

    def test_force_kill_adb_stops_streaming_before_killing_adb(self):
        calls: list[str] = []
        controller = SimpleNamespace(
            stop_streaming=lambda device_serial=None: calls.append(f"stop:{device_serial}"),
            _adb_device_service=SimpleNamespace(force_kill_adb=lambda: calls.append("kill")),
        )

        CoreController.force_kill_adb(controller)

        self.assertEqual(calls, ["stop:None", "kill"])

    def test_restart_adb_stops_streaming_before_restart(self):
        calls: list[str] = []
        controller = SimpleNamespace(
            stop_streaming=lambda device_serial=None: calls.append(f"stop:{device_serial}"),
            _adb_device_service=SimpleNamespace(restart_adb=lambda: calls.append("restart")),
        )

        CoreController.restart_adb(controller)

        self.assertEqual(calls, ["stop:None", "restart"])

    def test_run_adb_command_internal_can_override_timeout(self):
        captured: list[tuple[list[str], str, object]] = []
        controller = SimpleNamespace(
            _adb_client=SimpleNamespace(
                run_logged=lambda command, description, timeout_seconds=15: captured.append(
                    (command, description, timeout_seconds)
                ) or "ok"
            )
        )

        result = CoreController._run_adb_command_internal(
            controller,
            ["adb", "version"],
            "测试",
            timeout_seconds=None,
        )

        self.assertEqual(result, "ok")
        self.assertEqual(captured, [(["adb", "version"], "测试", None)])


if __name__ == "__main__":
    unittest.main()
