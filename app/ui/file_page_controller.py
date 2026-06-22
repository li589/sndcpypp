from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QTableWidgetItem

from app.ui.file_actions import handle_download_request
from app.ui.interaction_helpers import join_remote_path, parent_remote_path
from app.ui.menu_builders import exec_file_table_context_menu
from app.ui.menu_coordinator import handle_file_table_action
from app.ui.message_templates import log_download_preparing, log_listing_path, log_symlink_unavailable
from core import FileType


class FilePageController:
    def __init__(
        self,
        *,
        host_widget,
        file_device_combo,
        remote_path_edit,
        file_table,
        local_down_edit,
        core_provider,
        popups,
        log_to_console,
        request_list_files,
        request_pull,
    ):
        self._host_widget = host_widget
        self._file_device_combo = file_device_combo
        self._remote_path_edit = remote_path_edit
        self._file_table = file_table
        self._local_down_edit = local_down_edit
        self._core_provider = core_provider
        self._popups = popups
        self._log_to_console = log_to_console
        self._request_list_files = request_list_files
        self._request_pull = request_pull

    def refresh_file_list(self) -> None:
        device = self._file_device_combo.currentText()
        if not device or self._core_provider() is None:
            return

        target = self._request_list_files(device, self._remote_path_edit.text().strip())
        if target:
            self._remote_path_edit.setText(target)
            self._log_to_console(log_listing_path(target), "info")

    def go_up_dir(self) -> None:
        current = self._remote_path_edit.text().strip()
        if current == "/":
            return
        self._remote_path_edit.setText(parent_remote_path(current))
        self.refresh_file_list()

    def handle_table_double_click(self, item: QTableWidgetItem) -> None:
        row = item.row()
        type_item = self._file_table.item(row, 0)
        if not type_item:
            return
        fi = type_item.data(Qt.ItemDataRole.UserRole)
        if not fi:
            return

        if fi.is_dir or (fi.file_type == FileType.SYMLINK and fi.is_symlink_to_dir is True):
            new_path = join_remote_path(self._remote_path_edit.text().strip(), fi.name, is_dir=True)
            self._remote_path_edit.setText(new_path)
            self.refresh_file_list()
            return

        if fi.file_type != FileType.SYMLINK or fi.is_symlink_to_dir is False:
            self._log_to_console(log_download_preparing(fi.name, fi.size_display, fi.type_description), "info")
            self.download_file_item(fi)
            return

        self._log_to_console(log_symlink_unavailable(fi.name), "warning")

    def show_file_table_menu(self, pos) -> None:
        item = self._file_table.itemAt(pos)
        if not item:
            return

        row = item.row()
        type_item = self._file_table.item(row, 0)
        if not type_item:
            return
        fi = type_item.data(Qt.ItemDataRole.UserRole)
        if not fi:
            return

        remote_path = join_remote_path(self._remote_path_edit.text().strip(), fi.name)
        is_directory_entry = fi.is_dir or (fi.file_type == FileType.SYMLINK and fi.is_symlink_to_dir is True)
        action = exec_file_table_context_menu(
            self._host_widget,
            self._file_table.mapToGlobal(pos),
            is_directory_entry=is_directory_entry,
            include_copy_link_target=bool(fi.is_symlink and fi.symlink_target),
        )

        handle_file_table_action(
            action,
            is_directory_entry=is_directory_entry,
            type_item=type_item,
            entry=fi,
            remote_path=remote_path,
            on_enter_folder=self.handle_table_double_click,
            on_download=lambda: self.download_file_item(fi),
        )

    def download_file_item(self, fi) -> None:
        device = self._file_device_combo.currentText()
        if not device or self._core_provider() is None:
            return

        handle_download_request(
            fi,
            remote_base_path=self._remote_path_edit.text().strip(),
            local_dir=self._local_down_edit.text().strip(),
            popups=self._popups,
            log_to_console=self._log_to_console,
            request_pull=lambda remote_file, local_dir, rename_to: self._request_pull(
                device,
                remote_file,
                local_dir,
                rename_to,
            ),
        )
