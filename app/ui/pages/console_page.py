from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QComboBox,
    QGroupBox,
    QHBoxLayout,
    QPushButton,
    QSplitter,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

CONSOLE_TARGET_NO_DEVICE = "[ADB无设备]"
CONSOLE_TARGET_SCRCPY = "[Scrcpy命令]"


class ConsolePage(QWidget):
    def __init__(self, command_input_factory, on_show_console_menu, on_execute_command, parent=None):
        super().__init__(parent)

        layout = QVBoxLayout(self)
        console_group = QGroupBox("日志记录")
        console_main_layout = QVBoxLayout(console_group)
        console_main_layout.setContentsMargins(10, 15, 10, 10)

        console_splitter = QSplitter(Qt.Orientation.Vertical)

        self.console_output = QTextEdit()
        self.console_output.setReadOnly(True)
        self.console_output.setStyleSheet(
            "QTextEdit { background-color: #1E1E1E; color: #CCCCCC; font-family: Consolas, monospace; font-size: 10pt; }"
        )
        self.console_output.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.console_output.customContextMenuRequested.connect(on_show_console_menu)
        console_splitter.addWidget(self.console_output)

        bottom_cmd_widget = QWidget()
        bottom_cmd_layout = QHBoxLayout(bottom_cmd_widget)
        bottom_cmd_layout.setContentsMargins(0, 0, 0, 0)

        self.device_combo = QComboBox()
        self.device_combo.addItem(CONSOLE_TARGET_NO_DEVICE)
        self.device_combo.addItem(CONSOLE_TARGET_SCRCPY)
        # 长设备名处理：宽度基于最小字符数，闭合时省略显示，下拉列表和 tooltip 可看完整名称
        self.device_combo.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
        self.device_combo.setMinimumContentsLength(12)
        self.device_combo.currentTextChanged.connect(lambda text: self.device_combo.setToolTip(text))
        self.device_combo.setToolTip(self.device_combo.currentText())
        bottom_cmd_layout.addWidget(self.device_combo, 1)

        self.cmd_input = command_input_factory()
        self.cmd_input.setPlaceholderText("输入自定义命令...\n[Shift+Enter]换行 / [Enter]执行")
        self.cmd_input.returnPressed.connect(on_execute_command)
        bottom_cmd_layout.addWidget(self.cmd_input, 4)

        self.send_cmd_btn = QPushButton("执行")
        self.send_cmd_btn.clicked.connect(on_execute_command)
        bottom_cmd_layout.addWidget(self.send_cmd_btn, 1, alignment=Qt.AlignmentFlag.AlignCenter)

        console_splitter.addWidget(bottom_cmd_widget)
        console_splitter.setStretchFactor(0, 4)
        console_splitter.setStretchFactor(1, 1)
        console_main_layout.addWidget(console_splitter)
        layout.addWidget(console_group)
