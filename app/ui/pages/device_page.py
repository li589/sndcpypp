from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFrame,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)


class DeviceControlPage(QWidget):
    def __init__(
        self,
        refresh_button,
        on_restart_adb,
        on_kill_adb,
        on_browse_adb,
        on_browse_player,
        on_browse_sndcpy_dir,
        on_open_adb_settings,
        on_open_player_settings,
        on_open_scrcpy_settings,
        on_validate_paths,
        on_back_video_bitrate_default,
        on_back_audio_bitrate_default,
        on_start_audio_only,
        on_stop_audio_only,
        on_install_sndcpy,
        on_start_routing,
        on_stop_routing,
        parent=None,
    ):
        super().__init__(parent)

        layout = QVBoxLayout(self)

        device_group = QGroupBox("设备列表")
        device_group_layout = QVBoxLayout(device_group)
        device_group_layout.setContentsMargins(15, 15, 15, 15)
        self.device_list = QListWidget()
        self.device_list.setMinimumHeight(80)
        device_group_layout.addWidget(self.device_list)

        device_btn_layout = QHBoxLayout()
        self.refresh_devices_btn = refresh_button
        self.restart_adb_btn = QPushButton("重启ADB")
        self.restart_adb_btn.clicked.connect(on_restart_adb)
        self.kill_adb_btn = QPushButton("结束ADB")
        self.kill_adb_btn.clicked.connect(on_kill_adb)
        device_btn_layout.addWidget(self.refresh_devices_btn)
        device_btn_layout.addWidget(self.restart_adb_btn)
        device_btn_layout.addWidget(self.kill_adb_btn)
        device_group_layout.addLayout(device_btn_layout)
        layout.addWidget(device_group)

        path_group = QGroupBox("路径设置")
        path_layout = QVBoxLayout(path_group)
        path_layout.setContentsMargins(15, 10, 15, 10)

        def create_path_row(label_text, placeholder, on_browse, on_settings):
            row = QHBoxLayout()
            label = QLabel(label_text)
            label.setFixedWidth(70)
            row.addWidget(label)
            edit = QLineEdit()
            edit.setPlaceholderText(placeholder)
            row.addWidget(edit, 4)
            browse_btn = QPushButton("浏览...")
            browse_btn.clicked.connect(lambda: on_browse(edit))
            row.addWidget(browse_btn, 1)
            settings_btn = QPushButton("⚙")
            settings_btn.clicked.connect(on_settings)
            row.addWidget(settings_btn)
            return row, edit

        adb_row, self.adb_path_edit = create_path_row(
            "ADB路径:", "留空自动优先外部ADB，失败回退内置", on_browse_adb, on_open_adb_settings
        )
        player_row, self.player_path_edit = create_path_row(
            "播放器路径:", "默认优先VLC，自动探测 AudioRouter", on_browse_player, on_open_player_settings
        )
        sndcpy_row, self.sndcpy_dir_edit = create_path_row(
            "Sndcpy目录:", "Sndcpy文件夹路径", on_browse_sndcpy_dir, on_open_scrcpy_settings
        )
        path_layout.addLayout(adb_row)
        path_layout.addLayout(player_row)
        path_layout.addLayout(sndcpy_row)
        self.validate_btn = QPushButton("验证")
        self.validate_btn.clicked.connect(on_validate_paths)
        path_layout.addWidget(self.validate_btn)
        layout.addWidget(path_group)

        route_group = QGroupBox("路由控制")
        route_layout = QVBoxLayout(route_group)
        route_layout.setContentsMargins(15, 10, 15, 10)
        route_layout.setSpacing(10)

        compact_btn_style = (
            "QPushButton { background-color: #3A3A3D; color: #3EAA7F; font-size: 16px; "
            "font-weight: bold; border-radius: 2px; border: 1px solid #3A3A3D; padding: 0px; "
            "min-width: 24px; min-height: 24px; } "
            "QPushButton:hover { background-color: #3EAA7F; color: white; border: 1px solid #3EAA7F; } "
            "QPushButton:pressed { background-color: #2E8B68; }"
        )
        pause_btn_style = (
            "QPushButton { background-color: #3A3A3D; color: #FFFFFF; font-size: 13px; font-weight: bold; "
            "border-radius: 2px; border: 1px solid #3A3A3D; padding: 0px; min-width: 58px; min-height: 24px; } "
            "QPushButton:hover { background-color: #E74C3C; color: white; border: 1px solid #E74C3C; } "
            "QPushButton:pressed { background-color: #C0392B; }"
        )
        play_btn_style = pause_btn_style.replace("#E74C3C", "#3EAA7F").replace("#C0392B", "#2E8B68")

        self.video_check = QCheckBox("启用画面路由 (带触控)")
        self.video_check.setChecked(True)
        self.fps_check = QCheckBox("显示FPS")
        self.fps_check.setChecked(False)
        self.stay_awake_check = QCheckBox("保持唤醒")
        self.stay_awake_check.setChecked(True)
        self.screen_off_check = QCheckBox("自动息屏")
        self.screen_off_check.setChecked(True)

        row1 = QHBoxLayout()
        row1.addWidget(self.video_check)
        row1.addWidget(self.fps_check)
        row1.addWidget(self.stay_awake_check)
        row1.addWidget(self.screen_off_check)
        row1.addStretch()
        route_layout.addLayout(row1)

        self.video_bitrate = QSpinBox()
        self.video_bitrate.setRange(500, 20000)
        self.video_bitrate.setValue(8000)
        self.video_bitrate.setSuffix(" kbps")
        self.video_bitrate.setFixedWidth(90)
        self.back_video_bitrate_default_btn = QPushButton("↺")
        self.back_video_bitrate_default_btn.setStyleSheet(compact_btn_style)
        self.back_video_bitrate_default_btn.clicked.connect(on_back_video_bitrate_default)
        self.max_size_combo = QComboBox()
        self.max_size_combo.addItems(["原始", "1920", "1280", "1080", "720"])
        self.max_size_combo.setFixedWidth(70)
        self.lock_ori_combo = QComboBox()
        self.lock_ori_combo.addItems(["不锁定", "0°", "90°", "180°", "270°"])
        self.lock_ori_combo.setFixedWidth(70)

        row2 = QHBoxLayout()
        row2.addWidget(QLabel("比特率:"))
        row2.addWidget(self.video_bitrate)
        row2.addWidget(self.back_video_bitrate_default_btn)
        row2.addSpacing(15)
        row2.addWidget(QLabel("最大尺寸:"))
        row2.addWidget(self.max_size_combo)
        row2.addSpacing(15)
        row2.addWidget(QLabel("锁定方向:"))
        row2.addWidget(self.lock_ori_combo)
        row2.addStretch()
        route_layout.addLayout(row2)

        separator = QFrame()
        separator.setFrameShape(QFrame.Shape.HLine)
        separator.setFrameShadow(QFrame.Shadow.Sunken)
        route_layout.addWidget(separator)

        self.audio_check = QCheckBox("启用音频路由")
        self.audio_check.setChecked(True)
        row3 = QHBoxLayout()
        row3.addWidget(self.audio_check)
        row3.addStretch()
        route_layout.addLayout(row3)

        self.audio_bitrate = QSpinBox()
        self.audio_bitrate.setRange(48, 320)
        self.audio_bitrate.setValue(192)
        self.audio_bitrate.setSuffix(" kbps")
        self.audio_bitrate.setFixedWidth(90)
        self.audio_bitrate.setEnabled(False)
        self.audio_bitrate.setToolTip("当前 sndcpy + VLC 链路不支持在此调整音频比特率，该值不会生效。")
        self.back_bitrate_default_btn = QPushButton("↺")
        self.back_bitrate_default_btn.setStyleSheet(compact_btn_style)
        self.back_bitrate_default_btn.clicked.connect(on_back_audio_bitrate_default)
        self.start_audio_btn = QPushButton("▶ 启动")
        self.start_audio_btn.setStyleSheet(play_btn_style)
        self.start_audio_btn.clicked.connect(on_start_audio_only)
        self.pause_audio_btn = QPushButton("⏸ 暂停")
        self.pause_audio_btn.setStyleSheet(pause_btn_style)
        self.pause_audio_btn.clicked.connect(on_stop_audio_only)

        row4 = QHBoxLayout()
        bitrate_label = QLabel("音频比特(固定):")
        bitrate_label.setToolTip("当前 sndcpy + VLC 链路不支持在此调整音频比特率。")
        row4.addWidget(bitrate_label)
        row4.addWidget(self.audio_bitrate)
        row4.addWidget(self.back_bitrate_default_btn)
        row4.addSpacing(15)
        row4.addWidget(self.start_audio_btn)
        row4.addWidget(self.pause_audio_btn)
        row4.addStretch()
        route_layout.addLayout(row4)

        layout.addWidget(route_group)

        action_group = QGroupBox("操作")
        action_layout = QHBoxLayout(action_group)
        self.install_btn = QPushButton("安装SNDCPY")
        self.install_btn.clicked.connect(on_install_sndcpy)
        self.start_btn = QPushButton("一键启动路由")
        self.start_btn.clicked.connect(on_start_routing)
        self.start_btn.setStyleSheet("background-color: #3EAA7F; color: white;")
        self.stop_btn = QPushButton("停止选中设备")
        self.stop_btn.clicked.connect(on_stop_routing)
        self.stop_btn.setStyleSheet("background-color: #E74C3C; color: white;")
        action_layout.addWidget(self.install_btn)
        action_layout.addWidget(self.start_btn)
        action_layout.addWidget(self.stop_btn)
        layout.addWidget(action_group)
