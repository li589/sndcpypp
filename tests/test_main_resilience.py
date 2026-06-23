import unittest
from types import SimpleNamespace

from main import SndcpyGUI


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


if __name__ == "__main__":
    unittest.main()
