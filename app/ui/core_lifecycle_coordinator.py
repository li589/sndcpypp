from collections.abc import Callable

from app.domain.models.operation_requests import RuntimeConfigurationRequest
from app.infrastructure.adb.path_resolver import ResolvedADBPath
from app.ui.message_templates import (
    log_adb_resolution_builtin,
    log_adb_resolution_external,
    log_adb_resolution_fallback,
    log_adb_resolution_unresolved,
)
from app.ui.runtime_settings import build_runtime_configuration_request, resolve_runtime_paths
from core import CoreController


def resolve_and_prepare_paths(
    *,
    adb_path_text: str,
    player_path_text: str,
    sndcpy_dir_text: str,
    adb_path_resolver,
    app_base_dir: str,
    set_adb_tooltip: Callable[[str], None],
) -> tuple[ResolvedADBPath, str, str]:
    adb_resolution, player_path, sndcpy_dir = resolve_runtime_paths(
        adb_path_text,
        player_path_text,
        sndcpy_dir_text,
        adb_path_resolver=adb_path_resolver,
        app_base_dir=app_base_dir,
    )
    set_adb_tooltip(
        "留空时自动优先尝试外部 ADB，失败后回退到内置 ADB。\n"
        f"当前解析: {adb_resolution.source}\n{adb_resolution.path}"
    )
    return adb_resolution, player_path, sndcpy_dir


def maybe_log_adb_resolution(
    adb_resolution: ResolvedADBPath,
    last_signature: tuple | None,
    log_to_console: Callable[[str, str], None],
) -> tuple | None:
    signature = (
        adb_resolution.path,
        adb_resolution.source,
        adb_resolution.used_fallback,
        adb_resolution.requested_path,
    )
    if signature == last_signature:
        return last_signature

    if adb_resolution.requested_path and adb_resolution.used_fallback:
        log_to_console(
            log_adb_resolution_fallback(adb_resolution.source, adb_resolution.path),
            "warning",
        )
        return signature

    if adb_resolution.source == "内置 Sndcpy":
        log_to_console(log_adb_resolution_builtin(adb_resolution.path), "info")
        return signature

    if adb_resolution.source != "未解析":
        log_to_console(log_adb_resolution_external(adb_resolution.source, adb_resolution.path), "success")
        return signature

    log_to_console(log_adb_resolution_unresolved(adb_resolution.path), "warning")
    return signature


def sync_core_runtime(
    *,
    core_controller: CoreController | None,
    settings: dict,
    adb_resolution: ResolvedADBPath | None = None,
    player_path: str | None = None,
    sndcpy_dir: str | None = None,
    log_resolution: bool = True,
    last_adb_signature: tuple | None = None,
    resolve_paths: Callable[[], tuple[ResolvedADBPath, str, str]],
    log_to_console: Callable[[str, str], None],
) -> tuple | None:
    if not core_controller:
        return last_adb_signature

    if adb_resolution is None or player_path is None or sndcpy_dir is None:
        adb_resolution, player_path, sndcpy_dir = resolve_paths()

    new_signature = last_adb_signature
    if log_resolution:
        new_signature = maybe_log_adb_resolution(adb_resolution, last_adb_signature, log_to_console)

    core_controller.request_configure_runtime(
        build_runtime_configuration_request(settings, adb_resolution, player_path, sndcpy_dir)
    )
    return new_signature


def build_signal_pairs(controller: CoreController, slots: dict[str, Callable]) -> list[tuple]:
    return [
        (controller.devices_updated, slots["update_device_list"]),
        (controller.log_message, slots["log_to_console"]),
        (controller.operation_completed, slots["handle_operation_complete"]),
        (controller.validation_result, slots["handle_validation_result"]),
        (controller.player_process_exited, slots["handle_player_exit"]),
        (controller.recording_state_changed, slots["handle_recording_state_change"]),
        (controller.files_listed_detailed, slots["update_file_table"]),
        (controller.symlink_resolved, slots["handle_symlink_resolved"]),
        (controller.file_transfer_progress, slots["handle_file_progress"]),
    ]


def connect_core_signals(controller: CoreController, slots: dict[str, Callable]) -> None:
    for signal, slot in build_signal_pairs(controller, slots):
        signal.connect(slot)


def disconnect_core_signals(controller: CoreController | None, slots: dict[str, Callable]) -> None:
    if controller is None:
        return
    for signal, slot in build_signal_pairs(controller, slots):
        try:
            signal.disconnect(slot)
        except TypeError:
            pass


def recreate_core_controller(
    *,
    previous_controller: CoreController | None,
    slots: dict[str, Callable],
    resolve_paths: Callable[[], tuple[ResolvedADBPath, str, str]],
    log_to_console: Callable[[str, str], None],
    last_adb_signature: tuple | None,
    settings: dict,
) -> tuple[CoreController, tuple | None]:
    if previous_controller:
        disconnect_core_signals(previous_controller, slots)
        previous_controller.request_shutdown()
        previous_controller.deleteLater()

    adb_resolution, player_path, sndcpy_dir = resolve_paths()
    new_signature = maybe_log_adb_resolution(adb_resolution, last_adb_signature, log_to_console)

    controller = CoreController(adb_resolution.path, player_path, sndcpy_dir)
    new_signature = sync_core_runtime(
        core_controller=controller,
        settings=settings,
        adb_resolution=adb_resolution,
        player_path=player_path,
        sndcpy_dir=sndcpy_dir,
        log_resolution=False,
        last_adb_signature=new_signature,
        resolve_paths=resolve_paths,
        log_to_console=log_to_console,
    )
    connect_core_signals(controller, slots)
    return controller, new_signature
