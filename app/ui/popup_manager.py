from collections.abc import Callable
from typing import Literal

from PyQt6.QtWidgets import QDialog, QFileDialog, QMessageBox, QWidget

from app.ui.dialogs import (
    DIALOG_STYLESHEET,
    ExitAction,
    ExitConfirmDialog,
    FileConflictDialog,
    ParamSettingsDialog,
)
from app.ui.interaction_helpers import (
    overwrite_file_message,
    player_exit_message,
    recording_audio_conflict_message,
    resolve_conflict_choice,
)
from app.ui.message_templates import (
    CMD_SETTINGS_TITLES,
    POPUP_AUDIOROUTER_QUICK_FILL_LABEL,
    POPUP_MSG_DEVICE_REQUIRED,
    POPUP_MSG_DOWNLOAD_DIRECTORY_INVALID,
    POPUP_MSG_EXPORT_LOGS_SUCCESS,
    POPUP_MSG_RECORD_DIRECTORY_INVALID,
    POPUP_MSG_RECORDING_DEVICE_REQUIRED,
    POPUP_MSG_RECORDING_TARGET_REQUIRED,
    POPUP_MSG_SNDCPY_INSTALL_FAILED,
    POPUP_MSG_SNDCPY_INSTALL_SUCCESS,
    POPUP_TITLE_AUDIO_CONFLICT,
    POPUP_TITLE_ERROR,
    POPUP_TITLE_FAILURE,
    POPUP_TITLE_FILE_EXISTS,
    POPUP_TITLE_PLAYER_EXIT,
    POPUP_TITLE_SUCCESS,
    POPUP_TITLE_WARNING,
    param_settings_dialog_title,
    popup_msg_export_logs_failure,
    popup_msg_record_overwrite_failed,
)
from app.ui.runtime_settings import get_audio_router_recommended_args


class PopupManager:
    def __init__(self, parent: QWidget, audit_callback: Callable[[str, str], None] | None = None):
        self.parent = parent
        self._audit_callback = audit_callback

    def info(self, title: str, message: str) -> None:
        self._show_message_box(QMessageBox.Icon.Information, title, message)

    def warning(self, title: str, message: str) -> None:
        self._show_message_box(QMessageBox.Icon.Warning, title, message)

    def error(self, title: str, message: str) -> None:
        self._show_message_box(QMessageBox.Icon.Critical, title, message)

    def confirm(self, title: str, message: str, default_no: bool = True) -> bool:
        default_button = QMessageBox.StandardButton.No if default_no else QMessageBox.StandardButton.Yes
        box = self._create_message_box(
            QMessageBox.Icon.Question,
            title,
            message,
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            default_button,
        )
        reply = box.exec()
        self._audit(f"确认弹窗: {title} -> {'是' if reply == QMessageBox.StandardButton.Yes else '否'}")
        return reply == QMessageBox.StandardButton.Yes

    def open_param_settings(self, cmd_type: str, current_val: str) -> str | None:
        title = CMD_SETTINGS_TITLES.get(cmd_type, "")
        quick_fill_actions: list[tuple[str, str]] = []
        if cmd_type == "player":
            quick_fill_actions.append((POPUP_AUDIOROUTER_QUICK_FILL_LABEL, get_audio_router_recommended_args()))
        dialog = ParamSettingsDialog(
            self.parent,
            title=param_settings_dialog_title(title),
            param_name=title,
            current_val=current_val,
            quick_fill_actions=quick_fill_actions,
        )
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self._audit(f"参数弹窗: 已保存 {title} 附加参数")
            return dialog.get_value()
        self._audit(f"参数弹窗: 已取消 {title} 附加参数")
        return None

    def confirm_exit_action(self) -> ExitAction:
        result = ExitConfirmDialog(self.parent).exec()
        try:
            action = ExitAction(result)
        except ValueError:
            action = ExitAction.CANCEL
        self._audit(f"退出弹窗: {action.name}")
        return action

    def confirm_recording_audio_conflict(self) -> bool:
        return self.confirm(POPUP_TITLE_AUDIO_CONFLICT, recording_audio_conflict_message(), default_no=True)

    def confirm_overwrite_existing_file(self, filename: str) -> bool:
        return self.confirm(POPUP_TITLE_FILE_EXISTS, overwrite_file_message(filename), default_no=True)

    def confirm_restart_audio_route(self, device_serial: str) -> bool:
        return self.confirm(POPUP_TITLE_PLAYER_EXIT, player_exit_message(device_serial), default_no=True)

    def resolve_file_conflict(
        self,
        target_name: str,
        is_upload: bool,
        exists: Callable[[str], bool],
    ) -> tuple[Literal["overwrite", "rename", "skip"], str | None]:
        dialog = FileConflictDialog(target_name, is_upload=is_upload, parent=self.parent)
        action, rename_to = resolve_conflict_choice(target_name, dialog.exec(), exists)
        detail = f"{action}" if rename_to is None else f"{action} -> {rename_to}"
        self._audit(f"文件冲突弹窗: {target_name} ({'上传' if is_upload else '下载'}) -> {detail}")
        return action, rename_to

    def open_file(self, title: str, directory: str = "", file_filter: str = "所有文件 (*.*)") -> str | None:
        dialog = self._create_file_dialog(title, directory, file_filter, QFileDialog.FileMode.ExistingFile)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            selected = dialog.selectedFiles()[0]
            self._audit(f"文件选择弹窗: {title} -> {selected}")
            return selected
        self._audit(f"文件选择弹窗: {title} -> 已取消")
        return None

    def select_directory(self, title: str, directory: str = "") -> str | None:
        dialog = self._create_file_dialog(title, directory, "", QFileDialog.FileMode.Directory)
        dialog.setOption(QFileDialog.Option.ShowDirsOnly, True)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            selected = dialog.selectedFiles()[0]
            self._audit(f"目录选择弹窗: {title} -> {selected}")
            return selected
        self._audit(f"目录选择弹窗: {title} -> 已取消")
        return None

    def save_file(self, title: str, suggested_name: str = "", file_filter: str = "所有文件 (*.*)") -> str | None:
        dialog = self._create_file_dialog(title, suggested_name, file_filter, QFileDialog.FileMode.AnyFile)
        dialog.setAcceptMode(QFileDialog.AcceptMode.AcceptSave)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            selected = dialog.selectedFiles()[0]
            self._audit(f"保存文件弹窗: {title} -> {selected}")
            return selected
        self._audit(f"保存文件弹窗: {title} -> 已取消")
        return None

    def show_export_logs_success(self) -> None:
        self.info(POPUP_TITLE_SUCCESS, POPUP_MSG_EXPORT_LOGS_SUCCESS)

    def show_export_logs_failure(self, error_text: str) -> None:
        self.error(POPUP_TITLE_ERROR, popup_msg_export_logs_failure(error_text))

    def show_device_required_warning(self) -> None:
        self.warning(POPUP_TITLE_WARNING, POPUP_MSG_DEVICE_REQUIRED)

    def show_recording_device_required_warning(self) -> None:
        self.warning(POPUP_TITLE_WARNING, POPUP_MSG_RECORDING_DEVICE_REQUIRED)

    def show_recording_target_required_warning(self) -> None:
        self.warning(POPUP_TITLE_WARNING, POPUP_MSG_RECORDING_TARGET_REQUIRED)

    def show_record_directory_invalid(self) -> None:
        self.error(POPUP_TITLE_ERROR, POPUP_MSG_RECORD_DIRECTORY_INVALID)

    def show_record_overwrite_failed(self, error_text: str) -> None:
        self.error(POPUP_TITLE_ERROR, popup_msg_record_overwrite_failed(error_text))

    def show_download_directory_invalid(self) -> None:
        self.error(POPUP_TITLE_ERROR, POPUP_MSG_DOWNLOAD_DIRECTORY_INVALID)

    def show_install_result(self, success: bool) -> None:
        if success:
            self.info(POPUP_TITLE_SUCCESS, POPUP_MSG_SNDCPY_INSTALL_SUCCESS)
            return
        self.warning(POPUP_TITLE_FAILURE, POPUP_MSG_SNDCPY_INSTALL_FAILED)

    def _show_message_box(self, icon: QMessageBox.Icon, title: str, message: str) -> None:
        box = self._create_message_box(icon, title, message, QMessageBox.StandardButton.Ok)
        box.exec()
        self._audit(f"提示弹窗: {title}")

    def _create_message_box(
        self,
        icon: QMessageBox.Icon,
        title: str,
        message: str,
        buttons: QMessageBox.StandardButton,
        default_button: QMessageBox.StandardButton | None = None,
    ) -> QMessageBox:
        box = QMessageBox(self.parent)
        box.setIcon(icon)
        box.setWindowTitle(title)
        box.setText(message)
        box.setStandardButtons(buttons)
        if default_button is not None:
            box.setDefaultButton(default_button)
        box.setStyleSheet(DIALOG_STYLESHEET)
        return box

    def _create_file_dialog(
        self,
        title: str,
        directory: str,
        file_filter: str,
        file_mode: QFileDialog.FileMode,
    ) -> QFileDialog:
        dialog = QFileDialog(self.parent, title, directory, file_filter)
        dialog.setFileMode(file_mode)
        dialog.setOption(QFileDialog.Option.DontUseNativeDialog, True)
        dialog.setStyleSheet(DIALOG_STYLESHEET)
        return dialog

    def _audit(self, message: str) -> None:
        if self._audit_callback is not None:
            self._audit_callback(message, "popup")
