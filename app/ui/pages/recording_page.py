import os

from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)


class RecordingPage(QWidget):
    def __init__(self, on_browse_dir, on_start_recording, on_stop_recording, parent=None):
        super().__init__(parent)

        layout = QVBoxLayout(self)
        rec_opt_group = QGroupBox("录制选项")
        rec_opt_layout = QVBoxLayout(rec_opt_group)

        rec_dev_lyt = QHBoxLayout()
        rec_dev_lbl = QLabel("选择设备:")
        rec_dev_lbl.setFixedWidth(60)
        rec_dev_lyt.addWidget(rec_dev_lbl)
        self.rec_device_combo = QComboBox()
        rec_dev_lyt.addWidget(self.rec_device_combo, 1)
        rec_opt_layout.addLayout(rec_dev_lyt)

        rec_path_lyt = QHBoxLayout()
        rec_path_lbl = QLabel("保存目录:")
        rec_path_lbl.setFixedWidth(60)
        rec_path_lyt.addWidget(rec_path_lbl)
        self.record_dir_edit = QLineEdit(os.path.abspath("."))
        rec_path_lyt.addWidget(self.record_dir_edit, 4)
        rec_browse = QPushButton("浏览...")
        rec_browse.clicked.connect(on_browse_dir)
        rec_path_lyt.addWidget(rec_browse, 1)
        rec_opt_layout.addLayout(rec_path_lyt)

        rec_file_lyt = QHBoxLayout()
        rec_file_lbl = QLabel("自定义名:")
        rec_file_lbl.setFixedWidth(60)
        rec_file_lyt.addWidget(rec_file_lbl)
        self.rec_filename_edit = QLineEdit()
        self.rec_filename_edit.setPlaceholderText("留空则自动生成 (无需加后缀)")
        rec_file_lyt.addWidget(self.rec_filename_edit, 1)
        rec_opt_layout.addLayout(rec_file_lyt)

        rec_mode_lyt = QHBoxLayout()
        self.rec_video_check = QCheckBox("录制视频")
        self.rec_video_check.setChecked(True)
        self.rec_audio_check = QCheckBox("录制音频")
        self.rec_audio_check.setChecked(True)
        self.rec_bg_check = QCheckBox("录制始终后台进行(不会新开窗口)")
        self.rec_bg_check.setChecked(True)
        self.rec_bg_check.setEnabled(False)
        self.rec_bg_check.setToolTip("录制会始终复用后台模式；即使已打开 Scrcpy 路由窗口，也不会再为录制弹出新窗口。")
        rec_mode_lyt.addWidget(self.rec_video_check)
        rec_mode_lyt.addWidget(self.rec_audio_check)
        rec_mode_lyt.addWidget(self.rec_bg_check)
        rec_mode_lyt.addStretch()
        rec_opt_layout.addLayout(rec_mode_lyt)

        rec_fmt_lyt = QHBoxLayout()
        rec_fmt_lyt.addWidget(QLabel("录制方向:"))
        self.rec_ori_combo = QComboBox()
        self.rec_ori_combo.addItems(["不锁定", "0°", "90°", "180°", "270°"])
        rec_fmt_lyt.addWidget(self.rec_ori_combo)
        rec_fmt_lyt.addSpacing(20)
        rec_fmt_lyt.addWidget(QLabel("保存格式:"))
        self.rec_format_combo = QComboBox()
        self.rec_format_combo.addItems([".mp4", ".mkv"])
        rec_fmt_lyt.addWidget(self.rec_format_combo)
        rec_fmt_lyt.addStretch()
        rec_opt_layout.addLayout(rec_fmt_lyt)

        rec_act_lyt = QHBoxLayout()
        self.start_rec_btn = QPushButton("⚫ 开始录制")
        self.start_rec_btn.setStyleSheet("background-color: #E74C3C; color: white;")
        self.start_rec_btn.clicked.connect(on_start_recording)
        self.stop_rec_btn = QPushButton("⏹ 停止录制")
        self.stop_rec_btn.clicked.connect(on_stop_recording)
        rec_act_lyt.addWidget(self.start_rec_btn)
        rec_act_lyt.addWidget(self.stop_rec_btn)
        rec_opt_layout.addLayout(rec_act_lyt)

        layout.addWidget(rec_opt_group)
        layout.addStretch()
