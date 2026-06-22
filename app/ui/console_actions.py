from collections.abc import Callable


def submit_console_command(
    command_text: str,
    *,
    before_submit: Callable[[], None] | None = None,
    submit: Callable[[str], None],
    after_submit: Callable[[], None] | None = None,
) -> bool:
    normalized_command = (command_text or "").strip()
    if not normalized_command:
        return False

    if before_submit is not None:
        before_submit()
    submit(normalized_command)
    if after_submit is not None:
        after_submit()
    return True
