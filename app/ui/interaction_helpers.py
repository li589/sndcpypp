from collections.abc import Callable, Iterable
from datetime import datetime
from typing import Literal

from PyQt6.QtCore import QTimer
from PyQt6.QtWidgets import QPushButton


def cooldown_buttons(
    buttons: Iterable[QPushButton | None],
    ms: int = 900,
    restore_callback: Callable[[], None] | None = None,
) -> None:
    valid_buttons = [button for button in buttons if button is not None]
    for button in valid_buttons:
        button.setEnabled(False)

    def _restore() -> None:
        if restore_callback is not None:
            restore_callback()
            return
        for button in valid_buttons:
            button.setEnabled(True)

    QTimer.singleShot(ms, _restore)


def ensure_trailing_slash(path: str) -> str:
    normalized = (path or "").strip() or "/"
    if normalized == "/":
        return normalized
    return normalized if normalized.endswith("/") else f"{normalized}/"


def parent_remote_path(path: str) -> str:
    normalized = ensure_trailing_slash(path)
    if normalized == "/":
        return "/"
    trimmed = normalized.rstrip("/")
    last_slash = trimmed.rfind("/")
    if last_slash > 0:
        return f"{trimmed[:last_slash]}/"
    return "/"


def join_remote_path(base_path: str, name: str, is_dir: bool = False) -> str:
    joined = f"{ensure_trailing_slash(base_path)}{name}"
    return f"{joined}/" if is_dir else joined


def build_recording_filename(device_serial: str, file_ext: str, filename_input: str) -> str:
    normalized_input = (filename_input or "").strip()
    if not normalized_input:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        return f"record_{device_serial}_{timestamp}{file_ext}"
    if normalized_input.endswith(file_ext):
        return normalized_input
    return f"{normalized_input}{file_ext}"


def allocate_available_name(target_name: str, exists: Callable[[str], bool]) -> str:
    base, ext = _split_name(target_name)
    counter = 1
    while counter <= 9999:
        candidate = f"{base} ({counter}){ext}"
        if not exists(candidate):
            return candidate
        counter += 1
    # 超过上限时回退到原始名称，由调用方处理冲突
    return target_name


def resolve_conflict_choice(
    target_name: str,
    choice: int,
    exists: Callable[[str], bool],
) -> tuple[Literal["overwrite", "rename", "skip"], str | None]:
    if choice == 1:
        return "overwrite", None
    if choice == 2:
        return "rename", allocate_available_name(target_name, exists)
    return "skip", None


def recording_audio_conflict_message() -> str:
    return (
        "检测到当前设备的音频路由正在运行。\n\n"
        "由于 Android 系统限制，录制音频需要独占音频焦点。\n"
        "继续操作将自动暂停音频路由，录制结束后尝试恢复。\n\n"
        "是否继续？"
    )


def overwrite_file_message(filename: str) -> str:
    return f"文件\n{filename}\n已存在，是否覆盖旧文件？"


def player_exit_message(device_serial: str) -> str:
    return f"设备 {device_serial} 的音频播放器进程已意外终止，是否重新启动音频路由?"


def _split_name(target_name: str) -> tuple[str, str]:
    dot_index = target_name.rfind(".")
    if dot_index <= 0:
        return target_name, ""
    return target_name[:dot_index], target_name[dot_index:]
