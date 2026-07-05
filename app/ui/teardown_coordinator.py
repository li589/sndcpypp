from collections.abc import Callable

from app.ui.dialogs import ExitAction
from app.ui.message_templates import log_cleanup_processes

_SHUTDOWN_TIMEOUT_SECONDS = 8


def handle_close_event(
    *,
    event,
    force_quit: bool,
    confirm_exit: Callable[[], ExitAction],
    hide_to_tray: Callable[[], None],
    save_settings: Callable[[], None],
    usb_monitor,
    core_controller,
    log_to_console: Callable[[str, str], None],
    scan_timer,
    tray_icon,
    extra_timers=None,
) -> ExitAction:
    """统一处理主窗口 `closeEvent` 的退出确认与资源清理流程。

    返回值：用户实际选择的退出动作（`HIDE_TO_TRAY` 或 `EXIT`）。
    调用方应根据返回值与 `event.ignore()` / `event.accept()` 的语义在自身
    `closeEvent` 中决定是否真正关闭窗口。本函数会主动调用
    `event.ignore()`（隐藏到托盘）或 `event.accept()`（真正退出）。
    """
    if not force_quit:
        res = confirm_exit()
        if res == ExitAction.HIDE_TO_TRAY:
            hide_to_tray()
            event.ignore()
            return ExitAction.HIDE_TO_TRAY
        if res != ExitAction.EXIT:
            event.ignore()
            return res

    save_settings()

    if usb_monitor is not None:
        usb_monitor.stop_monitoring()

    if core_controller is not None:
        log_to_console(log_cleanup_processes(), "warning")
        if not core_controller.request_shutdown_and_wait(timeout=_SHUTDOWN_TIMEOUT_SECONDS):
            log_to_console("后台清理超时，应用将继续退出。", "warning")

    if scan_timer is not None and hasattr(scan_timer, "isActive") and scan_timer.isActive():
        scan_timer.stop()

    # 停止其他活跃定时器（status_indicator_timer 等），避免退出时触发已销毁对象
    if extra_timers:
        for timer in extra_timers:
            if timer is not None and hasattr(timer, "isActive") and timer.isActive():
                timer.stop()

    if tray_icon is not None:
        tray_icon.hide()

    event.accept()
    return ExitAction.EXIT
