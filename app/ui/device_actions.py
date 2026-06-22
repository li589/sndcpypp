from collections.abc import Callable

from app.ui.message_templates import scoped_status_text


def submit_scoped_stop_action(
    *,
    device_serial: str | None,
    before_submit: Callable[[], None] | None = None,
    submit: Callable[[str | None], None],
    set_status: Callable[[str], None],
    device_template: str,
    all_devices_text: str,
    after_submit: Callable[[], None] | None = None,
) -> None:
    normalized_device = (device_serial or "").strip() or None

    if before_submit is not None:
        before_submit()
    submit(normalized_device)
    set_status(scoped_status_text(normalized_device, device_template, all_devices_text))
    if after_submit is not None:
        after_submit()


def submit_device_start_action(
    device_serial: str,
    *,
    before_submit: Callable[[], None] | None = None,
    submit: Callable[[str], None],
    set_status: Callable[[str], None],
    status_text: str,
    after_submit: Callable[[], None] | None = None,
) -> None:
    normalized_device = device_serial.strip()
    if not normalized_device:
        return

    if before_submit is not None:
        before_submit()
    set_status(status_text)
    submit(normalized_device)
    if after_submit is not None:
        after_submit()
