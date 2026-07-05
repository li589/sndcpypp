import os
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QLabel,
    QLineEdit,
    QProgressBar,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QWidget,
)

from app.domain.enums.file_type import FileType
from app.domain.models.file_info import FileInfo
from app.domain.models.operation_requests import (
    ConsoleTargetKind,
    RecordingState,
    RecordingStateEvent,
)
from app.infrastructure.adb.path_resolver import ResolvedADBPath
from app.infrastructure.config.settings_store import JsonSettingsStore
from app.ui.core_lifecycle_coordinator import (
    build_signal_pairs,
    connect_core_signals,
    disconnect_core_signals,
    maybe_log_adb_resolution,
    sync_core_runtime,
)
from app.ui.device_service_coordinator import (
    finalize_operation_ui,
    submit_install_sndcpy,
    submit_kill_adb,
    submit_restart_adb,
)
from app.ui.file_transfer_coordinator import (
    collect_existing_names,
    handle_file_progress,
    handle_symlink_resolved,
    should_refresh_file_view_after_transfer,
    update_file_table,
)
from app.ui.pages.console_page import CONSOLE_TARGET_NO_DEVICE, CONSOLE_TARGET_SCRCPY
from app.ui.recording_session_coordinator import (
    RecordingSessionCoordinator,
    RecordingSessionState,
)
from app.ui.console_logger_coordinator import ConsoleLoggerCoordinator
from app.ui.dialogs import ExitAction
from app.ui.startup_coordinator import run_startup_routine
from app.ui.teardown_coordinator import handle_close_event
from app.ui.request_builders import (
    build_browse_files_request,
    build_console_command_request,
    build_pull_file_request,
    build_push_file_request,
    build_recording_request,
    build_routing_request,
)
from app.ui.settings_coordinator import (
    apply_cmd_extra_settings,
    load_settings_from_store,
    save_settings,
)


class _FakeSignal:
    """Mimics a Qt pyqtSignal for connect/disconnect bookkeeping."""

    def __init__(self):
        self.connected_slots: list = []

    def connect(self, slot):
        self.connected_slots.append(slot)

    def disconnect(self, slot):
        if slot not in self.connected_slots:
            raise TypeError("slot not connected")
        self.connected_slots.remove(slot)


class _FakeCoreController:
    """Stub CoreController exposing the 9 signals used by signal pairs."""

    def __init__(self):
        self.devices_updated = _FakeSignal()
        self.log_message = _FakeSignal()
        self.operation_completed = _FakeSignal()
        self.validation_result = _FakeSignal()
        self.player_process_exited = _FakeSignal()
        self.recording_state_changed = _FakeSignal()
        self.files_listed_detailed = _FakeSignal()
        self.symlink_resolved = _FakeSignal()
        self.file_transfer_progress = _FakeSignal()
        self.configure_calls: list = []

    def request_configure_runtime(self, request):
        self.configure_calls.append(request)


def _make_file_info(
    name: str,
    file_type: FileType = FileType.FILE,
    *,
    type_char: str = "-",
    permissions: str = "-rw-r--r--",
    owner: str = "shell",
    size: int = 1024,
    symlink_target: str = "",
    is_symlink_to_dir=None,
) -> FileInfo:
    return FileInfo(
        name=name,
        file_type=file_type,
        type_char=type_char,
        permissions=permissions,
        owner=owner,
        group="shell",
        size=size,
        date_str="2024-01-01 12:00",
        symlink_target=symlink_target,
        is_symlink_to_dir=is_symlink_to_dir,
    )


def _make_adb_resolution(
    path: str = "adb",
    source: str = "内置 Sndcpy",
    requested_path: str = "",
    used_fallback: bool = False,
) -> ResolvedADBPath:
    return ResolvedADBPath(
        path=path,
        source=source,
        requested_path=requested_path,
        bundled_path="bundled/adb",
        used_fallback=used_fallback,
    )


def _build_window_stub():
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

    return SimpleNamespace(
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


class RecordingSessionCoordinatorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.host_widget = QWidget()
        self.tray_widget = QWidget()
        self.status_messages: list[str] = []
        self.coordinator = RecordingSessionCoordinator(
            host_widget=self.host_widget,
            set_status=self.status_messages.append,
            tray_widget=self.tray_widget,
        )

    def _make_event(self, state, device_serial, payload="D:/records/audio.wav"):
        return RecordingStateEvent(
            state=state, device_serial=device_serial, payload=payload
        )

    def test_started_creates_session_and_starts_timers(self):
        event = self._make_event(RecordingState.STARTED, "device-1")

        self.coordinator.handle_state_change(event)

        self.assertIn("device-1", self.coordinator._sessions)
        session = self.coordinator._sessions["device-1"]
        self.assertIsInstance(session, RecordingSessionState)
        self.assertEqual(session.save_path, "D:/records/audio.wav")
        self.assertTrue(self.coordinator._status_timer.isActive())
        self.assertTrue(self.coordinator._reminder_timer.isActive())
        self.assertTrue(self.status_messages)
        self.assertIn("device-1", self.status_messages[-1])

    def test_stopped_removes_session_and_stops_timers(self):
        self.coordinator.handle_state_change(self._make_event(RecordingState.STARTED, "device-1"))

        self.coordinator.handle_state_change(self._make_event(RecordingState.STOPPED, "device-1"))

        self.assertNotIn("device-1", self.coordinator._sessions)
        self.assertFalse(self.coordinator._status_timer.isActive())
        self.assertFalse(self.coordinator._reminder_timer.isActive())
        self.assertIn("录制已结束", self.status_messages[-1])

    def test_failed_removes_session_and_sets_failed_status(self):
        self.coordinator.handle_state_change(self._make_event(RecordingState.STARTED, "device-1"))

        self.coordinator.handle_state_change(self._make_event(RecordingState.FAILED, "device-1"))

        self.assertNotIn("device-1", self.coordinator._sessions)
        self.assertFalse(self.coordinator._status_timer.isActive())
        self.assertIn("录制启动失败", self.status_messages[-1])

    def test_multiple_active_sessions_uses_multi_status_text(self):
        self.coordinator.handle_state_change(self._make_event(RecordingState.STARTED, "device-a"))
        self.coordinator.handle_state_change(self._make_event(RecordingState.STARTED, "device-b"))

        self.assertEqual(len(self.coordinator._sessions), 2)
        last = self.status_messages[-1]
        self.assertIn("2 台设备", last)

    def test_status_refresh_updates_elapsed_text(self):
        self.coordinator.handle_state_change(self._make_event(RecordingState.STARTED, "device-1"))
        self.status_messages.clear()

        self.coordinator._refresh_recording_status()

        self.assertTrue(self.status_messages)
        self.assertIn("device-1", self.status_messages[-1])
        self.assertIn("00:00:", self.status_messages[-1])


class FileTransferCoordinatorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.file_table = QTableWidget(0, 7)
        self.status_label = QLabel()

    def test_collect_existing_names_returns_names_from_name_column(self):
        self.file_table.setRowCount(2)
        self.file_table.setItem(0, 1, QTableWidgetItem("song.mp3"))
        self.file_table.setItem(1, 1, QTableWidgetItem("video.mp4"))

        names = collect_existing_names(self.file_table)

        self.assertEqual(names, {"song.mp3", "video.mp4"})

    def test_collect_existing_names_skips_empty_cells(self):
        self.file_table.setRowCount(2)
        self.file_table.setItem(0, 1, QTableWidgetItem("only.wav"))

        names = collect_existing_names(self.file_table)

        self.assertEqual(names, {"only.wav"})

    def test_should_refresh_returns_true_for_matching_push(self):
        result = should_refresh_file_view_after_transfer(
            device_serial="device-1",
            transfer_kind="push",
            remote_path="/sdcard/Music/",
            current_device="device-1",
            current_path_text="/sdcard/Music",
        )
        self.assertTrue(result)

    def test_should_refresh_returns_false_for_non_push_transfer(self):
        result = should_refresh_file_view_after_transfer(
            device_serial="device-1",
            transfer_kind="pull",
            remote_path="/sdcard/Music/",
            current_device="device-1",
            current_path_text="/sdcard/Music/",
        )
        self.assertFalse(result)

    def test_should_refresh_returns_false_when_device_differs(self):
        result = should_refresh_file_view_after_transfer(
            device_serial="device-1",
            transfer_kind="push",
            remote_path="/sdcard/Music/",
            current_device="device-2",
            current_path_text="/sdcard/Music/",
        )
        self.assertFalse(result)

    def test_should_refresh_returns_false_when_path_differs(self):
        result = should_refresh_file_view_after_transfer(
            device_serial="device-1",
            transfer_kind="push",
            remote_path="/sdcard/Music/",
            current_device="device-1",
            current_path_text="/sdcard/Download/",
        )
        self.assertFalse(result)

    def test_handle_file_progress_start_initializes_progress_bar(self):
        progress_bar = QProgressBar()
        progress_bar.setVisible(False)
        statuses: list[str] = []

        handle_file_progress(
            status="start",
            device_serial="device-1",
            transfer_kind="push",
            remote_path="/sdcard/Music",
            msg="开始上传",
            percent=0,
            progress_bar=progress_bar,
            set_status=statuses.append,
            should_refresh=False,
        )

        self.assertEqual(statuses, ["开始上传"])
        self.assertTrue(progress_bar.isVisible())
        self.assertEqual(progress_bar.minimum(), 0)
        self.assertEqual(progress_bar.maximum(), 100)
        self.assertEqual(progress_bar.value(), 0)

    def test_handle_file_progress_progress_updates_value(self):
        progress_bar = QProgressBar()
        progress_bar.setRange(0, 100)
        statuses: list[str] = []

        handle_file_progress(
            status="progress",
            device_serial="device-1",
            transfer_kind="push",
            remote_path="/sdcard/Music",
            msg="上传中",
            percent=42,
            progress_bar=progress_bar,
            set_status=statuses.append,
            should_refresh=False,
        )

        self.assertEqual(progress_bar.value(), 42)
        self.assertEqual(statuses, ["上传中"])

    def test_handle_file_progress_done_schedules_hide_and_refresh(self):
        progress_bar = QProgressBar()
        progress_bar.setVisible(True)
        progress_bar.setRange(0, 100)
        statuses: list[str] = []
        refresh_calls: list[int] = []
        scheduled: list[tuple] = []

        with patch(
            "app.ui.file_transfer_coordinator.QTimer.singleShot",
            side_effect=lambda ms, cb: scheduled.append((ms, cb)),
        ):
            handle_file_progress(
                status="done",
                device_serial="device-1",
                transfer_kind="push",
                remote_path="/sdcard/Music",
                msg="上传完成",
                percent=100,
                progress_bar=progress_bar,
                set_status=statuses.append,
                should_refresh=True,
                on_refresh=lambda: refresh_calls.append(1),
            )

        self.assertEqual(progress_bar.value(), 100)
        self.assertEqual(len(scheduled), 2)
        self.assertEqual(scheduled[0][0], 1500)
        self.assertEqual(scheduled[1][0], 500)
        scheduled[1][1]()
        self.assertEqual(refresh_calls, [1])
        scheduled[0][1]()
        self.assertFalse(progress_bar.isVisible())

    def test_handle_file_progress_error_sets_full_value_without_refresh(self):
        progress_bar = QProgressBar()
        progress_bar.setRange(0, 100)
        progress_bar.setValue(30)
        statuses: list[str] = []
        refresh_calls: list[int] = []

        with patch(
            "app.ui.file_transfer_coordinator.QTimer.singleShot",
            side_effect=lambda ms, cb: None,
        ):
            handle_file_progress(
                status="error",
                device_serial="device-1",
                transfer_kind="push",
                remote_path="/sdcard/Music",
                msg="上传失败",
                percent=0,
                progress_bar=progress_bar,
                set_status=statuses.append,
                should_refresh=True,
                on_refresh=lambda: refresh_calls.append(1),
            )

        self.assertEqual(progress_bar.value(), 100)
        self.assertEqual(refresh_calls, [])

    def test_update_file_table_success_populates_and_sets_path(self):
        file_list = [
            _make_file_info("song.mp3", FileType.FILE),
            _make_file_info("Music", FileType.DIRECTORY, type_char="d"),
        ]
        current_path_calls: list[str] = []
        logs: list[tuple] = []

        update_file_table(
            path="/sdcard/Music/",
            file_list=file_list,
            success=True,
            file_table=self.file_table,
            file_status_label=self.status_label,
            set_current_remote_path=current_path_calls.append,
            log_to_console=lambda msg, level: logs.append((msg, level)),
        )

        self.assertEqual(current_path_calls, ["/sdcard/Music/"])
        self.assertEqual(self.file_table.rowCount(), 2)
        summary = self.status_label.text()
        self.assertIn("1 文件夹", summary)
        self.assertIn("1 文件", summary)
        self.assertTrue(logs)
        self.assertEqual(logs[0][1], "success")

    def test_update_file_table_failure_clears_table_and_shows_error(self):
        self.file_table.setRowCount(3)
        current_path_calls: list[str] = []
        logs: list[tuple] = []

        update_file_table(
            path="/sdcard/Music/",
            file_list=[],
            success=False,
            file_table=self.file_table,
            file_status_label=self.status_label,
            set_current_remote_path=current_path_calls.append,
            log_to_console=lambda msg, level: logs.append((msg, level)),
        )

        self.assertEqual(current_path_calls, [])
        self.assertEqual(self.file_table.rowCount(), 0)
        self.assertEqual(self.status_label.text(), "读取失败")

    def test_handle_symlink_resolved_updates_table_when_device_matches(self):
        symlink_info = _make_file_info(
            "link1",
            FileType.SYMLINK,
            type_char="l",
            symlink_target="/sdcard/real",
            is_symlink_to_dir=None,
        )
        from app.ui.file_table_presenter import populate_file_table

        populate_file_table(self.file_table, self.status_label, [symlink_info])
        logs: list[tuple] = []

        handle_symlink_resolved(
            device_serial="device-1",
            name="link1",
            is_dir=True,
            current_device="device-1",
            file_table=self.file_table,
            log_to_console=lambda msg, level: logs.append((msg, level)),
        )

        self.assertTrue(logs)
        self.assertEqual(logs[0][1], "output")
        self.assertIn("目录", logs[0][0])

    def test_handle_symlink_resolved_skips_when_device_differs(self):
        symlink_info = _make_file_info(
            "link1",
            FileType.SYMLINK,
            type_char="l",
            symlink_target="/sdcard/real",
        )
        from app.ui.file_table_presenter import populate_file_table

        populate_file_table(self.file_table, self.status_label, [symlink_info])
        logs: list[tuple] = []

        handle_symlink_resolved(
            device_serial="device-1",
            name="link1",
            is_dir=True,
            current_device="device-2",
            file_table=self.file_table,
            log_to_console=lambda msg, level: logs.append((msg, level)),
        )

        self.assertEqual(logs, [])


class SettingsCoordinatorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._app = QApplication.instance() or QApplication([])

    def test_load_settings_from_store_returns_settings_and_warning(self):
        class _FakeStore:
            def __init__(self):
                self.last_load_warning = "load warning text"

            def load(self):
                return {"adb_path": "adb.exe", "video_bitrate": 1234}

        settings, warning = load_settings_from_store(_FakeStore())

        self.assertEqual(settings["adb_path"], "adb.exe")
        self.assertEqual(settings["video_bitrate"], 1234)
        self.assertEqual(warning, "load warning text")

    def test_save_settings_round_trip_with_temp_file(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            settings_path = os.path.join(temp_dir, "settings.json")
            store = JsonSettingsStore(settings_path)
            window = _build_window_stub()
            window.adb_path_edit.setText("C:/tools/adb.exe")
            window.player_path_edit.setText("C:/VLC/vlc.exe")
            window.video_bitrate.setValue(6000)
            window.audio_bitrate.setValue(192)
            window.max_size_combo.setCurrentText("1080")
            window.lock_ori_combo.setCurrentIndex(1)
            window.record_dir_edit.setText(os.path.join(temp_dir, "rec"))
            window.local_down_edit.setText(os.path.join(temp_dir, "down"))
            settings: dict = {}

            logs: list[tuple] = []
            save_settings(
                settings_store=store,
                window=window,
                settings=settings,
                log_to_console=lambda msg, level: logs.append((msg, level)),
            )

            self.assertTrue(os.path.exists(settings_path))
            self.assertEqual(settings["adb_path"], "C:/tools/adb.exe")
            self.assertEqual(settings["video_bitrate"], 6000)
            self.assertEqual(settings["max_size"], "1080")
            self.assertEqual(logs, [])

    def test_save_settings_logs_error_when_store_raises(self):
        class _FailingStore:
            def save(self, settings):
                raise IOError("disk full")

        window = _build_window_stub()
        settings: dict = {}
        logs: list[tuple] = []

        save_settings(
            settings_store=_FailingStore(),
            window=window,
            settings=settings,
            log_to_console=lambda msg, level: logs.append((msg, level)),
        )

        self.assertEqual(settings, {})
        self.assertTrue(logs)
        self.assertEqual(logs[0][1], "error")
        self.assertIn("disk full", logs[0][0])

    def test_apply_cmd_extra_settings_updates_value_and_returns_title(self):
        settings: dict = {}

        title = apply_cmd_extra_settings(
            cmd_type="adb",
            updated_value="--devices",
            settings=settings,
        )

        self.assertEqual(title, "ADB")
        self.assertEqual(settings["adb_extra"], "--devices")

    def test_apply_cmd_extra_settings_returns_none_for_unknown_cmd_type(self):
        settings: dict = {}

        title = apply_cmd_extra_settings(
            cmd_type="unknown",
            updated_value="--x",
            settings=settings,
        )

        self.assertIsNone(title)
        self.assertEqual(settings["unknown_extra"], "--x")

    def test_apply_cmd_extra_settings_returns_none_when_value_is_none(self):
        settings: dict = {}

        title = apply_cmd_extra_settings(
            cmd_type="adb",
            updated_value=None,
            settings=settings,
        )

        self.assertIsNone(title)
        self.assertNotIn("adb_extra", settings)


class CoreLifecycleCoordinatorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._app = QApplication.instance() or QApplication([])

    def _build_slots(self):
        return {
            "update_device_list": lambda *a, **kw: None,
            "log_to_console": lambda *a, **kw: None,
            "handle_operation_complete": lambda *a, **kw: None,
            "handle_validation_result": lambda *a, **kw: None,
            "handle_player_exit": lambda *a, **kw: None,
            "handle_recording_state_change": lambda *a, **kw: None,
            "update_file_table": lambda *a, **kw: None,
            "handle_symlink_resolved": lambda *a, **kw: None,
            "handle_file_progress": lambda *a, **kw: None,
        }

    def test_maybe_log_adb_resolution_dedups_same_signature(self):
        resolution = _make_adb_resolution(path="adb", source="内置 Sndcpy")
        logs: list[tuple] = []

        first = maybe_log_adb_resolution(resolution, None, lambda msg, level: logs.append((msg, level)))
        second = maybe_log_adb_resolution(resolution, first, lambda msg, level: logs.append((msg, level)))

        self.assertEqual(first, second)
        self.assertEqual(len(logs), 1)

    def test_maybe_log_adb_resolution_logs_builtin_with_info_level(self):
        resolution = _make_adb_resolution(path="bundled/adb", source="内置 Sndcpy")
        logs: list[tuple] = []

        maybe_log_adb_resolution(resolution, None, lambda msg, level: logs.append((msg, level)))

        self.assertEqual(logs[0][1], "info")
        self.assertIn("bundled/adb", logs[0][0])

    def test_maybe_log_adb_resolution_logs_fallback_with_warning(self):
        resolution = _make_adb_resolution(
            path="bundled/adb",
            source="内置 Sndcpy",
            requested_path="C:/missing/adb.exe",
            used_fallback=True,
        )
        logs: list[tuple] = []

        maybe_log_adb_resolution(resolution, None, lambda msg, level: logs.append((msg, level)))

        self.assertEqual(logs[0][1], "warning")
        self.assertIn("回退", logs[0][0])

    def test_maybe_log_adb_resolution_logs_unresolved_with_warning(self):
        resolution = _make_adb_resolution(path="adb", source="未解析")
        logs: list[tuple] = []

        maybe_log_adb_resolution(resolution, None, lambda msg, level: logs.append((msg, level)))

        self.assertEqual(logs[0][1], "warning")
        self.assertIn("尚未解析", logs[0][0])

    def test_build_signal_pairs_returns_nine_pairs(self):
        controller = _FakeCoreController()
        slots = self._build_slots()

        pairs = build_signal_pairs(controller, slots)

        self.assertEqual(len(pairs), 9)
        for signal, slot in pairs:
            self.assertIsInstance(signal, _FakeSignal)
            self.assertIsNotNone(slot)

    def test_connect_core_signals_connects_all_slots(self):
        controller = _FakeCoreController()
        slots = self._build_slots()

        connect_core_signals(controller, slots)

        for attr in (
            "devices_updated",
            "log_message",
            "operation_completed",
            "validation_result",
            "player_process_exited",
            "recording_state_changed",
            "files_listed_detailed",
            "symlink_resolved",
            "file_transfer_progress",
        ):
            signal = getattr(controller, attr)
            self.assertEqual(len(signal.connected_slots), 1)

    def test_disconnect_core_signals_with_none_is_noop(self):
        slots = self._build_slots()

        disconnect_core_signals(None, slots)

    def test_disconnect_core_signals_removes_all_slots(self):
        controller = _FakeCoreController()
        slots = self._build_slots()
        connect_core_signals(controller, slots)

        disconnect_core_signals(controller, slots)

        for attr in (
            "devices_updated",
            "log_message",
            "operation_completed",
            "validation_result",
            "player_process_exited",
            "recording_state_changed",
            "files_listed_detailed",
            "symlink_resolved",
            "file_transfer_progress",
        ):
            signal = getattr(controller, attr)
            self.assertEqual(len(signal.connected_slots), 0)

    def test_sync_core_runtime_returns_last_signature_when_controller_none(self):
        last_signature = ("adb", "内置 Sndcpy", False, "")

        result = sync_core_runtime(
            core_controller=None,
            settings={"adb_extra": ""},
            last_adb_signature=last_signature,
            resolve_paths=lambda: (_make_adb_resolution(), "player", "sndcpy"),
            log_to_console=lambda msg, level: None,
        )

        self.assertEqual(result, last_signature)

    def test_sync_core_runtime_configures_controller_and_returns_new_signature(self):
        controller = _FakeCoreController()
        resolution = _make_adb_resolution(path="adb-path", source="内置 Sndcpy")
        settings = {"adb_extra": "--a", "player_extra": "--p", "scrcpy_extra": "--s"}

        result = sync_core_runtime(
            core_controller=controller,
            settings=settings,
            adb_resolution=resolution,
            player_path="player-path",
            sndcpy_dir="sndcpy-dir",
            log_resolution=True,
            last_adb_signature=None,
            resolve_paths=lambda: (_make_adb_resolution(), "player", "sndcpy"),
            log_to_console=lambda msg, level: None,
        )

        self.assertEqual(len(controller.configure_calls), 1)
        request = controller.configure_calls[0]
        self.assertEqual(request.adb_path, "adb-path")
        self.assertEqual(request.player_path, "player-path")
        self.assertEqual(request.sndcpy_dir, "sndcpy-dir")
        self.assertEqual(request.adb_extra, "--a")
        self.assertIsNotNone(result)


class DeviceServiceCoordinatorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._app = QApplication.instance() or QApplication([])

    def test_submit_restart_adb_is_noop_with_none_controller(self):
        cooldown_calls: list[int] = []
        statuses: list[str] = []

        submit_restart_adb(
            core_controller=None,
            cooldown=lambda: cooldown_calls.append(1),
            set_status=statuses.append,
        )

        self.assertEqual(cooldown_calls, [])
        self.assertEqual(statuses, [])

    def test_submit_restart_adb_invokes_cooldown_and_request_restart(self):
        class _FakeController:
            def __init__(self):
                self.restart_calls = 0

            def request_restart_adb(self):
                self.restart_calls += 1

        controller = _FakeController()
        cooldown_calls: list[int] = []
        statuses: list[str] = []

        submit_restart_adb(
            core_controller=controller,
            cooldown=lambda: cooldown_calls.append(1),
            set_status=statuses.append,
        )

        self.assertEqual(controller.restart_calls, 1)
        self.assertEqual(cooldown_calls, [1])
        self.assertTrue(statuses)
        self.assertIn("ADB", statuses[0])

    def test_submit_kill_adb_is_noop_with_none_controller(self):
        cooldown_calls: list[int] = []
        statuses: list[str] = []

        submit_kill_adb(
            core_controller=None,
            cooldown=lambda: cooldown_calls.append(1),
            set_status=statuses.append,
        )

        self.assertEqual(cooldown_calls, [])
        self.assertEqual(statuses, [])

    def test_submit_kill_adb_invokes_request_force_kill(self):
        class _FakeController:
            def __init__(self):
                self.kill_calls = 0

            def request_force_kill_adb(self):
                self.kill_calls += 1

        controller = _FakeController()
        statuses: list[str] = []

        submit_kill_adb(
            core_controller=controller,
            cooldown=lambda: None,
            set_status=statuses.append,
        )

        self.assertEqual(controller.kill_calls, 1)
        self.assertTrue(statuses)
        self.assertIn("清理", statuses[0])

    def test_submit_install_sndcpy_is_noop_with_none_controller(self):
        cooldown_calls: list[int] = []
        statuses: list[str] = []
        busy_calls: list[int] = []

        submit_install_sndcpy(
            device_serial="device-1",
            core_controller=None,
            cooldown=lambda: cooldown_calls.append(1),
            set_status=statuses.append,
            show_busy_progress=lambda: busy_calls.append(1),
        )

        self.assertEqual(cooldown_calls, [])
        self.assertEqual(statuses, [])
        self.assertEqual(busy_calls, [])

    def test_submit_install_sndcpy_is_noop_with_empty_device(self):
        class _FakeController:
            def __init__(self):
                self.install_calls: list = []

            def request_install_apk(self, device_serial):
                self.install_calls.append(device_serial)

        controller = _FakeController()
        statuses: list[str] = []
        busy_calls: list[int] = []

        submit_install_sndcpy(
            device_serial="",
            core_controller=controller,
            cooldown=lambda: None,
            set_status=statuses.append,
            show_busy_progress=lambda: busy_calls.append(1),
        )

        self.assertEqual(controller.install_calls, [])
        self.assertEqual(statuses, [])
        self.assertEqual(busy_calls, [])

    def test_submit_install_sndcpy_invokes_request_install_apk(self):
        class _FakeController:
            def __init__(self):
                self.install_calls: list = []

            def request_install_apk(self, device_serial):
                self.install_calls.append(device_serial)

        controller = _FakeController()
        cooldown_calls: list[int] = []
        statuses: list[str] = []
        busy_calls: list[int] = []

        submit_install_sndcpy(
            device_serial="device-1",
            core_controller=controller,
            cooldown=lambda: cooldown_calls.append(1),
            set_status=statuses.append,
            show_busy_progress=lambda: busy_calls.append(1),
        )

        self.assertEqual(controller.install_calls, ["device-1"])
        self.assertEqual(cooldown_calls, [1])
        self.assertEqual(busy_calls, [1])
        self.assertTrue(statuses)
        self.assertIn("device-1", statuses[0])

    def test_finalize_operation_ui_hides_progress_and_sets_status(self):
        hide_calls: list[int] = []
        statuses: list[str] = []

        finalize_operation_ui(
            "audio_route",
            True,
            hide_progress=lambda: hide_calls.append(1),
            set_status=statuses.append,
        )

        self.assertEqual(hide_calls, [1])
        self.assertEqual(statuses, ["音频路由启动成功"])

    def test_finalize_operation_ui_shows_install_result_for_install_operation(self):
        hide_calls: list[int] = []
        statuses: list[str] = []
        install_results: list[bool] = []

        finalize_operation_ui(
            "install",
            False,
            hide_progress=lambda: hide_calls.append(1),
            set_status=statuses.append,
            show_install_result=install_results.append,
        )

        self.assertEqual(hide_calls, [1])
        self.assertEqual(statuses, ["APK安装失败"])
        self.assertEqual(install_results, [False])

    def test_finalize_operation_ui_skips_install_result_for_non_install(self):
        install_results: list[bool] = []

        finalize_operation_ui(
            "video_route",
            True,
            hide_progress=lambda: None,
            set_status=lambda _: None,
            show_install_result=install_results.append,
        )

        self.assertEqual(install_results, [])


class RequestBuildersTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._app = QApplication.instance() or QApplication([])

    def test_build_routing_request_maps_all_fields(self):
        request = build_routing_request(
            device_serial="device-1",
            enable_audio=True,
            enable_video=False,
            video_bitrate=8000,
            max_size="1080",
            lock_ori_index=1,
            show_fps=True,
            stay_awake=False,
            turn_screen_off=True,
        )

        self.assertEqual(request.device_serial, "device-1")
        self.assertTrue(request.enable_audio)
        self.assertFalse(request.enable_video)
        self.assertEqual(request.video_bitrate, 8000)
        self.assertEqual(request.max_size, "1080")
        self.assertEqual(request.lock_ori_index, 1)
        self.assertTrue(request.show_fps)
        self.assertFalse(request.stay_awake)
        self.assertTrue(request.turn_screen_off)
        self.assertEqual(request.audio_port, 28200)

    def test_build_routing_request_supports_custom_audio_port(self):
        request = build_routing_request(
            device_serial="device-1",
            enable_audio=True,
            enable_video=True,
            video_bitrate=4000,
            max_size="原始",
            lock_ori_index=0,
            show_fps=False,
            stay_awake=True,
            turn_screen_off=False,
            audio_port=9999,
        )

        self.assertEqual(request.audio_port, 9999)

    def test_build_recording_request_forces_bg_mode_true(self):
        request = build_recording_request(
            device_serial="device-1",
            save_path="D:/records/audio.wav",
            record_video=False,
            record_audio=True,
            record_ori_index=2,
        )

        self.assertTrue(request.bg_mode)
        self.assertEqual(request.device_serial, "device-1")
        self.assertEqual(request.save_path, "D:/records/audio.wav")
        self.assertFalse(request.record_video)
        self.assertTrue(request.record_audio)
        self.assertEqual(request.record_ori_index, 2)

    def test_build_console_command_request_scrcpy_target(self):
        request = build_console_command_request("shell", CONSOLE_TARGET_SCRCPY)

        self.assertEqual(request.command_str, "shell")
        self.assertEqual(request.target_kind, ConsoleTargetKind.SCRCPY)
        self.assertEqual(request.device_serial, "")

    def test_build_console_command_request_adb_device_target(self):
        request = build_console_command_request("devices", "device-1")

        self.assertEqual(request.command_str, "devices")
        self.assertEqual(request.target_kind, ConsoleTargetKind.ADB_DEVICE)
        self.assertEqual(request.device_serial, "device-1")

    def test_build_console_command_request_no_device_target_defaults_to_global(self):
        request = build_console_command_request("kill-server", CONSOLE_TARGET_NO_DEVICE)

        self.assertEqual(request.target_kind, ConsoleTargetKind.ADB_GLOBAL)
        self.assertEqual(request.device_serial, "")

    def test_build_push_file_request_adds_trailing_slash_to_remote_dir(self):
        request = build_push_file_request(
            device_serial="device-1",
            local_path="D:/local/song.mp3",
            remote_dir="/sdcard/Music",
        )

        self.assertEqual(request.device_serial, "device-1")
        self.assertEqual(request.local_path, "D:/local/song.mp3")
        self.assertEqual(request.remote_dir, "/sdcard/Music/")
        self.assertIsNone(request.rename_to)

    def test_build_push_file_request_preserves_rename_to(self):
        request = build_push_file_request(
            device_serial="device-1",
            local_path="D:/local/song.mp3",
            remote_dir="/sdcard/Music/",
            rename_to="renamed.mp3",
        )

        self.assertEqual(request.remote_dir, "/sdcard/Music/")
        self.assertEqual(request.rename_to, "renamed.mp3")

    def test_build_pull_file_request_maps_fields(self):
        request = build_pull_file_request(
            device_serial="device-1",
            remote_path="/sdcard/Music/song.mp3",
            local_dir="D:/Downloads",
        )

        self.assertEqual(request.device_serial, "device-1")
        self.assertEqual(request.remote_path, "/sdcard/Music/song.mp3")
        self.assertEqual(request.local_dir, "D:/Downloads")
        self.assertIsNone(request.rename_to)

    def test_build_pull_file_request_supports_rename(self):
        request = build_pull_file_request(
            device_serial="device-1",
            remote_path="/sdcard/Music/song.mp3",
            local_dir="D:/Downloads",
            rename_to="song_copy.mp3",
        )

        self.assertEqual(request.rename_to, "song_copy.mp3")

    def test_build_browse_files_request_maps_fields(self):
        request = build_browse_files_request("device-1", "/sdcard/Music/")

        self.assertEqual(request.device_serial, "device-1")
        self.assertEqual(request.remote_path, "/sdcard/Music/")


# ===== ConsoleLoggerCoordinator 冒烟测试 =====
class ConsoleLoggerCoordinatorTests(unittest.TestCase):
    def setUp(self):
        self._app = QApplication.instance() or QApplication([])

    def test_emit_writes_html_to_console_output(self):
        console = QTextEdit()
        coordinator = ConsoleLoggerCoordinator(console_output=console)

        coordinator.emit("hello world", "info")

        self.assertIn("hello world", console.toPlainText())

    def test_emit_drops_empty_message(self):
        console = QTextEdit()
        coordinator = ConsoleLoggerCoordinator(console_output=console)

        coordinator.emit("   ", "info")

        self.assertEqual(console.toPlainText(), "")
        self.assertIsNone(coordinator.last_log_signature)

    def test_emit_dedups_repeated_message_within_window(self):
        console = QTextEdit()
        coordinator = ConsoleLoggerCoordinator(console_output=console)

        coordinator.emit("dup", "info")
        coordinator.emit("dup", "info")

        # 第二次因签名+时间窗口去重被丢弃，控制台仅有一条
        self.assertEqual(console.toPlainText().count("dup"), 1)

    def test_emit_accepts_distinct_messages_back_to_back(self):
        console = QTextEdit()
        coordinator = ConsoleLoggerCoordinator(console_output=console)

        coordinator.emit("first", "info")
        coordinator.emit("second", "warning")

        self.assertIn("first", console.toPlainText())
        self.assertIn("second", console.toPlainText())

    def test_emit_records_signature_and_time_after_write(self):
        console = QTextEdit()
        coordinator = ConsoleLoggerCoordinator(console_output=console)

        coordinator.emit("tracked", "success")

        self.assertEqual(coordinator.last_log_signature, ("success", "tracked"))
        self.assertIsNotNone(coordinator.last_log_time)


# ===== startup_coordinator 冒烟测试 =====
class StartupCoordinatorTests(unittest.TestCase):
    def test_returns_true_when_usb_monitor_starts_successfully(self):
        logs: list[tuple[str, str]] = []
        calls: list[str] = []

        class _UsbMonitor:
            def start_monitoring(self):
                calls.append("start")

        ok = run_startup_routine(
            log_to_console=lambda msg, level: logs.append((msg, level)),
            validate_paths=lambda: calls.append("validate"),
            usb_monitor=_UsbMonitor(),
        )

        self.assertTrue(ok)
        self.assertEqual(calls, ["validate", "start"])
        self.assertTrue(any(level == "info" for _, level in logs))
        self.assertTrue(any(level == "success" for _, level in logs))

    def test_returns_false_when_usb_monitor_is_none(self):
        calls: list[str] = []
        ok = run_startup_routine(
            log_to_console=lambda msg, level: None,
            validate_paths=lambda: calls.append("validate"),
            usb_monitor=None,
        )

        self.assertFalse(ok)
        self.assertEqual(calls, ["validate"])

    def test_returns_false_and_logs_warning_when_start_raises(self):
        logs: list[tuple[str, str]] = []

        class _FailingMonitor:
            def start_monitoring(self):
                raise RuntimeError("boom")

        ok = run_startup_routine(
            log_to_console=lambda msg, level: logs.append((msg, level)),
            validate_paths=lambda: None,
            usb_monitor=_FailingMonitor(),
        )

        self.assertFalse(ok)
        self.assertTrue(any(level == "warning" and "boom" in msg for msg, level in logs))

    def test_validate_paths_is_called_before_usb_monitor_start(self):
        order: list[str] = []

        class _UsbMonitor:
            def start_monitoring(self):
                order.append("usb")

        run_startup_routine(
            log_to_console=lambda msg, level: None,
            validate_paths=lambda: order.append("validate"),
            usb_monitor=_UsbMonitor(),
        )

        self.assertEqual(order, ["validate", "usb"])


# ===== teardown_coordinator 冒烟测试 =====
class _StubEvent:
    def __init__(self):
        self.calls: list[str] = []

    def accept(self):
        self.calls.append("accept")

    def ignore(self):
        self.calls.append("ignore")


class TeardownCoordinatorTests(unittest.TestCase):
    def test_force_quit_skips_confirmation_and_accepts_event(self):
        event = _StubEvent()
        calls: list[str] = []

        result = handle_close_event(
            event=event,
            force_quit=True,
            confirm_exit=lambda: (_ for _ in ()).throw(AssertionError("不应弹出确认")),
            hide_to_tray=lambda: calls.append("hide"),
            save_settings=lambda: calls.append("save"),
            usb_monitor=None,
            core_controller=None,
            log_to_console=lambda msg, level: None,
            scan_timer=None,
            tray_icon=None,
        )

        self.assertEqual(result, ExitAction.EXIT)
        self.assertEqual(event.calls, ["accept"])
        self.assertIn("save", calls)

    def test_hide_to_tray_ignores_event_and_returns_tray_action(self):
        event = _StubEvent()
        calls: list[str] = []

        result = handle_close_event(
            event=event,
            force_quit=False,
            confirm_exit=lambda: ExitAction.HIDE_TO_TRAY,
            hide_to_tray=lambda: calls.append("hide"),
            save_settings=lambda: calls.append("save"),
            usb_monitor=None,
            core_controller=None,
            log_to_console=lambda msg, level: None,
            scan_timer=None,
            tray_icon=None,
        )

        self.assertEqual(result, ExitAction.HIDE_TO_TRAY)
        self.assertEqual(event.calls, ["ignore"])
        self.assertIn("hide", calls)
        self.assertNotIn("save", calls)

    def test_cancel_action_ignores_event_without_cleanup(self):
        event = _StubEvent()
        calls: list[str] = []

        result = handle_close_event(
            event=event,
            force_quit=False,
            confirm_exit=lambda: ExitAction.CANCEL,
            hide_to_tray=lambda: calls.append("hide"),
            save_settings=lambda: calls.append("save"),
            usb_monitor=None,
            core_controller=None,
            log_to_console=lambda msg, level: None,
            scan_timer=None,
            tray_icon=None,
        )

        self.assertEqual(result, ExitAction.CANCEL)
        self.assertEqual(event.calls, ["ignore"])
        self.assertEqual(calls, [])

    def test_exit_action_stops_usb_monitor_and_waits_for_core_shutdown(self):
        event = _StubEvent()
        usb_calls: list[str] = []
        shutdown_calls: list[tuple[str, int]] = []

        result = handle_close_event(
            event=event,
            force_quit=False,
            confirm_exit=lambda: ExitAction.EXIT,
            hide_to_tray=lambda: None,
            save_settings=lambda: None,
            usb_monitor=SimpleNamespace(stop_monitoring=lambda: usb_calls.append("stop")),
            core_controller=SimpleNamespace(
                request_shutdown_and_wait=lambda timeout=0: shutdown_calls.append(("shutdown", timeout)) or True,
            ),
            log_to_console=lambda msg, level: None,
            scan_timer=None,
            tray_icon=None,
        )

        self.assertEqual(result, ExitAction.EXIT)
        self.assertEqual(usb_calls, ["stop"])
        self.assertIn(("shutdown", 8), shutdown_calls)
        self.assertEqual(event.calls, ["accept"])

    def test_shutdown_timeout_logs_warning_but_still_accepts(self):
        event = _StubEvent()
        logs: list[tuple[str, str]] = []

        result = handle_close_event(
            event=event,
            force_quit=True,
            confirm_exit=lambda: ExitAction.EXIT,
            hide_to_tray=lambda: None,
            save_settings=lambda: None,
            usb_monitor=None,
            core_controller=SimpleNamespace(
                request_shutdown_and_wait=lambda timeout=0: False,
            ),
            log_to_console=lambda msg, level: logs.append((msg, level)),
            scan_timer=None,
            tray_icon=None,
        )

        self.assertEqual(result, ExitAction.EXIT)
        self.assertEqual(event.calls, ["accept"])
        self.assertTrue(any(level == "warning" and "超时" in msg for msg, level in logs))

    def test_active_scan_timer_is_stopped_on_exit(self):
        event = _StubEvent()
        timer_calls: list[str] = []

        class _Timer:
            def isActive(self):
                return True

            def stop(self):
                timer_calls.append("stop")

        handle_close_event(
            event=event,
            force_quit=True,
            confirm_exit=lambda: ExitAction.EXIT,
            hide_to_tray=lambda: None,
            save_settings=lambda: None,
            usb_monitor=None,
            core_controller=None,
            log_to_console=lambda msg, level: None,
            scan_timer=_Timer(),
            tray_icon=None,
        )

        self.assertEqual(timer_calls, ["stop"])

    def test_tray_icon_is_hidden_on_exit(self):
        event = _StubEvent()
        tray_calls: list[str] = []

        handle_close_event(
            event=event,
            force_quit=True,
            confirm_exit=lambda: ExitAction.EXIT,
            hide_to_tray=lambda: None,
            save_settings=lambda: None,
            usb_monitor=None,
            core_controller=None,
            log_to_console=lambda msg, level: None,
            scan_timer=None,
            tray_icon=SimpleNamespace(hide=lambda: tray_calls.append("hide")),
        )

        self.assertEqual(tray_calls, ["hide"])


if __name__ == "__main__":
    unittest.main()
