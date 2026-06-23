import os
import shlex
import subprocess

from PyQt6.QtCore import QObject, pyqtSignal


class DebugCommandService(QObject):
    log_message = pyqtSignal(str, str)

    def __init__(self, cmd_manager, adb_client, task_runner):
        super().__init__()
        self._cmd_manager = cmd_manager
        self._adb_client = adb_client
        self._task_runner = task_runner

    def execute_custom_cmd(self, device_serial: str, command_str: str, cmd_type: str = "adb"):
        def _run():
            if cmd_type == "adb":
                adb_path = self._cmd_manager.get_variable("adb_path") or "adb"
                adb_extra = self._cmd_manager.get_variable("adb_extra")
                full_command = [adb_path]
                if adb_extra.strip():
                    full_command.extend(shlex.split(adb_extra))
                if device_serial.strip():
                    full_command.extend(["-s", device_serial])
                full_command.extend(shlex.split(command_str))
                self._adb_client.run_logged(full_command, "自定义命令")
                return

            if cmd_type == "scrcpy":
                scrcpy_path = self._cmd_manager.get_variable("scrcpy_path")
                sndcpy_dir = self._cmd_manager.get_variable("sndcpy_dir")
                full_command = shlex.split(command_str)

                if full_command:
                    if full_command[0] in ["scrcpy", "scrcpy.exe"]:
                        full_command[0] = scrcpy_path
                    else:
                        full_command.insert(0, scrcpy_path)
                else:
                    return

                cwd = sndcpy_dir if sndcpy_dir and os.path.isdir(sndcpy_dir) else None
                self._adb_client.run_logged(full_command, f"[{cmd_type}命令]", cwd=cwd)

        self._task_runner.start(name="debug-custom-command", group="debug", target=_run)
