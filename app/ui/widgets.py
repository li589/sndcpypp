from PyQt6.QtCore import QRect, Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QColor, QKeyEvent, QMouseEvent, QPaintEvent, QPainter
from PyQt6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QWidget,
)


class FileTableWidgetItem(QTableWidgetItem):
    """自定义表格项，支持按类型和名称正确排序"""

    def __init__(self, text: str, sort_key: tuple):
        super().__init__(text)
        self._sort_key = sort_key

    def __lt__(self, other):
        if isinstance(other, FileTableWidgetItem):
            return self._sort_key < other._sort_key
        return super().__lt__(other)


class AutoExpandTextEdit(QTextEdit):
    returnPressed = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.textChanged.connect(self.adjust_height)
        self.setAcceptRichText(False)
        self.min_height = 32
        self.max_height = 120
        self.setFixedHeight(self.min_height)
        self.setStyleSheet(
            "background-color: #252526; color: #CCCCCC; border: 1px solid #3A3A3D; "
            "border-radius: 3px; padding: 4px;"
        )

    def keyPressEvent(self, event: QKeyEvent | None):
        if event and event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            if event.modifiers() & Qt.KeyboardModifier.ShiftModifier:
                super().keyPressEvent(event)
            else:
                self.returnPressed.emit()
        elif event:
            super().keyPressEvent(event)

    def adjust_height(self):
        doc_height = int(self.document().size().height())
        margins = self.contentsMargins()
        new_height = doc_height + margins.top() + margins.bottom() + 4
        new_height = max(self.min_height, min(new_height, self.max_height))
        self.setFixedHeight(new_height)
        if doc_height > self.max_height - 10:
            self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        else:
            self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)


class DragDropTableWidget(QTableWidget):
    """支持拖放文件的表格控件"""

    files_dropped = pyqtSignal(list)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAcceptDrops(True)

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
        else:
            super().dragEnterEvent(event)

    def dragMoveEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
        else:
            super().dragMoveEvent(event)

    def dropEvent(self, event):
        urls = event.mimeData().urls()
        paths = [u.toLocalFile() for u in urls if u.isLocalFile()]
        if paths:
            self.files_dropped.emit(paths)


class SwitchControl(QWidget):
    toggled = pyqtSignal(bool)

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.checked = False
        self.radius = 16
        self.margin = 2
        self.thumb_pos = self.margin
        self.setMinimumSize(58, 18)
        self.text_list = ["", ""]
        self.timer = QTimer()
        self.timer.timeout.connect(self.update_position)

    def paintEvent(self, event: QPaintEvent | None):
        del event
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(Qt.PenStyle.NoPen)
        bg_color = QColor(62, 170, 127) if self.checked else QColor(100, 100, 100)
        painter.setBrush(bg_color)
        painter.drawRoundedRect(0, 0, self.width(), self.height(), self.height() // 2, self.height() // 2)

        painter.setBrush(QColor(255, 255, 255))
        painter.drawEllipse(self.thumb_pos, self.margin, self.height() - 2 * self.margin, self.height() - 2 * self.margin)

        painter.setPen(Qt.GlobalColor.white)
        font = painter.font()
        font.setPixelSize(11)
        painter.setFont(font)
        text = self.text_list[1] if self.checked else self.text_list[0]
        if self.checked:
            painter.drawText(
                QRect(0, 0, self.width() - self.height(), self.height()),
                Qt.AlignmentFlag.AlignCenter,
                text,
            )
        else:
            painter.drawText(
                QRect(self.height(), 0, self.width() - self.height(), self.height()),
                Qt.AlignmentFlag.AlignCenter,
                text,
            )

    def mousePressEvent(self, event: QMouseEvent | None):
        del event
        self.checked = not self.checked
        self.timer.start(5)
        self.toggled.emit(self.checked)

    def update_position(self):
        target_x = self.width() - self.height() + self.margin if self.checked else self.margin
        step = 2
        if abs(self.thumb_pos - target_x) < step:
            self.thumb_pos = target_x
            self.timer.stop()
        else:
            self.thumb_pos += step if self.checked else -step
        self.update()

    def set_switch_text(self, text_list: list[str], reverse: bool = False):
        self.text_list = [text_list[1], text_list[0]] if reverse else [text_list[0], text_list[1]]

    def setChecked(self, checked: bool):
        if self.checked == checked:
            return
        self.checked = checked
        self.timer.start(5)
        self.toggled.emit(self.checked)


class RefreshDevicesButton(QPushButton):
    auto_refresh_value = pyqtSignal(int)

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setStyleSheet("QPushButton { padding: 4px 8px; }")
        layout = QHBoxLayout(self)
        layout.setContentsMargins(5, 2, 5, 2)
        self.switch = SwitchControl()
        self.switch.set_switch_text(["手动", "自动"])
        label = QLabel("轮询刷新")
        label.setAlignment(Qt.AlignmentFlag.AlignVCenter)
        layout.addWidget(label)
        layout.addWidget(self.switch, alignment=Qt.AlignmentFlag.AlignVCenter)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.setSpacing(8)
        self.switch.toggled.connect(self.handle_refresh_mode)

    def handle_refresh_mode(self, checked: bool):
        self.auto_refresh_value.emit(1 if checked else 0)

    def set_refresh_mode(self, checked: bool | int):
        self.switch.setChecked(bool(checked))
