import os
import sys
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QDialog,
    QLineEdit,
    QListWidget,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
)

from app.ui.device_page_controller import DevicePageController
from app.ui.device_runtime_coordinator import apply_validation_result_ui
from app.ui.device_service_coordinator import finalize_operation_ui, submit_adb_service_action
from app.infrastructure.adb.path_resolver import ADBPathResolver
from app.ui.file_page_controller import FilePageController
from app.ui.popup_manager import PopupManager
from app.ui.runtime_settings import (
    apply_ui_settings,
    build_runtime_configuration_request,
    collect_ui_settings,
    get_audio_router_candidate_paths,
    get_audio_router_recommended_args,
    resolve_runtime_paths,
)
from core import FileType


class _RefreshButtonStub:
    def __init__(self):
        self.values: list[bool] = []

    def set_refresh_mode(self, checked):
        self.values.append(bool(checked))


class _CoreStub:
    def __init__(self):
        self.refresh_count = 0

    def request_refresh_devices(self):
        self.refresh_count += 1


class DevicePageControllerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.device_list = QListWidget()
        self.refresh_button = _RefreshButtonStub()
        self.device_combo = QComboBox()
        self.rec_combo = QComboBox()
        self.file_combo = QComboBox()
        self.status_messages: list[str] = []
        self.warning_count = 0
        self.core = _CoreStub()
        self.auto_refresh_value = 1
        self.is_adb_valid = True

        self.controller = DevicePageController(
            device_list=self.device_list,
            refresh_devices_button=self.refresh_button,
            device_combo=self.device_combo,
            recording_device_combo=self.rec_combo,
            file_device_combo=self.file_combo,
            status_setter=self.status_messages.append,
            show_device_required_warning=self._warn_device_required,
            core_provider=lambda: self.core,
            is_adb_valid_provider=lambda: self.is_adb_valid,
            auto_refresh_value_provider=lambda: self.auto_refresh_value,
        )

    def _warn_device_required(self):
        self.warning_count += 1

    def test_update_device_list_preserves_selected_device(self):
        self.controller.update_device_list(["device-a", "device-b"])
        self.device_list.item(1).setSelected(True)
        self.device_combo.setCurrentText("device-b")
        self.rec_combo.setCurrentText("device-b")
        self.file_combo.setCurrentText("device-b")

        self.controller.update_device_list(["device-b", "device-c"])

        self.assertEqual(self.controller.get_selected_device(show_warning=False), "device-b")
        self.assertEqual(self.device_combo.currentText(), "device-b")
        self.assertEqual(self.rec_combo.currentText(), "device-b")
        self.assertEqual(self.file_combo.currentText(), "device-b")

    def test_manual_refresh_disables_auto_mode_when_selection_exists(self):
        self.controller.update_device_list(["device-a"])
        self.device_list.setCurrentItem(self.device_list.item(0))
        self.device_list.item(0).setSelected(True)

        self.controller.manual_refresh_devices()

        self.assertEqual(self.refresh_button.values, [False])
        self.assertEqual(self.core.refresh_count, 1)

    def test_auto_refresh_skips_when_selection_exists(self):
        self.controller.update_device_list(["device-a"])
        self.device_list.setCurrentItem(self.device_list.item(0))
        self.device_list.item(0).setSelected(True)

        self.controller.auto_refresh_devices()

        self.assertEqual(self.refresh_button.values, [False])
        self.assertEqual(self.core.refresh_count, 0)

    def test_get_selected_device_shows_warning_when_empty(self):
        selected = self.controller.get_selected_device(show_warning=True)

        self.assertIsNone(selected)
        self.assertEqual(self.warning_count, 1)


class DeviceRuntimeCoordinatorTests(unittest.TestCase):
    def test_apply_validation_result_ui_triggers_first_ready_once(self):
        statuses: list[str] = []
        restored: list[bool] = []
        first_ready: list[str] = []

        result = apply_validation_result_ui(
            [1, 1, 1],
            is_first_startup=True,
            set_status=statuses.append,
            restore_validation_actions=restored.append,
            on_first_ready=lambda: first_ready.append("ready"),
        )

        self.assertTrue(result.adb_valid)
        self.assertTrue(result.are_paths_ready)
        self.assertFalse(result.next_first_startup)
        self.assertEqual(restored, [True])
        self.assertEqual(first_ready, ["ready"])
        self.assertIn("路径验证", statuses[0])

    def test_apply_validation_result_ui_does_not_trigger_first_ready_when_invalid(self):
        first_ready: list[str] = []

        result = apply_validation_result_ui(
            [1, 0, 1],
            is_first_startup=True,
            set_status=lambda _: None,
            restore_validation_actions=lambda _: None,
            on_first_ready=lambda: first_ready.append("ready"),
        )

        self.assertFalse(result.are_paths_ready)
        self.assertEqual(first_ready, [])

    def test_apply_validation_result_ui_restores_actions_with_current_ready_state(self):
        restored: list[bool] = []

        apply_validation_result_ui(
            [1, 0, 1],
            is_first_startup=False,
            set_status=lambda _: None,
            restore_validation_actions=restored.append,
        )

        self.assertEqual(restored, [False])


class DeviceServiceCoordinatorTests(unittest.TestCase):
    def test_submit_adb_service_action_runs_hook_then_updates_status(self):
        calls: list[str] = []
        statuses: list[str] = []

        submit_adb_service_action(
            before_submit=lambda: calls.append("before"),
            set_status=statuses.append,
            submit=lambda: calls.append("submit"),
            restart=True,
        )

        self.assertEqual(calls, ["before", "submit"])
        self.assertTrue(statuses)
        self.assertIn("ADB", statuses[0])

    def test_finalize_operation_ui_hides_progress_and_shows_install_result(self):
        calls: list[str] = []
        statuses: list[str] = []
        install_results: list[bool] = []

        finalize_operation_ui(
            "install",
            True,
            hide_progress=lambda: calls.append("hide"),
            set_status=statuses.append,
            show_install_result=install_results.append,
        )

        self.assertEqual(calls, ["hide"])
        self.assertTrue(statuses)
        self.assertEqual(install_results, [True])


class RuntimeSettingsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._app = QApplication.instance() or QApplication([])

    def _build_window_stub(self):
        max_size_combo = QComboBox()
        max_size_combo.addItems(["原始", "1080"])
        lock_ori_combo = QComboBox()
        lock_ori_combo.addItems(["默认", "竖屏"])
        rec_ori_combo = QComboBox()
        rec_ori_combo.addItems(["自动", "横屏"])
        video_bitrate = QSpinBox()
        video_bitrate.setRange(0, 99999)
        audio_bitrate = QSpinBox()
        audio_bitrate.setRange(0, 99999)

        window = SimpleNamespace(
            adb_path_edit=QLineEdit(),
            player_path_edit=QLineEdit(),
            sndcpy_dir_edit=QLineEdit(),
            video_check=QCheckBox(),
            audio_check=QCheckBox(),
            fps_check=QCheckBox(),
            stay_awake_check=QCheckBox(),
            screen_off_check=QCheckBox(),
            video_bitrate=video_bitrate,
            audio_bitrate=audio_bitrate,
            max_size_combo=max_size_combo,
            lock_ori_combo=lock_ori_combo,
            rec_ori_combo=rec_ori_combo,
            rec_bg_check=QCheckBox(),
            record_dir_edit=QLineEdit(),
            local_down_edit=QLineEdit(),
        )
        return window

    def test_resolve_runtime_paths_applies_defaults(self):
        resolver_calls: list[tuple[str, str]] = []

        class _Resolver:
            def resolve(self, adb_path, sndcpy_dir):
                resolver_calls.append((adb_path, sndcpy_dir))
                return SimpleNamespace(path="resolved-adb")

        with patch("app.ui.runtime_settings.shutil.which", return_value="C:/VLC/vlc.exe"), patch(
            "app.ui.runtime_settings.os.path.isfile",
            side_effect=lambda path: path == "C:/VLC/vlc.exe",
        ):
            resolution, player_path, sndcpy_dir = resolve_runtime_paths(
                "",
                "",
                "",
                adb_path_resolver=_Resolver(),
                app_base_dir="D:/App",
            )

        self.assertEqual(resolution.path, "resolved-adb")
        self.assertEqual(player_path, os.path.abspath("C:/VLC/vlc.exe"))
        expected_subdir = {"win32": "windows", "darwin": "macos"}.get(sys.platform, "linux")
        self.assertEqual(os.path.basename(sndcpy_dir), expected_subdir)
        self.assertEqual(resolver_calls, [("", sndcpy_dir)])

    def test_resolve_runtime_paths_falls_back_to_audio_router_when_vlc_is_missing(self):
        resolver_calls: list[tuple[str, str]] = []

        class _Resolver:
            def resolve(self, adb_path, sndcpy_dir):
                resolver_calls.append((adb_path, sndcpy_dir))
                return SimpleNamespace(path="resolved-adb")

        audio_router_path = get_audio_router_candidate_paths("D:/App")[2]

        with patch("app.ui.runtime_settings.shutil.which", return_value=None), patch(
            "app.ui.runtime_settings.os.path.isfile",
            side_effect=lambda path: os.path.abspath(path) == audio_router_path,
        ):
            resolution, player_path, sndcpy_dir = resolve_runtime_paths(
                "",
                "",
                "",
                adb_path_resolver=_Resolver(),
                app_base_dir="D:/App",
            )

        self.assertEqual(resolution.path, "resolved-adb")
        self.assertEqual(player_path, audio_router_path)
        self.assertEqual(resolver_calls, [("", sndcpy_dir)])

    def test_audio_router_recommended_args_match_compatible_vlc_style_flags(self):
        self.assertEqual(
            get_audio_router_recommended_args(),
            "-Idummy --demux rawaud --network-caching=200 --play-and-exit",
        )


    def test_collect_and_apply_ui_settings_round_trip(self):
        window = self._build_window_stub()
        window.adb_path_edit.setText("adb.exe")
        window.player_path_edit.setText("player.exe")
        window.sndcpy_dir_edit.setText("sndcpy-dir")
        window.video_check.setChecked(False)
        window.audio_check.setChecked(True)
        window.fps_check.setChecked(True)
        window.stay_awake_check.setChecked(False)
        window.screen_off_check.setChecked(False)
        window.video_bitrate.setValue(4321)
        window.audio_bitrate.setValue(256)
        window.max_size_combo.setCurrentText("1080")
        window.lock_ori_combo.setCurrentIndex(1)
        window.rec_ori_combo.setCurrentIndex(1)
        window.rec_bg_check.setChecked(True)
        window.record_dir_edit.setText("record-dir")
        window.local_down_edit.setText("download-dir")

        settings = collect_ui_settings(
            window,
            {"adb_extra": "--a", "player_extra": "--p", "scrcpy_extra": "--s"},
        )

        new_window = self._build_window_stub()
        apply_ui_settings(new_window, settings)

        self.assertEqual(settings["adb_path"], "adb.exe")
        self.assertEqual(settings["video_bitrate"], 4321)
        self.assertEqual(settings["download_dir"], "download-dir")
        self.assertEqual(new_window.player_path_edit.text(), "player.exe")
        self.assertFalse(new_window.video_check.isChecked())
        self.assertEqual(new_window.max_size_combo.currentText(), "1080")
        self.assertEqual(new_window.lock_ori_combo.currentIndex(), 1)
        self.assertEqual(new_window.rec_ori_combo.currentIndex(), 1)

    def test_build_runtime_configuration_request_maps_fields(self):
        request = build_runtime_configuration_request(
            {
                "adb_extra": "--adb",
                "player_extra": "--player",
                "scrcpy_extra": "--scrcpy",
            },
            adb_resolution=SimpleNamespace(path="adb-path"),
            player_path="player-path",
            sndcpy_dir="sndcpy-dir",
        )

        self.assertEqual(request.adb_path, "adb-path")
        self.assertEqual(request.player_path, "player-path")
        self.assertEqual(request.sndcpy_dir, "sndcpy-dir")
        self.assertEqual(request.adb_extra, "--adb")
        self.assertEqual(request.player_extra, "--player")
        self.assertEqual(request.scrcpy_extra, "--scrcpy")

    def test_popup_manager_exposes_audio_router_quick_fill_for_player_params(self):
        captured: dict[str, object] = {}

        class _FakeDialog:
            def __init__(self, parent=None, **kwargs):
                del parent
                captured.update(kwargs)

            def exec(self):
                return QDialog.DialogCode.Accepted

            def get_value(self):
                return "--filled"

        with patch("app.ui.popup_manager.ParamSettingsDialog", _FakeDialog):
            popup = PopupManager(parent=None)
            value = popup.open_param_settings("player", "")

        self.assertEqual(value, "--filled")
        self.assertEqual(
            captured["quick_fill_actions"],
            [("AudioRouter 推荐", get_audio_router_recommended_args())],
        )


class ADBPathResolverTests(unittest.TestCase):
    def test_negative_viability_result_is_not_cached(self):
        resolver = ADBPathResolver("D:/App")

        with patch("app.infrastructure.adb.path_resolver.subprocess.run") as mock_run:
            mock_run.side_effect = [
                SimpleNamespace(returncode=1),
                SimpleNamespace(returncode=0),
            ]

            first = resolver._is_usable_adb("C:/tools/adb.exe")
            second = resolver._is_usable_adb("C:/tools/adb.exe")

        self.assertFalse(first)
        self.assertTrue(second)
        self.assertEqual(mock_run.call_count, 2)


class FilePageControllerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.file_device_combo = QComboBox()
        self.file_device_combo.addItem("device-1")
        self.remote_path_edit = QLineEdit("/sdcard")
        self.file_table = QTableWidget(1, 1)
        self.local_down_edit = QLineEdit("D:/Downloads")
        self.logs: list[tuple[str, str]] = []
        self.list_requests: list[tuple[str, str]] = []
        self.pull_requests: list[tuple[str, str, str | None]] = []

        self.controller = FilePageController(
            host_widget=None,
            file_device_combo=self.file_device_combo,
            remote_path_edit=self.remote_path_edit,
            file_table=self.file_table,
            local_down_edit=self.local_down_edit,
            core_provider=lambda: object(),
            popups=SimpleNamespace(),
            log_to_console=lambda message, level: self.logs.append((message, level)),
            request_list_files=self._request_list_files,
            request_pull=self._request_pull,
        )

    def _request_list_files(self, device, remote_path):
        self.list_requests.append((device, remote_path))
        return remote_path if remote_path.endswith("/") else f"{remote_path}/"

    def _request_pull(self, device, remote_file, local_dir, rename_to):
        self.pull_requests.append((device, remote_file, rename_to))

    def test_refresh_file_list_normalizes_target_path(self):
        self.remote_path_edit.setText(" /sdcard/Music ")

        self.controller.refresh_file_list()

        self.assertEqual(self.list_requests, [("device-1", "/sdcard/Music")])
        self.assertEqual(self.remote_path_edit.text(), "/sdcard/Music/")
        self.assertEqual(self.logs[-1][1], "info")

    def test_go_up_dir_updates_path_and_refreshes(self):
        self.remote_path_edit.setText("/sdcard/Music/Album/")

        self.controller.go_up_dir()

        self.assertEqual(self.remote_path_edit.text(), "/sdcard/Music/")
        self.assertEqual(self.list_requests[-1], ("device-1", "/sdcard/Music/"))

    def test_handle_table_double_click_enters_directory(self):
        entry = SimpleNamespace(
            name="Music",
            is_dir=True,
            file_type=FileType.DIRECTORY,
            is_symlink_to_dir=False,
        )
        item = QTableWidgetItem("Music")
        item.setData(Qt.ItemDataRole.UserRole, entry)
        self.file_table.setItem(0, 0, item)

        self.controller.handle_table_double_click(item)

        self.assertEqual(self.remote_path_edit.text(), "/sdcard/Music/")
        self.assertEqual(self.list_requests[-1], ("device-1", "/sdcard/Music/"))

    def test_handle_table_double_click_downloads_regular_file(self):
        entry = SimpleNamespace(
            name="song.mp3",
            is_dir=False,
            file_type=FileType.FILE,
            is_symlink_to_dir=False,
            size_display="5 MB",
            type_description="音频",
        )
        item = QTableWidgetItem("song.mp3")
        item.setData(Qt.ItemDataRole.UserRole, entry)
        self.file_table.setItem(0, 0, item)

        with patch.object(self.controller, "download_file_item") as download_mock:
            self.controller.handle_table_double_click(item)

        download_mock.assert_called_once_with(entry)
        self.assertEqual(self.logs[-1][1], "info")

    def test_download_file_item_delegates_to_download_handler(self):
        entry = SimpleNamespace(name="song.mp3", is_dir=False)

        with patch("app.ui.file_page_controller.handle_download_request") as handler_mock:
            self.controller.download_file_item(entry)

        handler_mock.assert_called_once()
        kwargs = handler_mock.call_args.kwargs
        self.assertEqual(kwargs["remote_base_path"], "/sdcard")
        self.assertEqual(kwargs["local_dir"], "D:/Downloads")


if __name__ == "__main__":
    unittest.main()
