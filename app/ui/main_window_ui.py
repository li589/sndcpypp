import os

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor, QIcon, QPalette
from PyQt6.QtWidgets import QProgressBar, QSplitter, QTabWidget, QVBoxLayout, QWidget

from app.ui.message_templates import window_title_text
from app.ui.pages.console_page import ConsolePage
from app.ui.pages.device_page import DeviceControlPage
from app.ui.pages.file_page import FileTransferPage
from app.ui.pages.recording_page import RecordingPage
from app.ui.widgets import AutoExpandTextEdit, DragDropTableWidget, RefreshDevicesButton


def configure_main_window_shell(window) -> None:
    window.setWindowTitle(window_title_text())
    window.setWindowIcon(QIcon(_resolve_logo_path(window)))
    window.setMinimumSize(540, 720)


def build_main_window_ui(window) -> None:
    central_widget = QWidget()
    window.setCentralWidget(central_widget)
    main_layout = QVBoxLayout(central_widget)
    splitter = QSplitter(Qt.Orientation.Vertical)

    control_panel = QWidget()
    control_layout = QVBoxLayout(control_panel)
    tab_widget = QTabWidget()

    window.refresh_devices_btn = RefreshDevicesButton()
    window.refresh_devices_btn.set_refresh_mode(window.auto_refresh_value)
    window.refresh_devices_btn.clicked.connect(window.manual_refresh_devices)
    window.refresh_devices_btn.auto_refresh_value.connect(window.set_auto_refresh_value)
    window.device_page = DeviceControlPage(
        refresh_button=window.refresh_devices_btn,
        on_restart_adb=window.restart_adb_service,
        on_kill_adb=window.kill_adb_service,
        on_browse_adb=window.browse_file,
        on_browse_player=window.browse_file,
        on_browse_sndcpy_dir=window.browse_folder,
        on_open_adb_settings=lambda: window.open_cmd_settings("adb"),
        on_open_player_settings=lambda: window.open_cmd_settings("player"),
        on_open_scrcpy_settings=lambda: window.open_cmd_settings("scrcpy"),
        on_validate_paths=window.validate_paths,
        on_back_video_bitrate_default=lambda: window.back_to_default("video_bit"),
        on_back_audio_bitrate_default=lambda: window.back_to_default("audio_bit"),
        on_start_audio_only=window.start_audio_only,
        on_stop_audio_only=window.stop_audio_only,
        on_install_sndcpy=window.install_sndcpy,
        on_start_routing=window.start_routing,
        on_stop_routing=window.stop_routing,
        parent=window,
    )
    _bind_device_page(window)
    tab_widget.addTab(window.device_page, "设备控制")

    window.recording_page = RecordingPage(
        on_browse_dir=lambda: window.browse_folder(window.recording_page.record_dir_edit),
        on_start_recording=window.start_recording_ui,
        on_stop_recording=window.stop_recording_ui,
        parent=window,
    )
    _bind_recording_page(window)
    tab_widget.addTab(window.recording_page, "录制设置")

    window.file_page = FileTransferPage(
        initial_remote_path=window.current_remote_path,
        table_widget_factory=DragDropTableWidget,
        on_refresh=window.refresh_file_list,
        on_go_up=window.go_up_dir,
        on_table_double_clicked=window.on_file_table_double_clicked,
        on_show_context_menu=window.show_file_table_menu,
        on_files_dropped=window.handle_files_dropped,
        on_browse_download_dir=lambda: window.browse_folder(window.file_page.local_down_edit),
        parent=window,
    )
    _bind_file_page(window)
    tab_widget.addTab(window.file_page, "文件传输")

    window.console_page = ConsolePage(
        command_input_factory=AutoExpandTextEdit,
        on_show_console_menu=window.show_console_menu,
        on_execute_command=window.execute_custom_command,
        parent=window,
    )
    _bind_console_page(window)
    tab_widget.addTab(window.console_page, "调试控制台")

    control_layout.addWidget(tab_widget)
    splitter.addWidget(control_panel)

    window.progress_bar = QProgressBar()
    window.progress_bar.setVisible(False)
    window.progress_bar.setTextVisible(True)
    control_layout.addWidget(window.progress_bar)

    main_layout.addWidget(splitter)
    apply_dark_theme(window)


def apply_dark_theme(window) -> None:
    dark_palette = QPalette()
    dark_palette.setColor(QPalette.ColorRole.Window, QColor(45, 45, 48))
    dark_palette.setColor(QPalette.ColorRole.WindowText, Qt.GlobalColor.white)
    dark_palette.setColor(QPalette.ColorRole.Base, QColor(30, 30, 30))
    dark_palette.setColor(QPalette.ColorRole.AlternateBase, QColor(45, 45, 48))
    dark_palette.setColor(QPalette.ColorRole.ToolTipBase, Qt.GlobalColor.white)
    dark_palette.setColor(QPalette.ColorRole.ToolTipText, Qt.GlobalColor.white)
    dark_palette.setColor(QPalette.ColorRole.Text, Qt.GlobalColor.white)
    dark_palette.setColor(QPalette.ColorRole.Button, QColor(45, 45, 48))
    dark_palette.setColor(QPalette.ColorRole.ButtonText, Qt.GlobalColor.white)
    dark_palette.setColor(QPalette.ColorRole.Highlight, QColor(62, 170, 127))
    dark_palette.setColor(QPalette.ColorRole.HighlightedText, Qt.GlobalColor.black)
    window.setPalette(dark_palette)

    window.setStyleSheet(
        """
        QMainWindow { background-color: #2D2D30; color: #FFFFFF; }
        QGroupBox { border: 1px solid #3E3E42; border-radius: 5px; margin-top: 15px; padding-top: 1px; font-weight: bold; color: #3EAA7F; }
        QGroupBox::title { subcontrol-origin: margin; subcontrol-position: top center; padding: 0 10px; background-color: transparent; }
        QPushButton { background-color: #3A3A3D; color: white; border-radius: 4px; padding: 6px 14px; min-width: 60px; border: 1px solid #3A3A3D; }
        QPushButton:hover { background-color: #3EAA7F; border: 1px solid #3EAA7F; }
        QPushButton:pressed { background-color: #2E8B68; }
        QLineEdit, QComboBox, QSpinBox, QListWidget { background-color: #252526; color: #CCCCCC; border: 1px solid #3A3A3D; border-radius: 3px; padding: 5px; }
        QTabWidget::pane { border: 1px solid #3A3A3D; background: #252526; }
        QTabBar::tab { background: #2D2D30; color: #CCCCCC; padding: 8px 15px; border-top-left-radius: 4px; border-top-right-radius: 4px; border: 1px solid #3A3A3D; margin-right: 2px; }
        QTabBar::tab:selected { background: #252526; color: #3EAA7F; border-bottom-color: #252526; }
        QProgressBar { border: 1px solid #3A3A3D; border-radius: 3px; text-align: center; background-color: #252526; color: white; }
        QProgressBar::chunk { background-color: #3EAA7F; width: 1px; }
        """
    )


def _bind_device_page(window) -> None:
    page = window.device_page
    window.device_list = page.device_list
    window.restart_adb_btn = page.restart_adb_btn
    window.kill_adb_btn = page.kill_adb_btn
    window.adb_path_edit = page.adb_path_edit
    window.player_path_edit = page.player_path_edit
    window.sndcpy_dir_edit = page.sndcpy_dir_edit
    window.validate_btn = page.validate_btn
    window.video_check = page.video_check
    window.fps_check = page.fps_check
    window.stay_awake_check = page.stay_awake_check
    window.screen_off_check = page.screen_off_check
    window.video_bitrate = page.video_bitrate
    window.back_video_bitrate_default_btn = page.back_video_bitrate_default_btn
    window.max_size_combo = page.max_size_combo
    window.lock_ori_combo = page.lock_ori_combo
    window.audio_check = page.audio_check
    window.audio_bitrate = page.audio_bitrate
    window.back_bitrate_default_btn = page.back_bitrate_default_btn
    window.start_audio_btn = page.start_audio_btn
    window.pause_audio_btn = page.pause_audio_btn
    window.install_btn = page.install_btn
    window.start_btn = page.start_btn
    window.stop_btn = page.stop_btn


def _bind_recording_page(window) -> None:
    page = window.recording_page
    window.rec_device_combo = page.rec_device_combo
    window.record_dir_edit = page.record_dir_edit
    window.rec_filename_edit = page.rec_filename_edit
    window.rec_video_check = page.rec_video_check
    window.rec_audio_check = page.rec_audio_check
    window.rec_bg_check = page.rec_bg_check
    window.rec_ori_combo = page.rec_ori_combo
    window.rec_format_combo = page.rec_format_combo
    window.start_rec_btn = page.start_rec_btn
    window.stop_rec_btn = page.stop_rec_btn


def _bind_file_page(window) -> None:
    page = window.file_page
    window.file_device_combo = page.file_device_combo
    window.remote_path_edit = page.remote_path_edit
    window.file_status_label = page.file_status_label
    window.file_table = page.file_table
    window.local_down_edit = page.local_down_edit


def _bind_console_page(window) -> None:
    page = window.console_page
    window.console_output = page.console_output
    window.console_output.document().setMaximumBlockCount(1500)
    window.device_combo = page.device_combo
    window.cmd_input = page.cmd_input
    window.send_cmd_btn = page.send_cmd_btn


def _resolve_logo_path(window) -> str:
    base_dir = getattr(window, "app_base_dir", os.path.abspath("."))
    return os.path.join(base_dir, "logo", "ui_logo_1.png")
