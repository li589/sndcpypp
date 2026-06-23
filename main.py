import sys
import os
from dataclasses import dataclass
from datetime import datetime
from typing import Any
from PyQt6.QtCore import Qt, pyqtSignal, QTimer, pyqtSlot
from PyQt6.QtGui import QTextCursor
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QLabel, QLineEdit, QPushButton,
    QSystemTrayIcon, QTableWidgetItem
)

from app.domain.models.operation_requests import (
    BrowseFilesRequest,
    ConsoleCommandRequest,
    ConsoleTargetKind,
    PullFileRequest,
    PushFileRequest,
    RecordingRequest,
    RecordingState,
    RecordingStateEvent,
    RoutingRequest,
)
from app.infrastructure.adb.path_resolver import ADBPathResolver, ResolvedADBPath
from app.infrastructure.config.settings_store import JsonSettingsStore
from app.ui.console_actions import submit_console_command
from app.ui.device_page_controller import DevicePageController
from app.ui.device_runtime_coordinator import apply_validation_result_ui
from app.ui.device_service_coordinator import (
    finalize_operation_ui,
    submit_adb_service_action,
)
from app.ui.device_actions import (
    submit_device_start_action,
    submit_scoped_stop_action,
)
from app.ui.file_actions import submit_upload_requests
from app.ui.file_page_controller import FilePageController
from app.ui.dialogs import ExitAction
from app.ui.file_table_presenter import populate_file_table, update_symlink_in_table
from app.ui.interaction_helpers import (
    cooldown_buttons,
    ensure_trailing_slash,
)
from app.ui.main_window_shell import (
    force_exit,
    handle_window_context_menu,
    hide_to_tray,
    is_foreground_fullscreen,
    init_tray_icon,
    minimize_all_windows,
    show_tray_message,
    show_main_window,
    toggle_top_window,
    tray_icon_activated,
)
from app.ui.menu_coordinator import show_console_context_menu
from app.ui.main_window_ui import build_main_window_ui, configure_main_window_shell
from app.ui.pages.console_page import CONSOLE_TARGET_NO_DEVICE, CONSOLE_TARGET_SCRCPY
from app.ui.message_templates import (
    file_status_read_failed,
    log_adb_resolution_builtin,
    log_adb_resolution_external,
    log_adb_resolution_fallback,
    log_adb_resolution_unresolved,
    log_auto_validation_starting_adb,
    log_cleanup_processes,
    log_extra_params_updated,
    log_initial_validation,
    log_loaded_items,
    log_settings_load_warning,
    log_settings_save_failed,
    status_recording_active,
    status_recording_active_multi,
    status_recording_failed,
    status_recording_finished,
    log_symlink_resolved,
    log_usb_monitor_init_failed,
    log_usb_monitor_start_failed,
    log_usb_monitor_started,
    render_console_html,
    status_audio_route_submitted,
    status_installing,
    status_recording_preparing,
    status_routing_submitted,
    status_usb_refresh_pending,
    tray_recording_reminder_message,
    tray_recording_reminder_title,
)
from app.ui.popup_manager import PopupManager
from app.ui.recording_actions import prepare_recording_start
from app.ui.runtime_settings import (
    apply_ui_settings,
    build_runtime_configuration_request,
    collect_ui_settings,
    resolve_runtime_paths,
)
from core import CoreController, FileInfo, FileType


@dataclass(slots=True)
class RecordingSessionState:
    save_path: str
    started_at: datetime
    reminder_sent: bool = False


class SndcpyGUI(QMainWindow):
    usb_event_signal = pyqtSignal() 
    LONG_RECORDING_REMINDER_SECONDS = 30 * 60

    def __init__(self):
        super().__init__()
        self.setAttribute(Qt.WidgetAttribute.WA_QuitOnClose)
        configure_main_window_shell(self)
        
        self.core_controller = None
        self.settings_file = "settings.json"
        self.settings_store = JsonSettingsStore(self.settings_file)
        self._pending_settings_load_warning: str | None = None
        self.settings = self.load_json_settings()
        self.app_base_dir = os.path.dirname(os.path.abspath(__file__))
        self.adb_path_resolver = ADBPathResolver(self.app_base_dir)
        self.popups = PopupManager(self, audit_callback=self.log_to_console)
        self.auto_refresh_value = 0
        
        self._is_first_startup = True
        self.is_adb_valid = False
        self.are_paths_ready = False
        self.current_remote_path = "/sdcard/"
        self.force_quit = False
        self.is_top = False
        self._last_log_signature: tuple[str, str] | None = None
        self._last_log_time: datetime | None = None
        self._last_adb_resolution_signature: tuple[str, str, bool, str] | None = None
        self._recording_sessions: dict[str, RecordingSessionState] = {}
        
        build_main_window_ui(self)
        if self._pending_settings_load_warning:
            self.log_to_console(log_settings_load_warning(self._pending_settings_load_warning), "warning")
        self.file_page_controller = self._create_file_page_controller()
        self.load_settings()
        self.init_tray_icon()

        self.recording_status_timer = QTimer(self)
        self.recording_status_timer.setInterval(1000)
        self.recording_status_timer.timeout.connect(self._refresh_recording_status)

        self.recording_reminder_timer = QTimer(self)
        self.recording_reminder_timer.setInterval(60_000)
        self.recording_reminder_timer.timeout.connect(self._check_long_recording_reminders)
        
        self.scan_timer = QTimer(self)
        self.scan_timer.timeout.connect(self.auto_refresh_devices)
        
        self.usb_debounce_timer = QTimer(self)
        self.usb_debounce_timer.setSingleShot(True)
        self.usb_debounce_timer.timeout.connect(self.manual_refresh_devices)
        self.usb_event_signal.connect(self.trigger_usb_debounce)
        
        try:
            from app.infrastructure.adb.UsbMonitor import CrossPlatformUSBMonitor
            self.usb_monitor = CrossPlatformUSBMonitor()
            self.usb_monitor.on_connect(lambda d: self.usb_event_signal.emit())
            self.usb_monitor.on_disconnect(lambda d: self.usb_event_signal.emit())
        except Exception as e:
            self.usb_monitor = None
            self.log_to_console(log_usb_monitor_init_failed(str(e)), "warning")
        
        self.status_bar = self.statusBar()
        self.status_label = QLabel("就绪")
        self.status_bar.addPermanentWidget(self.status_label)
        self.device_page_controller = self._create_device_page_controller()
        
        QTimer.singleShot(1000, self.startup_routine)

    def init_tray_icon(self):
        init_tray_icon(self)

    def tray_icon_activated(self, reason):
        tray_icon_activated(self, reason)

    def show_main_window(self):
        show_main_window(self)

    def contextMenuEvent(self, event):
        handle_window_context_menu(self, event.globalPos())

    def minimize_all_windows(self):
        minimize_all_windows(self)

    def toggle_top_window(self):
        toggle_top_window(self)

    def close_only_action(self):
        hide_to_tray(self)

    def full_exit_action(self):
        force_exit(self)

    @pyqtSlot()
    def trigger_usb_debounce(self):
        self.usb_debounce_timer.start(1500)
        self.status_label.setText(status_usb_refresh_pending())
        
    def startup_routine(self):
        self.log_to_console(log_initial_validation(), "info")
        self.validate_paths()
        if hasattr(self, 'usb_monitor') and self.usb_monitor:
            try:
                self.usb_monitor.start_monitoring()
            except Exception as e:
                self.usb_monitor = None
                self.log_to_console(log_usb_monitor_start_failed(str(e)), "warning")
            else:
                self.log_to_console(log_usb_monitor_started(), "success")

    def set_auto_refresh_value(self, value: int):
        self.auto_refresh_value = value
        if self.auto_refresh_value: self.scan_timer.start(3000)
        else: self.scan_timer.stop()

    def browse_file(self, target_edit: QLineEdit, file_filter: str="所有文件 (*.*)"):
        file_path = self.popups.open_file("选择文件", target_edit.text().strip(), file_filter)
        if file_path:
            target_edit.setText(file_path)
            self.save_settings()

    def browse_folder(self, target_edit: QLineEdit):
        folder_path = self.popups.select_directory("选择文件夹", target_edit.text().strip())
        if folder_path:
            target_edit.setText(folder_path)
            self.save_settings()

    def show_console_menu(self, pos):
        show_console_context_menu(self.console_output, pos, self.popups)

    @pyqtSlot()
    def validate_paths(self):
        self._cooldown_buttons([self.validate_btn], 700, self._restore_validation_button)
        if not self.core_controller: self.init_core_controller()
        self._sync_core_runtime()
        if self.core_controller:
            self.core_controller.request_validate_runtime()
    
    def init_core_controller(self):
        previous_controller = self.core_controller
        if previous_controller:
            self._disconnect_core_signals(previous_controller)
            previous_controller.request_shutdown()
            previous_controller.deleteLater()

        adb_resolution, player_path, sndcpy_dir = self.resolve_runtime_paths()
        self._maybe_log_adb_resolution(adb_resolution)
        self.core_controller = CoreController(adb_resolution.path, player_path, sndcpy_dir)
        self._sync_core_runtime(adb_resolution, player_path, sndcpy_dir, log_resolution=False)
        self._connect_core_signals(self.core_controller)

    def resolve_runtime_paths(self) -> tuple[ResolvedADBPath, str, str]:
        adb_resolution, player_path, sndcpy_dir = resolve_runtime_paths(
            self.adb_path_edit.text(),
            self.player_path_edit.text(),
            self.sndcpy_dir_edit.text(),
            adb_path_resolver=self.adb_path_resolver,
            app_base_dir=self.app_base_dir,
        )
        self.adb_path_edit.setToolTip(
            "留空时自动优先尝试外部 ADB，失败后回退到内置 ADB。\n"
            f"当前解析: {adb_resolution.source}\n{adb_resolution.path}"
        )
        return adb_resolution, player_path, sndcpy_dir

    def _maybe_log_adb_resolution(self, adb_resolution: ResolvedADBPath) -> None:
        signature = (
            adb_resolution.path,
            adb_resolution.source,
            adb_resolution.used_fallback,
            adb_resolution.requested_path,
        )
        if signature == self._last_adb_resolution_signature:
            return

        self._last_adb_resolution_signature = signature
        if adb_resolution.requested_path and adb_resolution.used_fallback:
            self.log_to_console(
                log_adb_resolution_fallback(adb_resolution.source, adb_resolution.path),
                "warning",
            )
            return

        if adb_resolution.source == "内置 Sndcpy":
            self.log_to_console(log_adb_resolution_builtin(adb_resolution.path), "info")
            return

        if adb_resolution.source != "未解析":
            self.log_to_console(log_adb_resolution_external(adb_resolution.source, adb_resolution.path), "success")
            return

        self.log_to_console(log_adb_resolution_unresolved(adb_resolution.path), "warning")

    def _sync_core_runtime(
        self,
        adb_resolution: ResolvedADBPath | None = None,
        player_path: str | None = None,
        sndcpy_dir: str | None = None,
        log_resolution: bool = True,
    ):
        if not self.core_controller:
            return

        if adb_resolution is None or player_path is None or sndcpy_dir is None:
            adb_resolution, player_path, sndcpy_dir = self.resolve_runtime_paths()

        if log_resolution:
            self._maybe_log_adb_resolution(adb_resolution)

        self.core_controller.request_configure_runtime(
            build_runtime_configuration_request(self.settings, adb_resolution, player_path, sndcpy_dir)
        )

    def _connect_core_signals(self, controller: CoreController | None = None):
        controller = controller or self.core_controller
        if not controller:
            return
        controller.devices_updated.connect(self.update_device_list)
        controller.log_message.connect(self.log_to_console)
        controller.operation_completed.connect(self.handle_operation_complete)
        controller.validation_result.connect(self.handle_validation_result)
        controller.player_process_exited.connect(self.handle_player_exit)
        controller.recording_state_changed.connect(self.handle_recording_state_change)
        controller.files_listed_detailed.connect(self.update_file_table)
        controller.symlink_resolved.connect(self.handle_symlink_resolved)
        controller.file_transfer_progress.connect(self.handle_file_progress)

    def _disconnect_core_signals(self, controller: CoreController | None):
        if controller is None:
            return
        signal_pairs = [
            (controller.devices_updated, self.update_device_list),
            (controller.log_message, self.log_to_console),
            (controller.operation_completed, self.handle_operation_complete),
            (controller.validation_result, self.handle_validation_result),
            (controller.player_process_exited, self.handle_player_exit),
            (controller.recording_state_changed, self.handle_recording_state_change),
            (controller.files_listed_detailed, self.update_file_table),
            (controller.symlink_resolved, self.handle_symlink_resolved),
            (controller.file_transfer_progress, self.handle_file_progress),
        ]
        for signal, slot in signal_pairs:
            try:
                signal.disconnect(slot)
            except TypeError:
                pass

    def _build_routing_request(self, device_serial: str) -> RoutingRequest:
        return RoutingRequest(
            device_serial=device_serial,
            enable_audio=self.audio_check.isChecked(),
            enable_video=self.video_check.isChecked(),
            video_bitrate=self.video_bitrate.value(),
            max_size=self.max_size_combo.currentText(),
            lock_ori_index=self.lock_ori_combo.currentIndex(),
            show_fps=self.fps_check.isChecked(),
            stay_awake=self.stay_awake_check.isChecked(),
            turn_screen_off=self.screen_off_check.isChecked(),
            audio_port=28200,
        )

    def _build_recording_request(self, device_serial: str, save_path: str) -> RecordingRequest:
        return RecordingRequest(
            device_serial=device_serial,
            save_path=save_path,
            bg_mode=True,
            record_video=self.rec_video_check.isChecked(),
            record_audio=self.rec_audio_check.isChecked(),
            record_ori_index=self.rec_ori_combo.currentIndex(),
        )

    def _build_browse_files_request(self, device_serial: str, remote_path: str) -> BrowseFilesRequest:
        return BrowseFilesRequest(device_serial=device_serial, remote_path=remote_path)

    def _build_console_command_request(self, command_str: str) -> ConsoleCommandRequest:
        selected_target = self.device_combo.currentText()
        target_kind = ConsoleTargetKind.ADB_GLOBAL
        device_serial = ""

        if selected_target == CONSOLE_TARGET_SCRCPY:
            target_kind = ConsoleTargetKind.SCRCPY
        elif selected_target and selected_target != CONSOLE_TARGET_NO_DEVICE:
            target_kind = ConsoleTargetKind.ADB_DEVICE
            device_serial = selected_target

        return ConsoleCommandRequest(
            command_str=command_str,
            target_kind=target_kind,
            device_serial=device_serial,
        )

    def _build_push_file_request(self, device_serial: str, local_path: str, rename_to: str | None = None) -> PushFileRequest:
        return PushFileRequest(
            device_serial=device_serial,
            local_path=local_path,
            remote_dir=ensure_trailing_slash(self.current_remote_path),
            rename_to=rename_to,
        )

    def _build_pull_file_request(
        self,
        device_serial: str,
        remote_path: str,
        local_dir: str,
        rename_to: str | None = None,
    ) -> PullFileRequest:
        return PullFileRequest(
            device_serial=device_serial,
            remote_path=remote_path,
            local_dir=local_dir,
            rename_to=rename_to,
        )

    def _cooldown_buttons(self, buttons: list[QPushButton], ms: int = 900, restore_callback=None):
        cooldown_buttons(buttons, ms, restore_callback)

    def _restore_validation_actions(self):
        self.install_btn.setEnabled(self.are_paths_ready)
        self.start_btn.setEnabled(self.are_paths_ready)

    def _restore_validation_button(self):
        self.validate_btn.setEnabled(True)

    def _show_busy_progress(self):
        self.progress_bar.setVisible(True)
        self.progress_bar.setRange(0, 0)

    def _create_file_page_controller(self) -> FilePageController:
        return FilePageController(
            host_widget=self,
            file_device_combo=self.file_device_combo,
            remote_path_edit=self.remote_path_edit,
            file_table=self.file_table,
            local_down_edit=self.local_down_edit,
            core_provider=lambda: self.core_controller,
            popups=self.popups,
            log_to_console=self.log_to_console,
            request_list_files=lambda device, remote_path: self.core_controller.request_list_device_files(
                self._build_browse_files_request(device, remote_path)
            ) if self.core_controller else None,
            request_pull=lambda device, remote_file, local_dir, rename_to: self.core_controller.request_pull_file(
                self._build_pull_file_request(device, remote_file, local_dir, rename_to)
            ) if self.core_controller else None,
        )

    def _create_device_page_controller(self) -> DevicePageController:
        return DevicePageController(
            device_list=self.device_list,
            refresh_devices_button=self.refresh_devices_btn,
            device_combo=self.device_combo,
            recording_device_combo=self.rec_device_combo,
            file_device_combo=self.file_device_combo,
            status_setter=self.status_label.setText,
            show_device_required_warning=self.popups.show_device_required_warning,
            core_provider=lambda: self.core_controller,
            is_adb_valid_provider=lambda: self.is_adb_valid,
            auto_refresh_value_provider=lambda: self.auto_refresh_value,
        )

    def open_cmd_settings(self, cmd_type: str):
        titles = {"adb": "ADB", "player": "播放器", "scrcpy": "Scrcpy"}
        key = f"{cmd_type}_extra"
        updated_value = self.popups.open_param_settings(cmd_type, str(self.settings.get(key, "")))
        if updated_value is not None:
            self.settings[key] = updated_value
            self.save_settings()
            if self.core_controller:
                self._sync_core_runtime()
            self.log_to_console(log_extra_params_updated(titles.get(cmd_type)), "info")

    @pyqtSlot(list)
    def handle_validation_result(self, results: list[int]):
        ui_result = apply_validation_result_ui(
            results,
            is_first_startup=self._is_first_startup,
            set_status=self.status_label.setText,
            restore_validation_actions=self._restore_validation_actions,
            on_first_ready=self._handle_first_runtime_ready if self._is_first_startup else None,
        )
        self.is_adb_valid = ui_result.adb_valid
        self.are_paths_ready = ui_result.are_paths_ready
        self._is_first_startup = ui_result.next_first_startup

    def _handle_first_runtime_ready(self):
        if self.core_controller:
            self.core_controller.request_prewarm_scrcpy_capabilities()
        self.log_to_console(log_auto_validation_starting_adb(), "success")
        if self.core_controller:
            self.core_controller.request_start_adb_server()
        QTimer.singleShot(1500, self.manual_refresh_devices)

    @pyqtSlot()
    def auto_refresh_devices(self):
        self.device_page_controller.auto_refresh_devices()

    @pyqtSlot()
    def manual_refresh_devices(self):
        self.device_page_controller.manual_refresh_devices()

    @pyqtSlot(list)
    def update_device_list(self, devices: list[str]):
        self.device_page_controller.update_device_list(devices)
    
    def get_selected_device(self, show_warning: bool = True):
        return self.device_page_controller.get_selected_device(show_warning)
    
    @pyqtSlot()
    def install_sndcpy(self):
        device = self.get_selected_device()
        if device and self.core_controller:
            submit_device_start_action(
                device,
                before_submit=lambda: self._cooldown_buttons(
                    [self.install_btn], 1500, self._restore_validation_actions
                ),
                submit=self.core_controller.request_install_apk,
                set_status=self.status_label.setText,
                status_text=status_installing(device),
                after_submit=self._show_busy_progress,
            )
            
    @pyqtSlot()
    def start_routing(self):
        device = self.get_selected_device()
        if device and self.core_controller:
            submit_device_start_action(
                device,
                before_submit=lambda: self._cooldown_buttons(
                    [self.start_btn], 1200, self._restore_validation_actions
                ),
                submit=lambda serial: self.core_controller.request_start_routing_session(
                    self._build_routing_request(serial)
                ),
                set_status=self.status_label.setText,
                status_text=status_routing_submitted(device),
                after_submit=self._show_busy_progress,
            )

    @pyqtSlot()
    def start_audio_only(self):
        device = self.get_selected_device()
        if device and self.core_controller:
            submit_device_start_action(
                device,
                before_submit=lambda: self._cooldown_buttons([self.start_audio_btn], 1000),
                submit=lambda serial: self.core_controller.request_start_audio_route(serial, port=28200),
                set_status=self.status_label.setText,
                status_text=status_audio_route_submitted(device),
            )

    @pyqtSlot()
    def stop_audio_only(self):
        if self.core_controller:
            device = self.get_selected_device(show_warning=False)
            submit_scoped_stop_action(
                device_serial=device,
                before_submit=lambda: self._cooldown_buttons([self.pause_audio_btn], 1000),
                submit=self.core_controller.request_stop_audio_routes,
                set_status=self.status_label.setText,
                device_template="独立音频停止指令已发送 ({device})",
                all_devices_text="所有独立音频停止指令已发送",
            )
    
    def stop_routing(self):
        if self.core_controller:
            device = self.get_selected_device(show_warning=False)
            submit_scoped_stop_action(
                device_serial=device,
                before_submit=lambda: self._cooldown_buttons([self.stop_btn], 1000),
                submit=self.core_controller.request_stop_streaming,
                set_status=self.status_label.setText,
                device_template="流媒体路由停止指令已发送 ({device})",
                all_devices_text="所有设备流媒体路由停止指令已发送",
                after_submit=lambda: self.progress_bar.setVisible(False),
            )
            
    @pyqtSlot()
    def start_recording_ui(self):
        device = self.rec_device_combo.currentText()
        if not device:
            self.popups.show_recording_device_required_warning()
            return
            
        if not self.core_controller:
            return

        full_path = prepare_recording_start(
            device_serial=device,
            record_dir=self.record_dir_edit.text().strip(),
            file_ext=self.rec_format_combo.currentText(),
            filename_input=self.rec_filename_edit.text().strip(),
            record_video=self.rec_video_check.isChecked(),
            record_audio=self.rec_audio_check.isChecked(),
            is_audio_running=self.core_controller.is_audio_running(device),
            popups=self.popups,
            set_status=self.status_label.setText,
            before_prepare=lambda: self._cooldown_buttons([self.start_rec_btn], 2000),
        )
        if full_path is None:
            return

        self.core_controller.request_start_recording(self._build_recording_request(device, full_path))
        self.status_label.setText(status_recording_preparing(device))

    @pyqtSlot()
    def stop_recording_ui(self):
        device = self.rec_device_combo.currentText()
        if self.core_controller:
            submit_scoped_stop_action(
                device_serial=device,
                before_submit=lambda: self._cooldown_buttons([self.stop_rec_btn], 2000),
                submit=self.core_controller.request_stop_recording,
                set_status=self.status_label.setText,
                device_template="录制停止指令已发送 ({device})",
                all_devices_text="录制停止指令已发送 (所有设备)",
            )

    @pyqtSlot(object)
    def handle_recording_state_change(self, event: RecordingStateEvent):
        if event.state == RecordingState.STARTED:
            self._recording_sessions[event.device_serial] = RecordingSessionState(
                save_path=event.payload,
                started_at=datetime.now(),
            )
            if not self.recording_status_timer.isActive():
                self.recording_status_timer.start()
            if not self.recording_reminder_timer.isActive():
                self.recording_reminder_timer.start()
            self._refresh_recording_status()
            return

        if event.state == RecordingState.STOPPED:
            self._recording_sessions.pop(event.device_serial, None)
            self._stop_recording_timers_if_idle()
            self.status_label.setText(status_recording_finished(event.device_serial))
            return

        if event.state == RecordingState.FAILED:
            self._recording_sessions.pop(event.device_serial, None)
            self._stop_recording_timers_if_idle()
            self.status_label.setText(status_recording_failed(event.device_serial))

    def _stop_recording_timers_if_idle(self):
        if self._recording_sessions:
            return
        self.recording_status_timer.stop()
        self.recording_reminder_timer.stop()

    def _refresh_recording_status(self):
        if not self._recording_sessions:
            return

        now = datetime.now()
        elapsed_seconds = max(
            int((now - session.started_at).total_seconds())
            for session in self._recording_sessions.values()
        )
        elapsed_text = self._format_elapsed_seconds(elapsed_seconds)

        if len(self._recording_sessions) == 1:
            device_serial = next(iter(self._recording_sessions))
            self.status_label.setText(status_recording_active(device_serial, elapsed_text))
            return

        self.status_label.setText(
            status_recording_active_multi(len(self._recording_sessions), elapsed_text)
        )

    def _check_long_recording_reminders(self):
        if not self._recording_sessions:
            return
        if self._is_foreground_fullscreen():
            return

        now = datetime.now()
        for device_serial, session in self._recording_sessions.items():
            elapsed_seconds = int((now - session.started_at).total_seconds())
            if elapsed_seconds < self.LONG_RECORDING_REMINDER_SECONDS or session.reminder_sent:
                continue
            self._show_tray_notification(
                tray_recording_reminder_title(),
                tray_recording_reminder_message(
                    device_serial,
                    self._format_elapsed_seconds(elapsed_seconds),
                ),
                icon=QSystemTrayIcon.MessageIcon.Warning,
                timeout=6000,
            )
            session.reminder_sent = True

    def _is_foreground_fullscreen(self) -> bool:
        return is_foreground_fullscreen(self)

    def _show_tray_notification(self, title: str, message: str, *, icon, timeout: int = 5000):
        show_tray_message(self, title, message, icon=icon, timeout=timeout)

    def _format_elapsed_seconds(self, seconds: int) -> str:
        hours, remainder = divmod(max(seconds, 0), 3600)
        minutes, secs = divmod(remainder, 60)
        return f"{hours:02d}:{minutes:02d}:{secs:02d}"

    # ================ 文件传输 UI ================
    @pyqtSlot()
    def refresh_file_list(self):
        self.file_page_controller.refresh_file_list()

    @pyqtSlot(list)
    def handle_files_dropped(self, local_paths: list):
        device = self.file_device_combo.currentText()
        if not device or not self.core_controller:
            return

        existing_names = set()
        for row in range(self.file_table.rowCount()):
            item = self.file_table.item(row, 1)
            if item:
                existing_names.add(item.text())

        submit_upload_requests(
            local_paths,
            existing_names=existing_names,
            popups=self.popups,
            log_to_console=self.log_to_console,
            request_push=lambda path, rename_to: self.core_controller.request_push_file(
                self._build_push_file_request(device, path, rename_to)
            ),
        )

    @pyqtSlot(str, str, int) 
    def handle_file_progress(self, status: str, msg: str, percent: int):
        self.status_label.setText(msg)
        if status == "start":
            self.progress_bar.setVisible(True)
            self.progress_bar.setRange(0, 100)
            self.progress_bar.setValue(0)
        elif status == "progress":
            self.progress_bar.setValue(percent)
        elif status in["done", "error"]:
            self.progress_bar.setValue(100)
            QTimer.singleShot(1500, lambda: self.progress_bar.setVisible(False))
            # 若传输成功，静默刷新当前列表以展现最新文件
            if status == "done":
                QTimer.singleShot(500, self.refresh_file_list)
    
    @pyqtSlot()
    def go_up_dir(self):
        self.file_page_controller.go_up_dir()

    # ================ 文件表格 UI 方法 ================
    @pyqtSlot(str, list, bool)
    def update_file_table(self, path: str, file_list: list, success: bool):
        if success:
            self.current_remote_path = path # 确保路径同步
            self._populate_file_table(file_list)
            self.log_to_console(log_loaded_items(len(file_list), path), "success")
        else:
            self.file_table.setRowCount(0)
            self.file_status_label.setText(file_status_read_failed())
    
    @pyqtSlot(str, str, bool)
    def handle_symlink_resolved(self, device_serial: str, name: str, is_dir: bool):
        if device_serial != self.file_device_combo.currentText():
            return
        update_symlink_in_table(self.file_table, name, is_dir)
        self.log_to_console(log_symlink_resolved(name, is_dir), "output")

    def _populate_file_table(self, file_list: list):
        populate_file_table(self.file_table, self.file_status_label, file_list)
    
    def on_file_table_double_clicked(self, item: QTableWidgetItem):
        self.file_page_controller.handle_table_double_click(item)
    
    def show_file_table_menu(self, pos):
        self.file_page_controller.show_file_table_menu(pos)
    
    def download_file_item(self, fi: FileInfo):
        self.file_page_controller.download_file_item(fi)

    @pyqtSlot()
    def restart_adb_service(self):
        if self.core_controller:
            submit_adb_service_action(
                before_submit=lambda: self._cooldown_buttons([self.restart_adb_btn], 1200),
                set_status=self.status_label.setText,
                submit=self.core_controller.request_restart_adb,
                restart=True,
            )
            
    @pyqtSlot()
    def kill_adb_service(self):
        if self.core_controller:
            submit_adb_service_action(
                before_submit=lambda: self._cooldown_buttons([self.kill_adb_btn], 1200),
                set_status=self.status_label.setText,
                submit=self.core_controller.request_force_kill_adb,
                restart=False,
            )
            
    @pyqtSlot(str)
    def handle_player_exit(self, device_serial: str):
        if self.popups.confirm_restart_audio_route(device_serial):
            if self.core_controller: self.core_controller.request_start_audio_route(device_serial)
            
    def execute_custom_command(self):
        if self.core_controller is None:
            return

        submit_console_command(
            self.cmd_input.toPlainText(),
            before_submit=lambda: self._cooldown_buttons([self.send_cmd_btn], 600),
            submit=lambda command: self.core_controller.request_execute_console_target(
                self._build_console_command_request(command)
            ),
            after_submit=self.cmd_input.clear,
        )

    def log_to_console(self, message: str, msg_type: str="info"):
        normalized_message = (message or "").strip()
        if not normalized_message:
            return

        current_time = datetime.now()
        signature = (msg_type, normalized_message)
        if (
            self._last_log_signature == signature
            and self._last_log_time is not None
            and (current_time - self._last_log_time).total_seconds() < 1.5
        ):
            return

        self._last_log_signature = signature
        self._last_log_time = current_time

        html_message = render_console_html(normalized_message, msg_type, current_time)
        self.console_output.moveCursor(QTextCursor.MoveOperation.End)
        self.console_output.insertHtml(html_message)
        self.console_output.moveCursor(QTextCursor.MoveOperation.End)
        
    @pyqtSlot(str)
    def back_to_default(self, setting: str):
        if setting == "video_bit": self.video_bitrate.setValue(8000)
        if setting == "audio_bit": self.audio_bitrate.setValue(192)

    @pyqtSlot(str, bool)
    def handle_operation_complete(self, operation: str, success: bool):
        finalize_operation_ui(
            operation,
            success,
            hide_progress=lambda: self.progress_bar.setVisible(False),
            set_status=self.status_label.setText,
            show_install_result=self.popups.show_install_result,
        )

    def load_json_settings(self) -> dict[str, Any]:
        settings = self.settings_store.load()
        self._pending_settings_load_warning = self.settings_store.last_load_warning
        return settings
        
    def save_settings(self):
        settings = collect_ui_settings(self, self.settings)
        try:
            self.settings_store.save(settings)
            self.settings.update(settings)
        except Exception as e:
            self.log_to_console(log_settings_save_failed(str(e)), "error")
            
    def load_settings(self):
        apply_ui_settings(self, self.settings)
    
    def closeEvent(self, event):
        if not getattr(self, "force_quit", False):
            res = self.popups.confirm_exit_action()
            
            if res == ExitAction.HIDE_TO_TRAY:
                self.close_only_action()
                event.ignore()
                return
            elif res == ExitAction.EXIT:
                pass
            else:
                event.ignore()
                return

        self.save_settings()
        if hasattr(self, 'usb_monitor') and self.usb_monitor:
            self.usb_monitor.stop_monitoring()
        if self.core_controller:
            self.log_to_console(log_cleanup_processes(), "warning")
            self.core_controller.request_shutdown()
        if hasattr(self, 'scan_timer') and self.scan_timer.isActive():
            self.scan_timer.stop()
            
        if hasattr(self, 'tray_icon'):
            self.tray_icon.hide()
            
        event.accept()

if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    
    window = SndcpyGUI()
    window.show()
    sys.exit(app.exec())
