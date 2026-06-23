import json
import os
from datetime import datetime
from typing import Any


def get_default_settings_path(app_name: str = "sndcpypp") -> str:
    if os.name == "nt":
        base_dir = os.environ.get("APPDATA") or os.environ.get("LOCALAPPDATA")
        if base_dir:
            return os.path.join(base_dir, app_name, "settings.json")

    home_dir = os.path.expanduser("~")
    if home_dir and home_dir != "~":
        return os.path.join(home_dir, f".{app_name}", "settings.json")

    return os.path.join(os.path.abspath("."), "settings.json")


class JsonSettingsStore:
    def __init__(self, file_path: str):
        self.file_path = file_path
        self.last_load_warning: str | None = None

    def build_defaults(self) -> dict[str, Any]:
        base_dir = os.path.abspath(".")
        return {
            "adb_path": "",
            "player_path": "",
            "sndcpy_dir": "",
            "video_enabled": True,
            "audio_enabled": True,
            "show_fps": False,
            "stay_awake": True,
            "turn_screen_off": True,
            "video_bitrate": 8000,
            "audio_bitrate": 192,
            "max_size": "原始",
            "lock_ori": 0,
            "rec_ori": 0,
            "rec_bg_mode": True,
            "adb_extra": "",
            "player_extra": "",
            "scrcpy_extra": "",
            "record_dir": base_dir,
            "download_dir": base_dir,
        }

    def load(self) -> dict[str, Any]:
        self.last_load_warning = None
        settings = self.build_defaults()
        if os.path.exists(self.file_path):
            try:
                with open(self.file_path, "r", encoding="utf-8") as file:
                    loaded_settings = json.load(file)
                if not isinstance(loaded_settings, dict):
                    raise ValueError("设置文件根节点必须是 JSON 对象")
                settings.update(loaded_settings)
            except Exception as exc:
                backup_path = self._backup_invalid_file()
                self.last_load_warning = self._build_load_warning(str(exc), backup_path)
        return settings

    def save(self, settings: dict[str, Any]) -> dict[str, Any]:
        directory = os.path.dirname(os.path.abspath(self.file_path))
        if directory:
            os.makedirs(directory, exist_ok=True)
        with open(self.file_path, "w", encoding="utf-8") as file:
            json.dump(settings, file, indent=4)
        return settings

    def _backup_invalid_file(self) -> str | None:
        try:
            directory = os.path.dirname(os.path.abspath(self.file_path)) or os.path.abspath(".")
            file_name = os.path.basename(self.file_path)
            timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
            backup_path = os.path.join(directory, f"{file_name}.broken-{timestamp}")
            os.replace(self.file_path, backup_path)
            return backup_path
        except Exception:
            return None

    def _build_load_warning(self, error_text: str, backup_path: str | None) -> str:
        if backup_path:
            return f"设置文件损坏，已回退默认配置并备份到: {backup_path} | 原因: {error_text}"
        return f"设置文件损坏，已回退默认配置，但备份失败 | 原因: {error_text}"
