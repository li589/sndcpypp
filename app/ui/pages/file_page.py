import os

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)


class FileTransferPage(QWidget):
    def __init__(
        self,
        initial_remote_path: str,
        table_widget_factory,
        on_refresh,
        on_go_up,
        on_table_double_clicked,
        on_show_context_menu,
        on_files_dropped,
        on_browse_download_dir,
        parent=None,
    ):
        super().__init__(parent)

        self.file_device_combo = QComboBox()
        self.remote_path_edit = QLineEdit(initial_remote_path)
        self.remote_path_edit.returnPressed.connect(on_refresh)

        self.file_status_label = QLabel("")
        self.file_status_label.setStyleSheet("color: #888888; font-size: 11px; padding: 2px;")

        self.file_table = table_widget_factory()
        self.file_table.setColumnCount(7)
        self.file_table.setHorizontalHeaderLabels(["类型", "名称", "大小", "权限", "所有者", "修改日期", "链接目标"])
        self.file_table.setStyleSheet(
            """
            QTableWidget {
                background-color: #1E1E1E;
                color: #CCCCCC;
                border: 1px solid #3A3A3D;
                border-radius: 3px;
                gridline-color: #2D2D30;
                font-family: Consolas, monospace;
                font-size: 11px;
            }
            QTableWidget::item { padding: 3px 6px; }
            QTableWidget::item:selected { background-color: #3EAA7F; color: white; }
            QHeaderView::section {
                background-color: #2D2D30;
                color: #3EAA7F;
                border: 1px solid #3A3A3D;
                padding: 4px 8px;
                font-weight: bold;
            }
            """
        )
        self.file_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.file_table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.file_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.file_table.verticalHeader().setVisible(False)
        self.file_table.setSortingEnabled(False)

        header = self.file_table.horizontalHeader()
        header.setStretchLastSection(True)
        header.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)

        self.file_table.setColumnWidth(0, 85)
        self.file_table.setColumnWidth(1, 220)
        self.file_table.setColumnWidth(2, 70)
        self.file_table.setColumnWidth(3, 85)
        self.file_table.setColumnWidth(4, 75)
        self.file_table.setColumnWidth(5, 135)

        self.file_table.itemDoubleClicked.connect(on_table_double_clicked)
        self.file_table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.file_table.customContextMenuRequested.connect(on_show_context_menu)
        self.file_table.files_dropped.connect(on_files_dropped)

        self.local_down_edit = QLineEdit(os.path.abspath("."))

        layout = QVBoxLayout(self)

        file_dev_lyt = QHBoxLayout()
        file_dev_lyt.addWidget(QLabel("选择设备:"))
        file_dev_lyt.addWidget(self.file_device_combo, 1)
        layout.addLayout(file_dev_lyt)

        fm_path_lyt = QHBoxLayout()
        fm_path_lyt.addWidget(QLabel("当前路径:"))
        fm_path_lyt.addWidget(self.remote_path_edit, 4)
        fm_up_btn = QPushButton("返回上层")
        fm_up_btn.clicked.connect(on_go_up)
        fm_ref_btn = QPushButton("刷新")
        fm_ref_btn.clicked.connect(on_refresh)
        fm_path_lyt.addWidget(fm_up_btn)
        fm_path_lyt.addWidget(fm_ref_btn)
        layout.addLayout(fm_path_lyt)

        layout.addWidget(self.file_status_label)
        layout.addWidget(self.file_table)

        fm_local_lyt = QHBoxLayout()
        fm_local_lyt.addWidget(QLabel("本地下载至:"))
        fm_local_lyt.addWidget(self.local_down_edit, 4)
        fm_down_browse = QPushButton("浏览...")
        fm_down_browse.clicked.connect(on_browse_download_dir)
        fm_local_lyt.addWidget(fm_down_browse, 1)
        layout.addLayout(fm_local_lyt)
