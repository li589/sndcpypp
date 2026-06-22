import os
import shlex
from typing import Any, Dict, List

from PyQt6.QtCore import QObject, pyqtSignal


class ADBCommandBuilder(QObject):
    log_message = pyqtSignal(str, str)

    def __init__(self, path_dict: Dict[str, str]):
        super().__init__()
        ext = ".exe" if os.name == "nt" else ""

        self._variables: Dict[str, str] = {
            "adb_path": f"adb{ext}",
            "player_path": "",
            "sndcpy_dir": "",
            "apk_path": "",
            "scrcpy_path": f"scrcpy{ext}",
            "device_serial": "",
            "port": "28200",
            "audio_bitrate": "192",
            "video_bitrate": "8000",
            "max_size_flag": "",
            "max_size_val": "",
            "lock_ori_flag": "",
            "lock_ori_val": "",
            "fps_flag": "",
            "stay_awake_flag": "",
            "screen_off_flag": "",
            "adb_extra": "",
            "player_extra": "",
            "scrcpy_extra": "",
            "remote_path": "/sdcard/",
            "local_path": "",
        }
        self._variables.update(path_dict)
        self._command_templates: Dict[str, List[str]] = {}
        self.set_default_cmd()

    def set_default_cmd(self):
        self._command_templates = {
            "refresh_devices_cmd": ["{adb_path}", "{adb_extra}", "devices"],
            "install_apk_direct_install_cmd": ["{adb_path}", "{adb_extra}", "-s", "{device_serial}", "install", "-t", "-r", "-g", "{apk_path}"],
            "install_apk_install_cmd": ["{adb_path}", "{adb_extra}", "-s", "{device_serial}", "install", "-t", "-g", "{apk_path}"],
            "uninstall_apk_cmd": ["{adb_path}", "{adb_extra}", "-s", "{device_serial}", "uninstall", "com.rom1v.sndcpy"],
            "start_audio_forward_cmd": ["{adb_path}", "{adb_extra}", "-s", "{device_serial}", "forward", "tcp:{port}", "localabstract:sndcpy"],
            "start_audio_start_cmd": ["{adb_path}", "{adb_extra}", "-s", "{device_serial}", "shell", "am", "start", "com.rom1v.sndcpy/.MainActivity"],
            "start_audio_player_cmd": ["{player_path}", "{player_extra}", "-Idummy", "--demux", "rawaud", "--network-caching=200", "--play-and-exit", "tcp://localhost:{port}"],
            "stop_audio_app_cmd": ["{adb_path}", "{adb_extra}", "-s", "{device_serial}", "shell", "am", "force-stop", "com.rom1v.sndcpy"],
            "remove_audio_forward_cmd": ["{adb_path}", "{adb_extra}", "-s", "{device_serial}", "forward", "--remove", "tcp:{port}"],
            "start_video_scrcpy_cmd": ["{scrcpy_path}", "{scrcpy_extra}", "-s", "{device_serial}", "--video-bit-rate", "{video_bitrate}", "{max_size_flag}", "{max_size_val}", "{lock_ori_flag}", "{lock_ori_val}", "{fps_flag}", "{stay_awake_flag}", "{screen_off_flag}", "--pause-on-exit=if-error"],
            "restart_adb_kill_cmd": ["{adb_path}", "{adb_extra}", "kill-server"],
            "restart_adb_start_cmd": ["{adb_path}", "{adb_extra}", "start-server"],
            "list_files_detailed_cmd": ["{adb_path}", "{adb_extra}", "-s", "{device_serial}", "shell", 'ls -all "{remote_path}"'],
            "list_files_cmd": ["{adb_path}", "{adb_extra}", "-s", "{device_serial}", "shell", 'ls -1F "{remote_path}"'],
            "check_file_type_cmd": ["{adb_path}", "{adb_extra}", "-s", "{device_serial}", "shell", 'file "{remote_path}"'],
            "pull_file_cmd": ["{adb_path}", "{adb_extra}", "-s", "{device_serial}", "pull", "{remote_path}", "{local_path}"],
            "push_file_cmd": ["{adb_path}", "{adb_extra}", "-s", "{device_serial}", "push", "{local_path}", "{remote_path}"],
        }

    def update_variable(self, target_key: str, target_value: Any):
        try:
            self._variables[target_key] = str(target_value)
        except Exception as exc:
            self.log_message.emit(f"更新变量失败: {str(exc)}", "error")

    def get_variable(self, target_key: str) -> str:
        return self._variables.get(target_key, "")

    def get_target_cmd(self, target_key: str, **kwargs) -> List[str]:
        try:
            current_vars = self._variables.copy()
            for k, v in kwargs.items():
                current_vars[k] = str(v)

            template = self._command_templates.get(target_key, [])
            parsed_cmd = []
            for part in template:
                if part in ["{adb_extra}", "{player_extra}", "{scrcpy_extra}"]:
                    resolved = part.format(**current_vars)
                    if resolved.strip():
                        parsed_cmd.extend(shlex.split(resolved))
                else:
                    resolved = part.format(**current_vars)
                    parsed_cmd.append(resolved)

            final_cmd = []
            i = 0
            while i < len(parsed_cmd):
                if parsed_cmd[i] == "-s" and (i + 1 < len(parsed_cmd) and not parsed_cmd[i + 1].strip()):
                    i += 2
                    continue
                if parsed_cmd[i].strip() or parsed_cmd[i] == '""':
                    final_cmd.append("" if parsed_cmd[i] == '""' else parsed_cmd[i])
                i += 1
            return final_cmd
        except Exception as exc:
            self.log_message.emit(f"解析命令失败[{target_key}]: {str(exc)}", "error")
            return []
