import os
import shutil
import subprocess
import time
from typing import Callable, Optional

from PyQt6.QtCore import QObject, pyqtSignal


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
        self._last_device_snapshot: tuple[str, ...] | None = None

    def validate_paths(self):
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

            if sndcpy_dir and os.path.isdir(sndcpy_dir):
                ext = ".exe" if os.name == "nt" else ""
                scrcpy_path = os.path.join(sndcpy_dir, f"scrcpy{ext}")
                apk_path = os.path.join(sndcpy_dir, "sndcpy.apk")
                if is_exe(scrcpy_path) and os.path.isfile(apk_path):
                    results[2] = 1
                    self._cmd_manager.update_variable("scrcpy_path", scrcpy_path)
                    self._cmd_manager.update_variable("apk_path", apk_path)
                else:
                    self.log_message.emit("在目录中未找到 sndcpy.apk 或 scrcpy 核心文件", "error")
            else:
                self.log_message.emit("Sndcpy 目录无效", "error")

            self.validation_result.emit(results)

        self._task_runner.start(name="adb-validate-paths", group="adb", target=_validate)

    def refresh_devices(self):
        if self._is_refreshing:
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
                if result is None:
                    self.devices_updated.emit([])
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
                        devices = [line.split("\t")[0] for line in result.stdout.splitlines()[1:] if line.strip() and "device" in line]
                        if devices:
                            break
                self._emit_device_summary(devices)
                self.devices_updated.emit(devices)
            except Exception as exc:
                self.log_message.emit(f"刷新设备列表异常: {str(exc)}", "error")
            finally:
                self._is_refreshing = False

        self._task_runner.start(name="adb-refresh-devices", group="adb", target=_refresh)

    def install_apk(self, device_serial: str):
        def _install():
            try:
                cmd = self._cmd_manager.get_target_cmd("install_apk_direct_install_cmd", device_serial=device_serial)
                res = self._run_adb_command(cmd, f"直接安装APK ({device_serial})")
                if res and ("Failure" in res.stdout or "Error" in res.stdout):
                    self.log_message.emit("尝试卸载旧版本并重新安装...", "warning")
                    self._run_adb_command(self._cmd_manager.get_target_cmd("uninstall_apk_cmd", device_serial=device_serial), "卸载旧版本")
                    res = self._run_adb_command(
                        self._cmd_manager.get_target_cmd("install_apk_install_cmd", device_serial=device_serial),
                        "重新安装APK",
                    )
                success = res is not None and "Success" in res.stdout
                self.operation_completed.emit("install", success)
            except Exception as exc:
                self.log_message.emit(f"安装过程出错: {str(exc)}", "error")
                self.operation_completed.emit("install", False)

        self._task_runner.start(name="adb-install-apk", group="adb", target=_install)

    def force_kill_adb(self):
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

    def start_adb_server(self):
        def _start():
            self.log_message.emit("正在唤起 ADB 并枚举设备...", "info")
            self.refresh_devices()

        self._task_runner.start(name="adb-start-server", group="adb", target=_start)

    def restart_adb(self):
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
