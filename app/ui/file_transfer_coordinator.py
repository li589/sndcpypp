from collections.abc import Callable

from PyQt6.QtCore import QTimer

from app.ui.file_table_presenter import populate_file_table, update_symlink_in_table
from app.ui.interaction_helpers import ensure_trailing_slash
from app.ui.message_templates import (
    file_status_read_failed,
    log_loaded_items,
    log_symlink_resolved,
)


def collect_existing_names(file_table) -> set[str]:
    names: set[str] = set()
    for row in range(file_table.rowCount()):
        item = file_table.item(row, 1)
        if item:
            names.add(item.text())
    return names


def should_refresh_file_view_after_transfer(
    *,
    device_serial: str,
    transfer_kind: str,
    remote_path: str,
    current_device: str,
    current_path_text: str,
) -> bool:
    if transfer_kind != "push":
        return False
    if device_serial != current_device:
        return False
    current_path = ensure_trailing_slash(current_path_text.strip() or "/")
    return current_path == ensure_trailing_slash(remote_path or "/")


def handle_file_progress(
    *,
    status: str,
    device_serial: str,
    transfer_kind: str,
    remote_path: str,
    msg: str,
    percent: int,
    progress_bar,
    set_status: Callable[[str], None],
    should_refresh: bool,
    on_refresh: Callable[[], None] | None = None,
) -> None:
    set_status(msg)
    if status == "start":
        progress_bar.setVisible(True)
        progress_bar.setRange(0, 100)
        progress_bar.setValue(0)
    elif status == "progress":
        progress_bar.setValue(percent)
    elif status == "done":
        progress_bar.setValue(100)
        QTimer.singleShot(1500, lambda: progress_bar.setVisible(False))
        if should_refresh and on_refresh is not None:
            QTimer.singleShot(500, on_refresh)
    elif status == "error":
        progress_bar.setValue(percent)
        QTimer.singleShot(1500, lambda: progress_bar.setVisible(False))


def update_file_table(
    *,
    path: str,
    file_list: list,
    success: bool,
    file_table,
    file_status_label,
    set_current_remote_path: Callable[[str], None],
    log_to_console: Callable[[str, str], None],
) -> None:
    if success:
        set_current_remote_path(path)
        populate_file_table(file_table, file_status_label, file_list)
        log_to_console(log_loaded_items(len(file_list), path), "success")
    else:
        file_table.setRowCount(0)
        file_status_label.setText(file_status_read_failed())


def handle_symlink_resolved(
    *,
    device_serial: str,
    name: str,
    is_dir: bool,
    current_device: str,
    file_table,
    log_to_console: Callable[[str, str], None],
) -> None:
    if device_serial != current_device:
        return
    update_symlink_in_table(file_table, name, is_dir)
    log_to_console(log_symlink_resolved(name, is_dir), "output")
