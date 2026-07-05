import os
import shlex

from PyQt6.QtCore import QObject, pyqtSignal

from app.infrastructure.config.logging_config import get_logger

logger = get_logger(__name__)


class DebugCommandService(QObject):
    log_message = pyqtSignal(str, str)

    def __init__(self, cmd_manager, adb_client, task_runner) -> None:
        super().__init__()
        self._cmd_manager = cmd_manager
        self._adb_client = adb_client
        self._task_runner = task_runner

    def execute_custom_cmd(self, device_serial: str, command_str: str, cmd_type: str = "adb") -> None:
        def _run():
            try:
                if cmd_type == "adb":
                    adb_path = self._cmd_manager.get_variable("adb_path") or "adb"
                    adb_extra = self._cmd_manager.get_variable("adb_extra")
                    full_command = [adb_path]
                    if adb_extra.strip():
                        full_command.extend(shlex.split(adb_extra))
                    if device_serial.strip():
                        full_command.extend(["-s", device_serial])
                    full_command.extend(shlex.split(command_str))
                    self._adb_client.run_logged(full_command, "自定义命令", timeout_seconds=None)
                    return

                if cmd_type == "scrcpy":
                    scrcpy_path = self._cmd_manager.get_variable("scrcpy_path")
                    if not scrcpy_path:
                        self.log_message.emit("scrcpy 路径未配置，无法执行 scrcpy 命令", "error")
                        return
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
                    self._adb_client.run_logged(full_command, f"[{cmd_type}命令]", cwd=cwd, timeout_seconds=None)
                    return

                self.log_message.emit(f"未知命令类型: {cmd_type}", "error")
            except ValueError as exc:
                self.log_message.emit(f"命令解析失败: {exc}", "error")

        self._task_runner.start(name="debug-custom-command", group="debug", target=_run)
