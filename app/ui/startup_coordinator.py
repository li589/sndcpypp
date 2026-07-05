from collections.abc import Callable

from app.ui.message_templates import (
    log_initial_validation,
    log_usb_monitor_start_failed,
    log_usb_monitor_started,
)


def run_startup_routine(
    *,
    log_to_console: Callable[[str, str], None],
    validate_paths: Callable[[], None],
    usb_monitor,
) -> bool:
    """应用启动后的初始化例行流程。

    1. 输出初始校验日志；
    2. 触发路径校验；
    3. 启动 USB 监控（失败时记录日志）。

    返回值表示 USB 监控是否成功启动；调用方在失败时应将 `usb_monitor` 引用置空
    以避免后续重复使用已损坏的实例。
    """
    log_to_console(log_initial_validation(), "info")
    validate_paths()
    if usb_monitor is None:
        return False
    try:
        usb_monitor.start_monitoring()
    except Exception as exc:
        log_to_console(log_usb_monitor_start_failed(str(exc)), "warning")
        return False
    log_to_console(log_usb_monitor_started(), "success")
    return True
