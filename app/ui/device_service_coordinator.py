from collections.abc import Callable

from app.ui.message_templates import (
    status_adb_cleanup_running,
    status_adb_restart_submitted,
    status_operation_result,
)


def submit_adb_service_action(
    *,
    before_submit: Callable[[], None] | None = None,
    set_status: Callable[[str], None],
    submit: Callable[[], None],
    restart: bool,
) -> None:
    if before_submit is not None:
        before_submit()
    set_status(status_adb_restart_submitted() if restart else status_adb_cleanup_running())
    submit()


def finalize_operation_ui(
    operation: str,
    success: bool,
    *,
    hide_progress: Callable[[], None],
    set_status: Callable[[str], None],
    show_install_result: Callable[[bool], None] | None = None,
) -> None:
    hide_progress()
    status_text = status_operation_result(operation, success)
    if status_text is not None:
        set_status(status_text)
    if operation == "install" and show_install_result is not None:
        show_install_result(success)
