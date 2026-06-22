import os
from collections.abc import Callable
from typing import Protocol

from app.ui.interaction_helpers import join_remote_path
from app.ui.message_templates import (
    log_download_skipped,
    log_pull_from_device,
    log_upload_preparing,
    log_upload_skipped,
)
from app.ui.popup_manager import PopupManager


class SupportsDownloadEntry(Protocol):
    name: str
    is_dir: bool


def handle_download_request(
    entry: SupportsDownloadEntry,
    *,
    remote_base_path: str,
    local_dir: str,
    popups: PopupManager,
    log_to_console: Callable[[str, str], None],
    request_pull: Callable[[str, str, str | None], None],
) -> None:
    remote_file = join_remote_path(remote_base_path, entry.name)

    if not os.path.exists(local_dir):
        popups.show_download_directory_invalid()
        return

    target_name = entry.name
    real_target_path = os.path.join(local_dir, target_name)
    rename_to = None

    if os.path.exists(real_target_path):
        action, rename_to = popups.resolve_file_conflict(
            target_name,
            False,
            lambda name: os.path.exists(os.path.join(local_dir, name)),
        )
        if action == "skip":
            log_to_console(log_download_skipped(entry.name), "info")
            return

    desc = "文件夹" if entry.is_dir else "文件"
    log_to_console(log_pull_from_device(desc, target_name, rename_to), "info")
    request_pull(remote_file, local_dir, rename_to)


def submit_upload_requests(
    local_paths: list[str],
    *,
    existing_names: set[str],
    popups: PopupManager,
    log_to_console: Callable[[str, str], None],
    request_push: Callable[[str, str | None], None],
) -> None:
    for path in local_paths:
        target_name = os.path.basename(path.rstrip("/"))
        rename_to = None

        if target_name in existing_names:
            action, rename_to = popups.resolve_file_conflict(
                target_name,
                True,
                existing_names.__contains__,
            )
            if action == "rename" and rename_to is not None:
                existing_names.add(rename_to)
            elif action == "skip":
                log_to_console(log_upload_skipped(target_name), "info")
                continue

        log_to_console(log_upload_preparing(target_name, rename_to), "info")
        request_push(path, rename_to)
