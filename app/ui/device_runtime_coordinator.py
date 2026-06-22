from dataclasses import dataclass
from collections.abc import Callable

from app.ui.message_templates import validation_status_text


@dataclass(frozen=True)
class ValidationUiResult:
    adb_valid: bool
    player_valid: bool
    sndcpy_valid: bool
    are_paths_ready: bool
    next_first_startup: bool


def apply_validation_result_ui(
    results: list[int],
    *,
    is_first_startup: bool,
    set_status: Callable[[str], None],
    restore_validation_actions: Callable[[], None],
    on_first_ready: Callable[[], None] | None = None,
) -> ValidationUiResult:
    adb_valid, player_valid, sndcpy_valid = [bool(value) for value in results]
    are_paths_ready = adb_valid and player_valid and sndcpy_valid

    set_status(validation_status_text(adb_valid, player_valid, sndcpy_valid))
    restore_validation_actions()

    if is_first_startup and are_paths_ready and on_first_ready is not None:
        on_first_ready()

    return ValidationUiResult(
        adb_valid=adb_valid,
        player_valid=player_valid,
        sndcpy_valid=sndcpy_valid,
        are_paths_ready=are_paths_ready,
        next_first_startup=False if is_first_startup else is_first_startup,
    )
