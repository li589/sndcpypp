from app.domain.models.operation_requests import (
    BrowseFilesRequest,
    ConsoleCommandRequest,
    ConsoleTargetKind,
    PullFileRequest,
    PushFileRequest,
    RecordingRequest,
    RoutingRequest,
)
from app.infrastructure.config.constants import DEFAULT_AUDIO_PORT
from app.ui.interaction_helpers import ensure_trailing_slash
from app.ui.pages.console_page import CONSOLE_TARGET_NO_DEVICE, CONSOLE_TARGET_SCRCPY


def build_routing_request(
    *,
    device_serial: str,
    enable_audio: bool,
    enable_video: bool,
    video_bitrate: int,
    max_size: str,
    lock_ori_index: int,
    show_fps: bool,
    stay_awake: bool,
    turn_screen_off: bool,
    audio_port: int = DEFAULT_AUDIO_PORT,
) -> RoutingRequest:
    return RoutingRequest(
        device_serial=device_serial,
        enable_audio=enable_audio,
        enable_video=enable_video,
        video_bitrate=video_bitrate,
        max_size=max_size,
        lock_ori_index=lock_ori_index,
        show_fps=show_fps,
        stay_awake=stay_awake,
        turn_screen_off=turn_screen_off,
        audio_port=audio_port,
    )


def build_recording_request(
    *,
    device_serial: str,
    save_path: str,
    record_video: bool,
    record_audio: bool,
    record_ori_index: int,
) -> RecordingRequest:
    return RecordingRequest(
        device_serial=device_serial,
        save_path=save_path,
        bg_mode=True,
        record_video=record_video,
        record_audio=record_audio,
        record_ori_index=record_ori_index,
    )


def build_browse_files_request(device_serial: str, remote_path: str) -> BrowseFilesRequest:
    return BrowseFilesRequest(device_serial=device_serial, remote_path=remote_path)


def build_console_command_request(command_str: str, selected_target: str) -> ConsoleCommandRequest:
    target_kind = ConsoleTargetKind.ADB_GLOBAL
    device_serial = ""

    if selected_target == CONSOLE_TARGET_SCRCPY:
        target_kind = ConsoleTargetKind.SCRCPY
    elif selected_target and selected_target != CONSOLE_TARGET_NO_DEVICE:
        target_kind = ConsoleTargetKind.ADB_DEVICE
        device_serial = selected_target

    return ConsoleCommandRequest(
        command_str=command_str,
        target_kind=target_kind,
        device_serial=device_serial,
    )


def build_push_file_request(
    *,
    device_serial: str,
    local_path: str,
    remote_dir: str,
    rename_to: str | None = None,
) -> PushFileRequest:
    return PushFileRequest(
        device_serial=device_serial,
        local_path=local_path,
        remote_dir=ensure_trailing_slash(remote_dir),
        rename_to=rename_to,
    )


def build_pull_file_request(
    *,
    device_serial: str,
    remote_path: str,
    local_dir: str,
    rename_to: str | None = None,
) -> PullFileRequest:
    return PullFileRequest(
        device_serial=device_serial,
        remote_path=remote_path,
        local_dir=local_dir,
        rename_to=rename_to,
    )
