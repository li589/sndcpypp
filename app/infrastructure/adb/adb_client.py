import os
import subprocess
import threading
from typing import Callable, List, Optional


class ADBClient:
    def __init__(self, log_callback: Callable[[str, str], None]):
        self._log_callback = log_callback
        self._command_lock = threading.Lock()

    def run_logged(self, command: List[str], description: str = "", cwd: str = None) -> Optional[subprocess.CompletedProcess]:
        if not command:
            return None
        resolved_cwd = cwd
        if not resolved_cwd and command[0]:
            executable_path = os.path.abspath(command[0])
            if os.path.isfile(executable_path):
                resolved_cwd = os.path.dirname(executable_path)
        cmd_str = self._format_command_for_log(command)
        command_label = description.strip() or "执行命令"
        self._log_callback(f"{command_label}: {cmd_str}", "command")
        try:
            flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
            with self._command_lock:
                result = subprocess.run(
                    command,
                    cwd=resolved_cwd,
                    capture_output=True,
                    text=True,
                    timeout=15,
                    creationflags=flags,
                    encoding="utf-8",
                    errors="replace",
                )
            if result.stdout and self._should_log_output(command, description, stream_name="stdout"):
                self._log_callback(self._truncate_for_log(result.stdout.strip()), "output")
            if result.stderr and self._should_log_output(command, description, stream_name="stderr"):
                self._log_callback(self._truncate_for_log(result.stderr.strip()), "error")
            return result
        except subprocess.TimeoutExpired:
            self._log_callback(f"[{description}] 执行超时 (15s)", "error")
        except Exception as exc:
            self._log_callback(f"[{description}] 执行失败: {str(exc)}", "error")
        return None

    def _format_command_for_log(self, command: List[str]) -> str:
        if not command:
            return ""

        formatted_parts: list[str] = []
        for index, part in enumerate(command):
            display_part = os.path.basename(part) if index == 0 else part
            if any(char.isspace() for char in display_part):
                display_part = f'"{display_part}"'
            formatted_parts.append(display_part)
        return " ".join(formatted_parts)

    def _should_log_output(self, command: List[str], description: str, stream_name: str) -> bool:
        if not command:
            return False

        lowered_description = (description or "").lower()
        normalized_command = [part.lower() for part in command]
        is_adb_devices = "devices" in normalized_command and os.path.basename(command[0]).lower().startswith("adb")

        if is_adb_devices and (
            "刷新设备列表" in description
            or "重试刷新设备列表" in description
            or "延迟重试刷新设备列表" in description
        ):
            return False

        if stream_name == "stderr" and is_adb_devices and "start-server" not in lowered_description:
            return False

        return True

    def _truncate_for_log(self, message: str, limit: int = 1200) -> str:
        if len(message) <= limit:
            return message
        return f"{message[:limit]}...(输出过长，已截断)"
