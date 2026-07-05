import os
import shutil
from typing import Any

from PyQt6.QtWidgets import QCheckBox, QComboBox, QLineEdit

from app.domain.models.operation_requests import RuntimeConfigurationRequest
from app.infrastructure.adb.path_resolver import ResolvedADBPath, get_platform_vendor_subdir


def get_audio_router_candidate_paths(app_base_dir: str) -> list[str]:
    ext = ".exe" if os.name == "nt" else ""
    repo_root = os.path.abspath(app_base_dir)
    platform_subdir = get_platform_vendor_subdir()
    ci_artifact_name = {
        "windows": "AudioRouter-windows-x64.exe",
        "macos": "AudioRouter-macos-universal",
        "linux": "AudioRouter-linux-x64",
    }.get(platform_subdir, f"AudioRouter{ext}")
    candidates = [
        os.path.join(repo_root, "vendor", platform_subdir, f"AudioRouter{ext}"),
        os.path.join(repo_root, "vendor", platform_subdir, ci_artifact_name),
        os.path.join(repo_root, "AudioRouter", f"AudioRouter{ext}"),
        os.path.join(repo_root, "AudioRouter", "build", f"AudioRouter{ext}"),
        os.path.join(repo_root, "AudioRouter", "build", "Release", f"AudioRouter{ext}"),
        os.path.join(repo_root, "AudioRouter", "build", "Debug", f"AudioRouter{ext}"),
        os.path.join(repo_root, "AudioRouter", "cmake-build-release", f"AudioRouter{ext}"),
        os.path.join(repo_root, "AudioRouter", "cmake-build-debug", f"AudioRouter{ext}"),
        os.path.join(repo_root, "AudioRouter", "out", "build", "x64-Release", f"AudioRouter{ext}"),
        os.path.join(repo_root, "AudioRouter", "out", "build", "x64-Debug", f"AudioRouter{ext}"),
        os.path.join(repo_root, "AudioRouter", "x64", "Release", f"AudioRouter{ext}"),
        os.path.join(repo_root, "AudioRouter", "x64", "Debug", f"AudioRouter{ext}"),
    ]
    return [os.path.abspath(candidate) for candidate in candidates]


def get_audio_router_recommended_args() -> str:
    return "-Idummy --demux rawaud --network-caching=200 --play-and-exit"


def is_audio_router_path(player_path: str) -> bool:
    if not player_path:
        return False
    basename = os.path.basename(player_path).lower()
    return basename == "audiorouter" or basename == "audiorouter.exe" or basename.startswith("audiorouter-")


def get_default_player_path(app_base_dir: str) -> str:
    ext = ".exe" if os.name == "nt" else ""
    candidate_paths: list[str] = []

    # AudioRouter is preferred (native C++ backend, VLC-compatible CLI)
    candidate_paths.extend(get_audio_router_candidate_paths(app_base_dir))

    # VLC as fallback
    for name in [f"vlc{ext}", "vlc"]:
        resolved = shutil.which(name)
        if resolved:
            candidate_paths.append(resolved)

    if os.name == "nt":
        program_files_dirs = [
            os.environ.get("ProgramFiles", ""),
            os.environ.get("ProgramFiles(x86)", ""),
            os.path.join(os.environ.get("LOCALAPPDATA", ""), "Programs"),
        ]
        for base_dir in program_files_dirs:
            if not base_dir:
                continue
            candidate_paths.append(os.path.join(base_dir, "VideoLAN", "VLC", "vlc.exe"))

    candidate_paths.append(os.path.join(app_base_dir, "RouteAudio", f"AudioExt{ext}"))

    for candidate in candidate_paths:
        if candidate and os.path.isfile(candidate):
            return os.path.abspath(candidate)

    return ""


def get_default_sndcpy_dir(app_base_dir: str) -> str:
    """返回当前平台 vendor 子目录的绝对路径。

    语义说明：变量名沿用 `sndcpy_dir` 是历史包袱，实际指向 scrcpy/adb
    等二进制所在目录（不再包含 sndcpy.apk，apk 单独放在 vendor/ 顶层）。
    """
    subdir = get_platform_vendor_subdir()
    return os.path.abspath(os.path.join(app_base_dir, "vendor", subdir))


def get_default_apk_path(app_base_dir: str) -> str:
    """返回 sndcpy.apk 的默认路径（vendor/sndcpy.apk，与平台无关）。"""
    return os.path.abspath(os.path.join(app_base_dir, "vendor", "sndcpy.apk"))


def resolve_runtime_paths(
    adb_path_text: str,
    player_path_text: str,
    sndcpy_dir_text: str,
    *,
    adb_path_resolver,
    app_base_dir: str,
) -> tuple[ResolvedADBPath, str, str]:
    sndcpy_dir = sndcpy_dir_text.strip() or get_default_sndcpy_dir(app_base_dir)
    player_path = player_path_text.strip() or get_default_player_path(app_base_dir)
    adb_resolution = adb_path_resolver.resolve(adb_path_text.strip(), sndcpy_dir)
    return adb_resolution, player_path, sndcpy_dir


def build_runtime_configuration_request(
    settings: dict[str, Any],
    adb_resolution: ResolvedADBPath,
    player_path: str,
    sndcpy_dir: str,
) -> RuntimeConfigurationRequest:
    return RuntimeConfigurationRequest(
        adb_path=adb_resolution.path,
        player_path=player_path,
        sndcpy_dir=sndcpy_dir,
        adb_extra=str(settings.get("adb_extra", "")),
        player_extra=str(settings.get("player_extra", "")),
        scrcpy_extra=str(settings.get("scrcpy_extra", "")),
    )


def collect_ui_settings(window, settings: dict[str, Any]) -> dict[str, Any]:
    return {
        "adb_path": window.adb_path_edit.text().strip(),
        "player_path": window.player_path_edit.text().strip(),
        "sndcpy_dir": window.sndcpy_dir_edit.text().strip(),
        "video_enabled": window.video_check.isChecked(),
        "audio_enabled": window.audio_check.isChecked(),
        "show_fps": getattr(window, "fps_check", QCheckBox()).isChecked(),
        "stay_awake": getattr(window, "stay_awake_check", QCheckBox()).isChecked(),
        "turn_screen_off": getattr(window, "screen_off_check", QCheckBox()).isChecked(),
        "video_bitrate": window.video_bitrate.value(),
        "audio_bitrate": window.audio_bitrate.value(),
        "max_size": window.max_size_combo.currentText(),
        "lock_ori": window.lock_ori_combo.currentIndex(),
        "rec_ori": getattr(window, "rec_ori_combo", QComboBox()).currentIndex(),
        "rec_bg_mode": True,
        "adb_extra": settings.get("adb_extra", ""),
        "player_extra": settings.get("player_extra", ""),
        "scrcpy_extra": settings.get("scrcpy_extra", ""),
        "record_dir": getattr(window, "record_dir_edit", QLineEdit()).text().strip() or os.path.abspath("."),
        "download_dir": getattr(window, "local_down_edit", QLineEdit()).text().strip() or os.path.abspath("."),
    }


def apply_ui_settings(window, settings: dict[str, Any]) -> None:
    window.adb_path_edit.setText(settings.get("adb_path", ""))
    window.player_path_edit.setText(settings.get("player_path", ""))
    window.sndcpy_dir_edit.setText(settings.get("sndcpy_dir", ""))
    window.video_check.setChecked(settings.get("video_enabled", True))
    window.audio_check.setChecked(settings.get("audio_enabled", True))

    if hasattr(window, "fps_check"):
        window.fps_check.setChecked(settings.get("show_fps", False))
    if hasattr(window, "stay_awake_check"):
        window.stay_awake_check.setChecked(settings.get("stay_awake", True))
    if hasattr(window, "screen_off_check"):
        window.screen_off_check.setChecked(settings.get("turn_screen_off", True))

    window.video_bitrate.setValue(settings.get("video_bitrate", 8000))
    window.audio_bitrate.setValue(settings.get("audio_bitrate", 192))

    idx = window.max_size_combo.findText(str(settings.get("max_size", "原始")))
    if idx >= 0:
        window.max_size_combo.setCurrentIndex(idx)
    window.lock_ori_combo.setCurrentIndex(int(settings.get("lock_ori", 0)))

    if hasattr(window, "record_dir_edit"):
        window.record_dir_edit.setText(settings.get("record_dir", os.path.abspath(".")))
    if hasattr(window, "rec_ori_combo"):
        window.rec_ori_combo.setCurrentIndex(int(settings.get("rec_ori", 0)))
    if hasattr(window, "rec_bg_check"):
        window.rec_bg_check.setChecked(True)
    if hasattr(window, "local_down_edit"):
        window.local_down_edit.setText(settings.get("download_dir", os.path.abspath(".")))
