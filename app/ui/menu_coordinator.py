from collections.abc import Callable
from typing import Protocol

from PyQt6.QtCore import QPoint
from PyQt6.QtWidgets import QApplication, QTableWidgetItem, QTextEdit

from app.ui.menu_builders import FileTableMenuAction, apply_menu_style
from app.ui.message_templates import CONSOLE_MENU_CLEAR_LOGS, CONSOLE_MENU_EXPORT_LOGS
from app.ui.popup_manager import PopupManager


class SupportsFileMenuEntry(Protocol):
    name: str
    symlink_target: str | None


def show_console_context_menu(console_output: QTextEdit, pos: QPoint, popups: PopupManager) -> None:
    menu = console_output.createStandardContextMenu()
    apply_menu_style(menu)
    menu.addSeparator()
    clear_action = menu.addAction(CONSOLE_MENU_CLEAR_LOGS)
    export_action = menu.addAction(CONSOLE_MENU_EXPORT_LOGS)

    action = menu.exec(console_output.mapToGlobal(pos))
    if action == clear_action:
        console_output.clear()
    elif action == export_action:
        _export_console_logs(console_output.toPlainText(), popups)


def handle_file_table_action(
    action: FileTableMenuAction | None,
    *,
    is_directory_entry: bool,
    type_item: QTableWidgetItem,
    entry: SupportsFileMenuEntry,
    remote_path: str,
    on_enter_folder: Callable[[QTableWidgetItem], None],
    on_download: Callable[[], None],
) -> None:
    if action == "download":
        on_download()
        return

    if action == "copy_name":
        QApplication.clipboard().setText(entry.name)
        return

    if action == "copy_full_path":
        QApplication.clipboard().setText(remote_path)
        return

    if action == "copy_link_target" and entry.symlink_target:
        QApplication.clipboard().setText(entry.symlink_target)
        return

    if is_directory_entry and action == "enter_folder":
        on_enter_folder(type_item)


def _export_console_logs(log_text: str, popups: PopupManager) -> None:
    file_path = popups.save_file(
        "导出日志",
        "sndcpy_log.txt",
        "Text Files (*.txt);;Log Files (*.log);;All Files (*)",
    )
    if not file_path:
        return

    try:
        with open(file_path, "w", encoding="utf-8") as file_obj:
            file_obj.write(log_text)
        popups.show_export_logs_success()
    except Exception as exc:
        popups.show_export_logs_failure(str(exc))
