from collections.abc import Callable

from app.ui.message_templates import CMD_SETTINGS_TITLES, log_settings_save_failed
from app.ui.runtime_settings import apply_ui_settings, collect_ui_settings


def load_settings_from_store(settings_store) -> tuple[dict, str | None]:
    settings = settings_store.load()
    warning = settings_store.last_load_warning
    return settings, warning


def save_settings(
    *,
    settings_store,
    window,
    settings: dict,
    log_to_console: Callable[[str, str], None],
) -> None:
    collected = collect_ui_settings(window, settings)
    try:
        settings_store.save(collected)
        settings.update(collected)
    except Exception as exc:
        log_to_console(log_settings_save_failed(str(exc)), "error")


def apply_settings_to_ui(window, settings: dict) -> None:
    apply_ui_settings(window, settings)


def apply_cmd_extra_settings(
    *,
    cmd_type: str,
    updated_value: str | None,
    settings: dict,
) -> str | None:
    if updated_value is None:
        return None
    settings[f"{cmd_type}_extra"] = updated_value
    return CMD_SETTINGS_TITLES.get(cmd_type)
