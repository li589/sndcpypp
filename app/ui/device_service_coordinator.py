from collections.abc import Callable

from app.ui.message_templates import (
    status_adb_cleanup_running,
    status_adb_restart_submitted,
    status_installing,
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


def submit_restart_adb(
    *,
    core_controller,
    cooldown: Callable[[], None],
    set_status: Callable[[str], None],
) -> None:
    if not core_controller:
        return
    submit_adb_service_action(
        before_submit=cooldown,
        set_status=set_status,
        submit=core_controller.request_restart_adb,
        restart=True,
    )


def submit_kill_adb(
    *,
    core_controller,
    cooldown: Callable[[], None],
    set_status: Callable[[str], None],
) -> None:
    if not core_controller:
        return
    submit_adb_service_action(
        before_submit=cooldown,
        set_status=set_status,
        submit=core_controller.request_force_kill_adb,
        restart=False,
    )


def submit_install_sndcpy(
    *,
    device_serial: str,
    core_controller,
    cooldown: Callable[[], None],
    set_status: Callable[[str], None],
    show_busy_progress: Callable[[], None],
) -> None:
    if not device_serial or not core_controller:
        return
    if cooldown is not None:
        cooldown()
    set_status(status_installing(device_serial))
    core_controller.request_install_apk(device_serial)
    show_busy_progress()


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
