from collections.abc import Sequence
from enum import IntEnum

from PyQt6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
)

from app.ui.message_templates import (
    DIALOG_BTN_CANCEL,
    DIALOG_BTN_OK,
    DIALOG_BTN_OVERWRITE,
    DIALOG_BTN_RENAME,
    DIALOG_BTN_SKIP,
    DIALOG_LABEL_QUICK_FILL,
    EXIT_DIALOG_BTN_EXIT,
    EXIT_DIALOG_BTN_TRAY,
    EXIT_DIALOG_MESSAGE,
    EXIT_DIALOG_TITLE,
    file_conflict_dialog_message,
    file_conflict_dialog_title,
    param_settings_dialog_label,
)

DIALOG_STYLESHEET = """
QDialog, QMessageBox, QFileDialog { background-color: #2D2D30; color: #FFFFFF; }
QLabel { color: #CCCCCC; font-size: 13px; }
QLineEdit { background-color: #252526; color: #CCCCCC; border: 1px solid #3A3A3D; padding: 5px; }
QPushButton { background-color: #3A3A3D; color: white; padding: 6px 15px; border-radius: 3px; border: 1px solid #555555; }
QPushButton:hover { background-color: #3EAA7F; border: 1px solid #3EAA7F; }
QPushButton:pressed { background-color: #2E8B68; }
QTreeView, QListView { background-color: #252526; color: #CCCCCC; border: 1px solid #3A3A3D; }
"""


class ExitAction(IntEnum):
    CANCEL = 0
    HIDE_TO_TRAY = 1
    EXIT = 2


class ExitConfirmDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle(EXIT_DIALOG_TITLE)
        self.setMinimumWidth(400)
        self.setStyleSheet(f"{DIALOG_STYLESHEET}\nQLabel {{ font-weight: bold; }}")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(20)

        layout.addWidget(QLabel(EXIT_DIALOG_MESSAGE))

        btn_layout = QHBoxLayout()
        self.btn_tray = QPushButton(EXIT_DIALOG_BTN_TRAY)
        self.btn_exit = QPushButton(EXIT_DIALOG_BTN_EXIT)
        self.btn_cancel = QPushButton(DIALOG_BTN_CANCEL)

        btn_layout.addWidget(self.btn_tray)
        btn_layout.addWidget(self.btn_exit)
        btn_layout.addWidget(self.btn_cancel)
        layout.addLayout(btn_layout)

        self.btn_tray.clicked.connect(lambda: self.done(ExitAction.HIDE_TO_TRAY))
        self.btn_exit.clicked.connect(lambda: self.done(ExitAction.EXIT))
        self.btn_cancel.clicked.connect(lambda: self.done(ExitAction.CANCEL))


class ParamSettingsDialog(QDialog):
    def __init__(
        self,
        parent=None,
        title: str = "",
        param_name: str = "",
        current_val: str = "",
        quick_fill_actions: Sequence[tuple[str, str]] | None = None,
    ):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setMinimumWidth(350)
        self.setStyleSheet(DIALOG_STYLESHEET)

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel(param_settings_dialog_label(param_name)))
        self.input_edit = QLineEdit()
        self.input_edit.setText(current_val)
        layout.addWidget(self.input_edit)

        if quick_fill_actions:
            quick_fill_layout = QHBoxLayout()
            quick_fill_layout.addWidget(QLabel(DIALOG_LABEL_QUICK_FILL))
            for label, value in quick_fill_actions:
                button = QPushButton(label)
                button.clicked.connect(lambda _checked=False, fill_value=value: self.input_edit.setText(fill_value))
                quick_fill_layout.addWidget(button)
            quick_fill_layout.addStretch()
            layout.addLayout(quick_fill_layout)

        btn_layout = QHBoxLayout()
        ok_btn = QPushButton(DIALOG_BTN_OK)
        ok_btn.clicked.connect(self.accept)
        cancel_btn = QPushButton(DIALOG_BTN_CANCEL)
        cancel_btn.clicked.connect(self.reject)

        btn_layout.addStretch()
        btn_layout.addWidget(ok_btn)
        btn_layout.addWidget(cancel_btn)
        layout.addLayout(btn_layout)

    def get_value(self) -> str:
        return self.input_edit.text().strip()


class FileConflictDialog(QDialog):
    """同名冲突处理弹窗"""

    def __init__(self, filename: str, is_upload: bool = False, parent=None):
        super().__init__(parent)
        self.setWindowTitle(file_conflict_dialog_title(is_upload))
        self.setMinimumWidth(400)
        self.setStyleSheet(DIALOG_STYLESHEET)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(20)

        layout.addWidget(QLabel(file_conflict_dialog_message(filename)))

        btn_layout = QHBoxLayout()
        self.btn_overwrite = QPushButton(DIALOG_BTN_OVERWRITE)
        self.btn_rename = QPushButton(DIALOG_BTN_RENAME)
        self.btn_skip = QPushButton(DIALOG_BTN_SKIP)

        self.btn_overwrite.setStyleSheet(
            "QPushButton { background-color: #E74C3C; border: 1px solid #C0392B; } "
            "QPushButton:hover { background-color: #C0392B; }"
        )

        btn_layout.addWidget(self.btn_overwrite)
        btn_layout.addWidget(self.btn_rename)
        btn_layout.addWidget(self.btn_skip)
        layout.addLayout(btn_layout)

        self.btn_overwrite.clicked.connect(lambda: self.done(1))
        self.btn_rename.clicked.connect(lambda: self.done(2))
        self.btn_skip.clicked.connect(lambda: self.done(0))
