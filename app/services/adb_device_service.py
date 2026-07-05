import os
import shlex
import shutil
import subprocess
import time
from typing import Callable, Optional

from PyQt6.QtCore import QObject, pyqtSignal
from app.infrastructure.config.logging_config import get_logger
from app.infrastructure.adb.path_resolver import resolve_apk_path

logger = get_logger(__name__)


def _report_debug_event(hypothesis_id: str, location: str, msg: str, data: dict | None = None) -> None:
    del hypothesis_id, location, msg, data


class ADBDeviceService(QObject):
    devices_updated = pyqtSignal(list)
    operation_completed = pyqtSignal(str, bool)
    validation_result = pyqtSignal(list)
    log_message = pyqtSignal(str, str)

    def __init__(self, cmd_manager, run_adb_command: Callable[[list[str], str], Optional[subprocess.CompletedProcess]], task_runner):
        super().__init__()
        self._cmd_manager = cmd_manager
        self._run_adb_command = run_adb_command
        self._task_runner = task_runner
        self._is_refreshing = False
        self._refresh_pending = False
        self._last_device_snapshot: tuple[str, ...] | None = None
        self._sndcpy_package = "com.rom1v.sndcpy"

    def validate_paths(self) -> None:
        def _validate():
            results = [0, 0, 0]
            adb_path = self._cmd_manager.get_variable("adb_path")
            player_path = self._cmd_manager.get_variable("player_path")
            sndcpy_dir = self._cmd_manager.get_variable("sndcpy_dir")

            def is_exe(path_str):
                if not path_str:
                    return False
                if os.path.isfile(path_str) and os.access(path_str, os.X_OK):
                    return True
                if shutil.which(path_str):
                    return True
                if os.name == "nt" and os.path.isfile(path_str):
                    return True
                return False

            if is_exe(adb_path):
                results[0] = 1
                self.log_message.emit(f"ADB 就绪: {adb_path}", "success")
            else:
                self.log_message.emit(f"ADB 未找到: {adb_path}", "error")

            if is_exe(player_path):
                results[1] = 1
                self.log_message.emit(f"播放器 就绪: {player_path}", "success")
            else:
                self.log_message.emit(f"播放器 未找到: {player_path}", "error")

            self._clear_runtime_paths()
            if sndcpy_dir and os.path.isdir(sndcpy_dir):
                ext = ".exe" if os.name == "nt" else ""
                scrcpy_path = os.path.join(sndcpy_dir, f"scrcpy{ext}")
                apk_path = resolve_apk_path(sndcpy_dir, os.path.abspath("."))
                if is_exe(scrcpy_path) and os.path.isfile(apk_path):
                    results[2] = 1
                    self._cmd_manager.update_variable("scrcpy_path", scrcpy_path)
                    self._cmd_manager.update_variable("apk_path", apk_path)
                else:
                    self.log_message.emit("在目录中未找到 sndcpy.apk 或 scrcpy 核心文件", "error")
            else:
                self.log_message.emit("vendor 目录无效", "error")

            self.validation_result.emit(results)

        self._task_runner.start(name="adb-validate-paths", group="adb", target=_validate)

    def refresh_devices(self) -> None:
        if self._is_refreshing:
            self._refresh_pending = True
            return
        self._is_refreshing = True

        def _refresh():
            try:
                cmd = self._cmd_manager.get_target_cmd("refresh_devices_cmd")
                result = self._run_adb_command(cmd, "刷新设备列表")
                if result is None or result.returncode != 0:
                    self.log_message.emit("设备刷新失败，等待后直接重试设备枚举...", "warning")
                    time.sleep(1.5)
                    result = self._run_adb_command(cmd, "重试刷新设备列表")
                if result is None or result.returncode != 0:
                    self.log_message.emit("设备刷新失败，本次结果已忽略。", "error")
                    return
                devices = [line.split("\t")[0] for line in result.stdout.splitlines()[1:] if line.strip() and "device" in line]
                stderr_text = result.stderr or ""
                if not devices and ("daemon started successfully" in stderr_text or "daemon not running" in stderr_text):
                    self.log_message.emit("ADB 刚启动完成，等待设备枚举后自动重试...", "warning")
                    for retry_index in range(2):
                        time.sleep(1.0)
                        result = self._run_adb_command(cmd, f"延迟重试刷新设备列表 #{retry_index + 1}")
                        if result is None:
                            continue
                        if result.returncode != 0:
                            continue
                        devices = [line.split("\t")[0] for line in result.stdout.splitlines()[1:] if line.strip() and "device" in line]
                        if devices:
                            break
                self._emit_device_summary(devices)
                self.devices_updated.emit(devices)
            except Exception as exc:
                self.log_message.emit(f"刷新设备列表异常: {str(exc)}", "error")
            finally:
                self._is_refreshing = False
                if self._refresh_pending:
                    self._refresh_pending = False
                    self.refresh_devices()

        self._task_runner.start(name="adb-refresh-devices", group="adb", target=_refresh)

    def install_apk(self, device_serial: str) -> None:
        def _install():
            try:
                was_installed_before = self._is_sndcpy_installed(device_serial)
                cmd = self._cmd_manager.get_target_cmd("install_apk_direct_install_cmd", device_serial=device_serial)
                # #region debug-point B:install-command
                _report_debug_event(
                    "B",
                    "adb_device_service.install_apk",
                    "[DEBUG] install task started",
                    {
                        "device_serial": device_serial,
                        "cmd": cmd,
                        "apk_path": self._cmd_manager.get_variable("apk_path"),
                        "was_installed_before": was_installed_before,
                    },
                )
                # #endregion
                res = self._run_adb_command(cmd, f"直接安装APK ({device_serial})")
                if self._should_retry_install(res):
                    # #region debug-point B:install-retry
                    _report_debug_event(
                        "B",
                        "adb_device_service.install_apk",
                        "[DEBUG] install retry requested",
                        {
                            "device_serial": device_serial,
                            "returncode": None if res is None else res.returncode,
                            "result_text": self._result_text(res),
                        },
                    )
                    # #endregion
                    self.log_message.emit("尝试卸载旧版本并重新安装...", "warning")
                    self._run_adb_command(self._cmd_manager.get_target_cmd("uninstall_apk_cmd", device_serial=device_serial), "卸载旧版本")
                    res = self._run_adb_command(
                        self._cmd_manager.get_target_cmd("install_apk_install_cmd", device_serial=device_serial),
                        "重新安装APK",
                    )
                success = self._install_succeeded(res)
                if not success and self._install_indicates_existing_package(res):
                    success = was_installed_before or self._is_sndcpy_installed(device_serial)
                    if success:
                        self.log_message.emit("设备中已存在 sndcpy，跳过重复安装。", "info")
                if not success and not was_installed_before and self._should_wait_for_install_confirmation(res):
                    self.log_message.emit("安装结果尚未明确，正在等待手机端确认安装...", "info")
                    success = self._wait_for_sndcpy_install(device_serial)
                # #region debug-point B:install-finished
                _report_debug_event(
                    "B",
                    "adb_device_service.install_apk",
                    "[DEBUG] install task finished",
                    {
                        "device_serial": device_serial,
                        "success": success,
                        "returncode": None if res is None else res.returncode,
                        "result_text": self._result_text(res),
                    },
                )
                # #endregion
                if not success:
                    error_text = self._result_text(res) or "未获取到ADB返回结果"
                    self.log_message.emit(f"APK安装失败: {error_text}", "error")
                self.operation_completed.emit("install", success)
            except Exception as exc:
                self.log_message.emit(f"安装过程出错: {str(exc)}", "error")
                self.operation_completed.emit("install", False)

        self._task_runner.start(name="adb-install-apk", group="adb", target=_install)

    def force_kill_adb(self) -> None:
        def _kill():
            self.log_message.emit("正在强制结束 ADB 进程池...", "warning")
            try:
                flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
                if os.name == "nt":
                    res = subprocess.run(
                        ["taskkill", "/F", "/IM", "adb.exe"],
                        capture_output=True,
                        text=True,
                        creationflags=flags,
                        encoding="utf-8",
                        errors="replace",
                    )
                else:
                    res = subprocess.run(["pkill", "-f", "adb"], capture_output=True, text=True, encoding="utf-8", errors="replace")

                if "拒绝访问" in res.stderr or "Access is denied" in res.stderr:
                    self.log_message.emit("结束失败：拒绝访问！请【以管理员身份运行本程序】。", "error")
                else:
                    self.log_message.emit("ADB 进程清理指令执行完毕。", "success")
            except Exception as exc:
                self.log_message.emit(f"强杀过程异常: {str(exc)}", "error")

        self._task_runner.start(name="adb-force-kill", group="adb", target=_kill)

    def start_adb_server(self) -> None:
        def _start():
            self.log_message.emit("正在唤起 ADB 并枚举设备...", "info")
            self.refresh_devices()

        self._task_runner.start(name="adb-start-server", group="adb", target=_start)

    def restart_adb(self) -> None:
        def _restart():
            self._run_adb_command(self._cmd_manager.get_target_cmd("restart_adb_kill_cmd"), "杀掉ADB")
            time.sleep(1.0)
            self.log_message.emit("ADB服务重启指令已发送，正在重新枚举设备", "success")
            self.refresh_devices()

        self._task_runner.start(name="adb-restart-server", group="adb", target=_restart)

    def _emit_device_summary(self, devices: list[str]) -> None:
        snapshot = tuple(devices)
        if snapshot == self._last_device_snapshot:
            return

        self._last_device_snapshot = snapshot
        if devices:
            self.log_message.emit(f"设备枚举完成: 检测到 {len(devices)} 台在线设备", "success")
        else:
            self.log_message.emit("设备枚举完成: 当前没有在线设备", "info")

    def _clear_runtime_paths(self) -> None:
        self._cmd_manager.update_variable("scrcpy_path", "")
        self._cmd_manager.update_variable("apk_path", "")

    def _build_adb_shell_cmd(self, device_serial: str, *shell_args: str) -> list[str]:
        cmd = [self._cmd_manager.get_variable("adb_path")]
        adb_extra = self._cmd_manager.get_variable("adb_extra")
        if adb_extra.strip():
            cmd.extend(shlex.split(adb_extra))
        cmd.extend(["-s", device_serial, "shell", *shell_args])
        return cmd

    def _is_sndcpy_installed(self, device_serial: str) -> bool:
        result = self._run_adb_command(
            self._build_adb_shell_cmd(device_serial, "pm", "path", self._sndcpy_package),
            f"检查 sndcpy 安装状态 ({device_serial})",
        )
        if result is None or result.returncode != 0:
            return False
        return "package:" in (result.stdout or "").lower()

    def _wait_for_sndcpy_install(
        self,
        device_serial: str,
        timeout_seconds: float = 15.0,
        interval_seconds: float = 1.0,
    ) -> bool:
        deadline = time.time() + timeout_seconds
        while time.time() < deadline:
            if self._is_sndcpy_installed(device_serial):
                return True
            time.sleep(interval_seconds)
        return self._is_sndcpy_installed(device_serial)

    @staticmethod
    def _result_text(result: Optional[subprocess.CompletedProcess]) -> str:
        if result is None:
            return ""
        stdout = (result.stdout or "").strip()
        stderr = (result.stderr or "").strip()
        return "\n".join(part for part in (stdout, stderr) if part)

    @classmethod
    def _install_succeeded(cls, result: Optional[subprocess.CompletedProcess]) -> bool:
        if result is None:
            return False
        output = cls._result_text(result).lower()
        if result.returncode == 0 and (
            "success" in output
            or "successfully" in output
            or output == ""
        ):
            return True
        return False

    @classmethod
    def _install_indicates_existing_package(cls, result: Optional[subprocess.CompletedProcess]) -> bool:
        output = cls._result_text(result).lower()
        return any(token in output for token in ("already exists", "install_failed_already_exists", "already installed"))

    @classmethod
    def _should_wait_for_install_confirmation(cls, result: Optional[subprocess.CompletedProcess]) -> bool:
        if result is None:
            return False
        output = cls._result_text(result).lower()
        if cls._install_succeeded(result) or cls._install_indicates_existing_package(result):
            return False
        definitive_failures = (
            "adb: error:",
            "device offline",
            "no devices/emulators found",
            "more than one device",
            "permission denied",
            "failed to stat",
        )
        if any(token in output for token in definitive_failures):
            return False
        return result.returncode != 0 or "performing streamed install" in output

    @classmethod
    def _should_retry_install(cls, result: Optional[subprocess.CompletedProcess]) -> bool:
        if result is None or cls._install_succeeded(result):
            return False
        output = cls._result_text(result).lower()
        return any(
            token in output
            for token in (
                "install_failed_update_incompatible",
                "install_failed_version_downgrade",
                "version downgrade",
            )
        )
