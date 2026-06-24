import sys
import types
import unittest


if "PyQt6" not in sys.modules:
    qtcore = types.ModuleType("PyQt6.QtCore")

    class QObject:
        def __init__(self, *args, **kwargs):
            pass

    class _Signal:
        def __init__(self, *args, **kwargs):
            pass

        def connect(self, slot):
            del slot

        def emit(self, *args, **kwargs):
            del args, kwargs

    def pyqtSignal(*args, **kwargs):
        del args, kwargs
        return _Signal()

    qtcore.QObject = QObject
    qtcore.pyqtSignal = pyqtSignal
    pyqt6 = types.ModuleType("PyQt6")
    pyqt6.QtCore = qtcore
    sys.modules["PyQt6"] = pyqt6
    sys.modules["PyQt6.QtCore"] = qtcore


from app.infrastructure.adb.command_builder import ADBCommandBuilder
from app.ui.message_templates import status_operation_result


class CommandBuilderTests(unittest.TestCase):
    def test_start_video_scrcpy_cmd_disables_scrcpy_audio(self):
        builder = ADBCommandBuilder(
            {
                "scrcpy_path": r"D:\tools\scrcpy\scrcpy.exe",
                "device_serial": "device-1",
            }
        )

        cmd = builder.get_target_cmd(
            "start_video_scrcpy_cmd",
            device_serial="device-1",
            video_bitrate=8000000,
            max_size_flag="",
            max_size_val="",
            lock_ori_flag="",
            lock_ori_val="",
            fps_flag="",
            stay_awake_flag="--stay-awake",
            screen_off_flag="",
        )

        self.assertIn("--no-audio", cmd)
        self.assertEqual(cmd.count("--no-audio"), 1)

    def test_start_video_scrcpy_cmd_forces_adb_forward_without_pause_on_exit(self):
        builder = ADBCommandBuilder(
            {
                "scrcpy_path": r"D:\tools\scrcpy\scrcpy.exe",
                "device_serial": "device-1",
            }
        )

        cmd = builder.get_target_cmd(
            "start_video_scrcpy_cmd",
            device_serial="device-1",
            video_bitrate=8000000,
            max_size_flag="",
            max_size_val="",
            lock_ori_flag="",
            lock_ori_val="",
            fps_flag="",
            stay_awake_flag="--stay-awake",
            screen_off_flag="",
        )

        self.assertIn("--force-adb-forward", cmd)
        self.assertNotIn("--pause-on-exit=if-error", cmd)

    def test_status_operation_result_distinguishes_audio_and_video_route(self):
        self.assertEqual(status_operation_result("audio_route", False), "音频路由启动失败")
        self.assertEqual(status_operation_result("video_route", True), "画面路由启动成功")


if __name__ == "__main__":
    unittest.main()
