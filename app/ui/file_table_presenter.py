from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor

from app.domain.enums.file_type import FileType
from app.ui.message_templates import file_list_summary, symlink_target_display, symlink_type_text
from app.ui.widgets import FileTableWidgetItem


def populate_file_table(file_table, file_status_label, file_list: list) -> None:
    file_table.setRowCount(0)
    file_table.setRowCount(len(file_list))
    file_table.setSortingEnabled(False)

    dir_count, file_count, link_count = 0, 0, 0

    for row, fi in enumerate(file_list):
        type_text = _file_type_label(fi)
        sort_key = (0 if fi.is_dir else 1, fi.name.lower())
        type_item = FileTableWidgetItem(type_text, sort_key)

        if fi.file_type == FileType.SYMLINK:
            type_item.setForeground(QColor(100, 180, 255))
            link_count += 1
        elif fi.file_type == FileType.DIRECTORY:
            type_item.setForeground(QColor(62, 170, 127))
            dir_count += 1
        else:
            type_item.setForeground(QColor(200, 200, 200))
            file_count += 1

        file_table.setItem(row, 0, type_item)

        name_item = FileTableWidgetItem(fi.name, sort_key)
        if fi.file_type == FileType.SYMLINK:
            name_item.setForeground(QColor(100, 180, 255))
            name_item.setToolTip(f"符号链接 -> {fi.symlink_target}")
        elif fi.file_type == FileType.DIRECTORY:
            name_item.setForeground(QColor(62, 170, 127))
        elif _is_executable_entry(fi.permissions):
            name_item.setForeground(QColor(255, 200, 80))
        file_table.setItem(row, 1, name_item)

        size_item = FileTableWidgetItem(fi.size_display, (fi.size, fi.name.lower()))
        size_item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        file_table.setItem(row, 2, size_item)

        file_table.setItem(row, 3, FileTableWidgetItem(fi.permissions, (0, fi.permissions)))

        owner_item = FileTableWidgetItem(fi.owner, (0 if fi.is_root_owned else 1, fi.owner))
        if fi.is_root_owned:
            owner_item.setForeground(QColor(255, 85, 85))
            owner_item.setToolTip("Root 所有 - 跨界操作可能受限")
        file_table.setItem(row, 4, owner_item)

        file_table.setItem(row, 5, FileTableWidgetItem(fi.date_str, (0, fi.date_str)))
        file_table.setItem(row, 6, _build_link_target_item(fi))
        type_item.setData(Qt.ItemDataRole.UserRole, fi)

    file_status_label.setText(file_list_summary(dir_count, file_count, link_count))


def update_symlink_in_table(file_table, name: str, is_dir: bool) -> bool:
    for row in range(file_table.rowCount()):
        item = file_table.item(row, 0)
        if not item:
            continue

        fi = item.data(Qt.ItemDataRole.UserRole)
        if fi and fi.name == name and fi.file_type == FileType.SYMLINK:
            fi.is_symlink_to_dir = is_dir
            item.setText(symlink_type_text(is_dir))
            link_item = file_table.item(row, 6)
            if link_item:
                link_item.setText(symlink_target_display(fi.symlink_target, is_dir))
            return True
    return False


def _file_type_label(fi) -> str:
    if fi.is_dir:
        return "📁 目录"
    if fi.is_symlink:
        return "🔗 链接"
    return "📄 文件"


def _build_link_target_item(fi) -> FileTableWidgetItem:
    if fi.file_type == FileType.SYMLINK and fi.symlink_target:
        link_item = FileTableWidgetItem(
            symlink_target_display(fi.symlink_target, fi.is_symlink_to_dir),
            (0, fi.symlink_target.lower()),
        )
        link_item.setForeground(QColor(100, 180, 255))
        return link_item
    return FileTableWidgetItem("", (0, ""))


def _is_executable_entry(permissions: str) -> bool:
    return not permissions.startswith("-") and len(permissions) > 3 and permissions[3] == "x"
