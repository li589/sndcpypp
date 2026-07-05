"""Sndcpy++ 主窗口。

本模块承载旧单体 `main.py` 中的 `SndcpyGUI` 主窗口类，作为渐进式重构
的过渡载体。后续会继续向 `pages/*.py`、`widgets/*.py`、`dialogs/*.py`
拆分，直至本模块仅保留窗口骨架与生命周期协调。
"""

import os
from typing import Any

from PyQt6.QtCore import Qt, pyqtSignal, QTimer, pyqtSlot
from PyQt6.QtWidgets import (
    QMainWindow, QLabel, QLineEdit, QPushButton,
    QTableWidgetItem,
)

from app.domain.models.operation_requests import RecordingStateEvent
from app.infrastructure.adb.path_resolver import ADBPathResolver
from app.infrastructure.config.settings_store import JsonSettingsStore, get_default_settings_path
from app.ui.console_actions import submit_console_command
from app.ui.console_logger_coordinator import ConsoleLoggerCoordinator
from app.ui.device_page_controller import DevicePageController
from app.ui.device_runtime_coordinator import apply_validation_result_ui
from app.ui.device_service_coordinator import (
    finalize_operation_ui,
    submit_install_sndcpy,
    submit_kill_adb,
    submit_restart_adb,
)
from app.ui.device_actions import (
    submit_device_start_action,
    submit_scoped_stop_action,
)
from app.ui.file_actions import submit_upload_requests
from app.ui.file_page_controller import FilePageController
from app.ui.file_transfer_coordinator import (
    collect_existing_names,
    handle_file_progress as coordinate_file_progress,
    handle_symlink_resolved as coordinate_symlink_resolved,
    should_refresh_file_view_after_transfer,
    update_file_table as coordinate_update_file_table,
)
from app.ui.interaction_helpers import (
    cooldown_buttons,
)
from app.ui.main_window_shell import (
    force_exit,
    handle_window_context_menu,
    hide_to_tray,
    init_tray_icon,
    minimize_all_windows,
    show_main_window,
    toggle_top_window,
    tray_icon_activated,
)
from app.ui.menu_coordinator import show_console_context_menu
from app.ui.main_window_ui import build_main_window_ui, configure_main_window_shell
from app.ui.request_builders import (
    build_browse_files_request,
    build_console_command_request,
    build_pull_file_request,
    build_push_file_request,
    build_recording_request,
    build_routing_request,
)
from app.ui.message_templates import (
    log_auto_validation_starting_adb,
    log_extra_params_updated,
    log_settings_load_warning,
    log_usb_monitor_init_failed,
    status_audio_route_submitted,
    status_recording_preparing,
    status_routing_submitted,
    status_usb_refresh_pending,
)
from app.ui.popup_manager import PopupManager
from app.ui.recording_actions import prepare_recording_start
from app.ui.recording_session_coordinator import RecordingSessionCoordinator
from app.ui.settings_coordinator import (
    apply_cmd_extra_settings,
    apply_settings_to_ui,
    load_settings_from_store,
    save_settings as persist_settings,
)
from app.ui.startup_coordinator import run_startup_routine
from app.ui.teardown_coordinator import handle_close_event
from app.ui.core_lifecycle_coordinator import (
    connect_core_signals,
    disconnect_core_signals,
    recreate_core_controller,
    resolve_and_prepare_paths,
    sync_core_runtime as coordinate_sync_core_runtime,
)
from core import CoreController, FileInfo


def _report_debug_event(hypothesis_id: str, location: str, msg: str, data: dict[str, Any] | None = None) -> None:
    del hypothesis_id, location, msg, data


class SndcpyGUI(QMainWindow):
    usb_event_signal = pyqtSignal()

    def __init__(self):
        super().__init__()
        self.setAttribute(Qt.WidgetAttribute.WA_QuitOnClose)
        # app_base_dir 始终指向项目根目录（app/ui/main_window.py 上溯两级）
        self.app_base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        configure_main_window_shell(self)

        self.core_controller = None
        self.settings_file = get_default_settings_path()
        self.settings_store = JsonSettingsStore(self.settings_file)
        self._pending_settings_load_warning: str | None = None
        self.settings = self.load_json_settings()
        self.adb_path_resolver = ADBPathResolver(self.app_base_dir)
        self.popups = PopupManager(self, audit_callback=self.log_to_console)
        self.auto_refresh_value = 0

        self._is_first_startup = True
        self.is_adb_valid = False
        self.are_paths_ready = False
        self.current_remote_path = "/sdcard/"
        self.force_quit = False
        self.is_top = False
        self._last_adb_resolution_signature: tuple[str, str, bool, str] | None = None
        self._recording_coordinator: RecordingSessionCoordinator | None = None

        build_main_window_ui(self)
        self._console_logger = ConsoleLoggerCoordinator(console_output=self.console_output)
        if self._pending_settings_load_warning:
            self.log_to_console(log_settings_load_warning(self._pending_settings_load_warning), "warning")
        self.file_page_controller = self._create_file_page_controller()
        self.load_settings()
        self.init_tray_icon()

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
        self._recording_coordinator = RecordingSessionCoordinator(
            host_widget=self,
            set_status=self.status_label.setText,
            tray_widget=self,
        )
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
        usb_monitor = getattr(self, 'usb_monitor', None)
        ok = run_startup_routine(
            log_to_console=self.log_to_console,
            validate_paths=self.validate_paths,
            usb_monitor=usb_monitor,
        )
        if not ok and usb_monitor is not None:
            # 启动失败时清理引用，避免后续重复使用已损坏的实例
            self.usb_monitor = None

    def set_auto_refresh_value(self, value: int):
        self.auto_refresh_value = value
        if self.auto_refresh_value:
            self.scan_timer.start(3000)
        else:
            self.scan_timer.stop()

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
        if not self.core_controller:
            self.init_core_controller()
        self._sync_core_runtime()
        if self.core_controller:
            self.core_controller.request_validate_runtime()

    def init_core_controller(self):
        self.core_controller, self._last_adb_resolution_signature = recreate_core_controller(
            previous_controller=self.core_controller,
            slots=self._build_core_signal_slots(),
            resolve_paths=self.resolve_runtime_paths,
            log_to_console=self.log_to_console,
            last_adb_signature=self._last_adb_resolution_signature,
            settings=self.settings,
        )

    def resolve_runtime_paths(self):
        return resolve_and_prepare_paths(
            adb_path_text=self.adb_path_edit.text(),
            player_path_text=self.player_path_edit.text(),
            sndcpy_dir_text=self.sndcpy_dir_edit.text(),
            adb_path_resolver=self.adb_path_resolver,
            app_base_dir=self.app_base_dir,
            set_adb_tooltip=self.adb_path_edit.setToolTip,
        )

    def _sync_core_runtime(
        self,
        adb_resolution=None,
        player_path: str | None = None,
        sndcpy_dir: str | None = None,
        log_resolution: bool = True,
    ):
        self._last_adb_resolution_signature = coordinate_sync_core_runtime(
            core_controller=self.core_controller,
            settings=self.settings,
            adb_resolution=adb_resolution,
            player_path=player_path,
            sndcpy_dir=sndcpy_dir,
            log_resolution=log_resolution,
            last_adb_signature=self._last_adb_resolution_signature,
            resolve_paths=self.resolve_runtime_paths,
            log_to_console=self.log_to_console,
        )

    def _build_core_signal_slots(self) -> dict:
        return {
            "update_device_list": self.update_device_list,
            "log_to_console": self.log_to_console,
            "handle_operation_complete": self.handle_operation_complete,
            "handle_validation_result": self.handle_validation_result,
            "handle_player_exit": self.handle_player_exit,
            "handle_recording_state_change": self.handle_recording_state_change,
            "update_file_table": self.update_file_table,
            "handle_symlink_resolved": self.handle_symlink_resolved,
            "handle_file_progress": self.handle_file_progress,
        }

    def _connect_core_signals(self, controller: CoreController | None = None):
        controller = controller or self.core_controller
        if not controller:
            return
        connect_core_signals(controller, self._build_core_signal_slots())

    def _disconnect_core_signals(self, controller: CoreController | None):
        disconnect_core_signals(controller, self._build_core_signal_slots())

    def _cooldown_buttons(self, buttons: list[QPushButton], ms: int = 900, restore_callback=None):
        cooldown_buttons(buttons, ms, restore_callback)

    def _restore_validation_actions(self, paths_ready: bool | None = None):
        ready_state = self.are_paths_ready if paths_ready is None else paths_ready
        self.install_btn.setEnabled(ready_state)
        self.start_btn.setEnabled(ready_state)

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
                build_browse_files_request(device, remote_path)
            ) if self.core_controller else None,
            request_pull=lambda device, remote_file, local_dir, rename_to: self.core_controller.request_pull_file(
                build_pull_file_request(
                    device_serial=device,
                    remote_path=remote_file,
                    local_dir=local_dir,
                    rename_to=rename_to,
                )
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
        key = f"{cmd_type}_extra"
        updated_value = self.popups.open_param_settings(cmd_type, str(self.settings.get(key, "")))
        title = apply_cmd_extra_settings(
            cmd_type=cmd_type,
            updated_value=updated_value,
            settings=self.settings,
        )
        if title is not None:
            self.save_settings()
            if self.core_controller:
                self._sync_core_runtime()
            self.log_to_console(log_extra_params_updated(title), "info")

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
        # #region debug-point A:install-entry
        _report_debug_event(
            "A",
            "main_window.install_sndcpy",
            "[DEBUG] install action invoked",
            {
                "device": device or "",
                "has_core_controller": self.core_controller is not None,
                "selected_items": len(self.device_list.selectedItems()) if hasattr(self, "device_list") else -1,
            },
        )
        # #endregion
        submit_install_sndcpy(
            device_serial=device,
            core_controller=self.core_controller,
            cooldown=lambda: self._cooldown_buttons(
                [self.install_btn], 1500, self._restore_validation_actions
            ),
            set_status=self.status_label.setText,
            show_busy_progress=self._show_busy_progress,
        )

    @pyqtSlot()
    def start_routing(self):
        device = self.get_selected_device()
        # #region debug-point A:routing-entry
        _report_debug_event(
            "A",
            "main_window.start_routing",
            "[DEBUG] routing action invoked",
            {
                "device": device or "",
                "has_core_controller": self.core_controller is not None,
                "selected_items": len(self.device_list.selectedItems()) if hasattr(self, "device_list") else -1,
                "audio_enabled": self.audio_check.isChecked(),
                "video_enabled": self.video_check.isChecked(),
            },
        )
        # #endregion
        if device and self.core_controller:
            submit_device_start_action(
                device,
                before_submit=lambda: self._cooldown_buttons(
                    [self.start_btn], 1200, self._restore_validation_actions
                ),
                submit=lambda serial: self.core_controller.request_start_routing_session(
                    build_routing_request(
                        device_serial=serial,
                        enable_audio=self.audio_check.isChecked(),
                        enable_video=self.video_check.isChecked(),
                        video_bitrate=self.video_bitrate.value(),
                        max_size=self.max_size_combo.currentText(),
                        lock_ori_index=self.lock_ori_combo.currentIndex(),
                        show_fps=self.fps_check.isChecked(),
                        stay_awake=self.stay_awake_check.isChecked(),
                        turn_screen_off=self.screen_off_check.isChecked(),
                    )
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

        self.core_controller.request_start_recording(
            build_recording_request(
                device_serial=device,
                save_path=full_path,
                record_video=self.rec_video_check.isChecked(),
                record_audio=self.rec_audio_check.isChecked(),
                record_ori_index=self.rec_ori_combo.currentIndex(),
            )
        )
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
        if self._recording_coordinator:
            self._recording_coordinator.handle_state_change(event)

    # ================ 文件传输 UI ================
    @pyqtSlot()
    def refresh_file_list(self):
        self.file_page_controller.refresh_file_list()

    @pyqtSlot(list)
    def handle_files_dropped(self, local_paths: list):
        device = self.file_device_combo.currentText()
        if not device or not self.core_controller:
            return

        submit_upload_requests(
            local_paths,
            existing_names=collect_existing_names(self.file_table),
            popups=self.popups,
            log_to_console=self.log_to_console,
            request_push=lambda path, rename_to: self.core_controller.request_push_file(
                build_push_file_request(
                    device_serial=device,
                    local_path=path,
                    remote_dir=self.current_remote_path,
                    rename_to=rename_to,
                )
            ),
        )

    def _should_refresh_file_view_after_transfer(self, device_serial: str, transfer_kind: str, remote_path: str) -> bool:
        return should_refresh_file_view_after_transfer(
            device_serial=device_serial,
            transfer_kind=transfer_kind,
            remote_path=remote_path,
            current_device=self.file_device_combo.currentText(),
            current_path_text=self.remote_path_edit.text(),
        )

    @pyqtSlot(str, str, str, str, str, int)
    def handle_file_progress(self, status: str, device_serial: str, transfer_kind: str, remote_path: str, msg: str, percent: int):
        coordinate_file_progress(
            status=status,
            device_serial=device_serial,
            transfer_kind=transfer_kind,
            remote_path=remote_path,
            msg=msg,
            percent=percent,
            progress_bar=self.progress_bar,
            set_status=self.status_label.setText,
            should_refresh=self._should_refresh_file_view_after_transfer(device_serial, transfer_kind, remote_path),
            on_refresh=self.refresh_file_list,
        )

    @pyqtSlot()
    def go_up_dir(self):
        self.file_page_controller.go_up_dir()

    # ================ 文件表格 UI 方法 ================
    @pyqtSlot(str, list, bool)
    def update_file_table(self, path: str, file_list: list, success: bool):
        coordinate_update_file_table(
            path=path,
            file_list=file_list,
            success=success,
            file_table=self.file_table,
            file_status_label=self.file_status_label,
            set_current_remote_path=lambda p: setattr(self, "current_remote_path", p),
            log_to_console=self.log_to_console,
        )

    @pyqtSlot(str, str, bool)
    def handle_symlink_resolved(self, device_serial: str, name: str, is_dir: bool):
        coordinate_symlink_resolved(
            device_serial=device_serial,
            name=name,
            is_dir=is_dir,
            current_device=self.file_device_combo.currentText(),
            file_table=self.file_table,
            log_to_console=self.log_to_console,
        )

    def on_file_table_double_clicked(self, item: QTableWidgetItem):
        self.file_page_controller.handle_table_double_click(item)

    def show_file_table_menu(self, pos):
        self.file_page_controller.show_file_table_menu(pos)

    def download_file_item(self, fi: FileInfo):
        self.file_page_controller.download_file_item(fi)

    @pyqtSlot()
    def restart_adb_service(self):
        submit_restart_adb(
            core_controller=self.core_controller,
            cooldown=lambda: self._cooldown_buttons([self.restart_adb_btn], 1200),
            set_status=self.status_label.setText,
        )

    @pyqtSlot()
    def kill_adb_service(self):
        submit_kill_adb(
            core_controller=self.core_controller,
            cooldown=lambda: self._cooldown_buttons([self.kill_adb_btn], 1200),
            set_status=self.status_label.setText,
        )

    @pyqtSlot(str)
    def handle_player_exit(self, device_serial: str):
        if self.popups.confirm_restart_audio_route(device_serial):
            if self.core_controller:
                self.core_controller.request_start_audio_route(device_serial)

    def execute_custom_command(self):
        if self.core_controller is None:
            return

        submit_console_command(
            self.cmd_input.toPlainText(),
            before_submit=lambda: self._cooldown_buttons([self.send_cmd_btn], 600),
            submit=lambda command: self.core_controller.request_execute_console_target(
                build_console_command_request(command, self.device_combo.currentText())
            ),
            after_submit=self.cmd_input.clear,
        )

    def log_to_console(self, message: str, msg_type: str="info"):
        self._console_logger.emit(message, msg_type)

    @pyqtSlot(str)
    def back_to_default(self, setting: str):
        if setting == "video_bit":
            self.video_bitrate.setValue(8000)
        if setting == "audio_bit":
            self.audio_bitrate.setValue(192)

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
        settings, warning = load_settings_from_store(self.settings_store)
        self._pending_settings_load_warning = warning
        return settings

    def save_settings(self):
        persist_settings(
            settings_store=self.settings_store,
            window=self,
            settings=self.settings,
            log_to_console=self.log_to_console,
        )

    def load_settings(self):
        apply_settings_to_ui(self, self.settings)

    def closeEvent(self, event):
        handle_close_event(
            event=event,
            force_quit=getattr(self, "force_quit", False),
            confirm_exit=self.popups.confirm_exit_action,
            hide_to_tray=self.close_only_action,
            save_settings=self.save_settings,
            usb_monitor=getattr(self, 'usb_monitor', None),
            core_controller=self.core_controller,
            log_to_console=self.log_to_console,
            scan_timer=getattr(self, 'scan_timer', None),
            tray_icon=getattr(self, 'tray_icon', None),
        )
