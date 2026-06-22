import os
from collections.abc import Callable

from app.ui.interaction_helpers import build_recording_filename
from app.ui.message_templates import status_recording_cancelled
from app.ui.popup_manager import PopupManager


def prepare_recording_start(
    *,
    device_serial: str,
    record_dir: str,
    file_ext: str,
    filename_input: str,
    record_video: bool,
    record_audio: bool,
    is_audio_running: bool,
    popups: PopupManager,
    set_status: Callable[[str], None],
    before_prepare: Callable[[], None] | None = None,
) -> str | None:
    if not record_video and not record_audio:
        popups.show_recording_target_required_warning()
        return None

    if record_audio and is_audio_running:
        if not popups.confirm_recording_audio_conflict():
            set_status(status_recording_cancelled())
            return None

    if before_prepare is not None:
        before_prepare()

    if not os.path.exists(record_dir):
        popups.show_record_directory_invalid()
        return None

    filename = build_recording_filename(device_serial, file_ext, filename_input)
    full_path = os.path.join(record_dir, filename)

    if os.path.exists(full_path):
        if popups.confirm_overwrite_existing_file(filename):
            try:
                os.remove(full_path)
            except Exception as exc:
                popups.show_record_overwrite_failed(str(exc))
                return None
        else:
            set_status(status_recording_cancelled("取消覆盖"))
            return None

    return full_path
