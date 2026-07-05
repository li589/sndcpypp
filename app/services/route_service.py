import contextlib
import os
import shlex
import subprocess
import tempfile
import time
from collections.abc import Callable

from PyQt6.QtCore import QObject, pyqtSignal

from app.domain.models.operation_requests import RoutingRequest
from app.infrastructure.config.constants import DEFAULT_AUDIO_PORT
from app.infrastructure.config.logging_config import get_logger
from app.infrastructure.process.process_waiter import wait_for_process_exit
from app.ui.message_templates import (
    log_all_streams_force_stopped,
    log_await_screen_capture_auth,
    log_one_click_serial_video_first,
    log_video_link_stable_starting_audio,
)

logger = get_logger(__name__)


def _report_debug_event(hypothesis_id: str, location: str, msg: str, data: dict | None = None) -> None:
    # Production builds no longer emit HTTP debug events from workspace files.
    del hypothesis_id, location, msg, data


def _report_video_debug_event(hypothesis_id: str, location: str, msg: str, data: dict | None = None) -> None:
    del hypothesis_id, location, msg, data


def _is_audio_router(player_path: str) -> bool:
    if not player_path:
        return False
    basename = os.path.basename(player_path).lower()
    return basename in ("audiorouter", "audiorouter.exe")


class RouteService(QObject):
    log_message = pyqtSignal(str, str)
    operation_completed = pyqtSignal(str, bool)
    player_process_exited = pyqtSignal(str)

    def __init__(
        self,
        cmd_manager,
        process_registry,
        process_supervisor,
        task_runner,
        run_adb_command: Callable[[list[str], str], subprocess.CompletedProcess | None],
        probe_scrcpy_features: Callable[[], dict],
        is_running: Callable[[], bool],
    ) -> None:
        super().__init__()
        self._cmd_manager = cmd_manager
        self._process_registry = process_registry
        self._process_supervisor = process_supervisor
        self._task_runner = task_runner
        self._run_adb_command = run_adb_command
        self._probe_scrcpy_features = probe_scrcpy_features
        self._is_running = is_running

    def _mark_intentional_video_stop(self, device_serial: str) -> None:
        reg = self._process_registry.ensure(device_serial)
        with reg["lock"]:
            stop_markers = reg.setdefault("intentional_video_stop_pids", set())
            for proc in reg.get("video", []):
                stop_markers.add(proc.pid)

    def _wait_until_process_ready(self, proc, seconds: float = 1.0, interval: float = 0.1) -> bool:
        checks = max(1, int(seconds / interval))
        for _ in range(checks):
            if proc.poll() is not None:
                return False
            time.sleep(interval)
        return proc.poll() is None

    def _wait_for_process_exit(
        self,
        proc,
        *,
        poll_interval: float = 0.2,
        shutdown_grace_seconds: float = 3.0,
        on_shutdown_timeout: Callable[[], None] | None = None,
    ) -> int | None:
        return wait_for_process_exit(
            proc,
            is_running=self._is_running,
            poll_interval=poll_interval,
            shutdown_grace_seconds=shutdown_grace_seconds,
            on_shutdown_timeout=on_shutdown_timeout,
        )

    @staticmethod
    def _read_process_output(proc, timeout: float = 0.2) -> dict[str, str]:
        stdout_text = ""
        stderr_text = ""
        if getattr(proc, "stdout", None) is None and getattr(proc, "stderr", None) is None:
            return {"stdout": "", "stderr": ""}
        try:
            stdout_text, stderr_text = proc.communicate(timeout=timeout)
        except subprocess.TimeoutExpired:
            try:
                if getattr(proc, "stdout", None) is not None:
                    stdout_text = proc.stdout.read() or ""
                if getattr(proc, "stderr", None) is not None:
                    stderr_text = proc.stderr.read() or ""
            except Exception:
                pass  # best-effort: stdout/stderr may already be closed
        except Exception:
            pass  # best-effort: process may have already exited
        return {"stdout": (stdout_text or "").strip(), "stderr": (stderr_text or "").strip()}

    @staticmethod
    def _read_debug_file(file_path: str | None) -> str:
        if not file_path:
            return ""
        try:
            with open(file_path, encoding="utf-8", errors="replace") as file:
                return file.read().strip()
        except Exception:
            return ""  # best-effort: debug file may not exist or be readable

    @staticmethod
    def _create_temp_log_path(device_serial: str, stream_name: str) -> str:
        safe_device = "".join(ch if ch.isalnum() or ch in ("-", "_") else "_" for ch in device_serial) or "device"
        fd, path = tempfile.mkstemp(prefix=f"sndcpypp-{safe_device}-", suffix=f".{stream_name}.log")
        os.close(fd)
        return path

    @staticmethod
    def _cleanup_video_debug_logs(proc) -> None:
        for attr_name in ("_debug_stdout_log_path", "_debug_stderr_log_path"):
            log_path = getattr(proc, attr_name, None)
            if not log_path:
                continue
            with contextlib.suppress(OSError):
                os.remove(log_path)
            with contextlib.suppress(AttributeError):
                delattr(proc, attr_name)

    @staticmethod
    def _default_audio_player_args() -> list[str]:
        return ["-Idummy", "--demux", "rawaud", "--network-caching=200", "--play-and-exit"]

    def _build_audio_player_cmd(self, port: int) -> list[str]:
        player_path = self._cmd_manager.get_variable("player_path")
        player_extra = self._cmd_manager.get_variable("player_extra")
        player_args = shlex.split(player_extra) if player_extra.strip() else self._default_audio_player_args()
        if _is_audio_router(player_path) and "-Idummy" not in player_args:
            player_args = ["-Idummy", *player_args]
        return [player_path, *player_args, f"tcp://localhost:{port}"]

    @staticmethod
    def _result_text(result: subprocess.CompletedProcess | None) -> str:
        if result is None:
            return ""
        stdout = (result.stdout or "").strip()
        stderr = (result.stderr or "").strip()
        return "\n".join(part for part in (stdout, stderr) if part)

    def _require_adb_success(
        self,
        result: subprocess.CompletedProcess | None,
        *,
        action_text: str,
        operation: str,
    ) -> bool:
        if result is not None and result.returncode == 0:
            return True
        detail = self._result_text(result) or "未获取到ADB返回结果"
        self.log_message.emit(f"{action_text}失败: {detail}", "error")
        self.operation_completed.emit(operation, False)
        return False

    def _cleanup_stale_scrcpy_processes(self, scrcpy_path: str) -> list[int]:
        # Never scan/kill unrelated user processes. Only registry-tracked children
        # are terminated via ProcessSupervisor.
        del scrcpy_path
        return []

    def _cleanup_audio_player_processes(self, port: str) -> list[int]:
        del port
        return []

    def _ensure_video_adb_server_ready(self, device_serial: str) -> bool:
        result = self._run_adb_command(
            self._cmd_manager.get_target_cmd("restart_adb_start_cmd"),
            f"预热视频ADB服务 ({device_serial})",
        )
        _report_video_debug_event(
            "A",
            "route_service.start_video_route",
            "[DEBUG] video adb start-server result",
            {
                "device_serial": device_serial,
                "returncode": None if result is None else result.returncode,
                "output": self._result_text(result),
            },
        )
        if result is not None and result.returncode == 0:
            return True
        detail = self._result_text(result) or "未获取到ADB返回结果"
        self.log_message.emit(f"视频ADB服务预热失败 ({device_serial}): {detail}", "error")
        self.operation_completed.emit("video_route", False)
        return False

    @staticmethod
    def _parse_max_size_value(max_size: str) -> int | None:
        try:
            return int(str(max_size).strip())
        except (TypeError, ValueError):
            return None

    def _build_video_attempt_plan(
        self,
        bitrate: int,
        max_size: str,
        turn_screen_off: bool,
    ) -> list[dict[str, object]]:
        attempts: list[dict[str, object]] = [
            {
                "bitrate": bitrate,
                "max_size": max_size,
                "turn_screen_off": turn_screen_off,
                "reason": "requested",
            }
        ]
        fallback_bitrate = min(int(bitrate), 4000)
        parsed_max_size = self._parse_max_size_value(max_size)
        if max_size == "原始" or (parsed_max_size is not None and parsed_max_size > 1280):
            fallback_max_size = "1280"
        else:
            fallback_max_size = max_size
        fallback_turn_screen_off = False
        if fallback_bitrate != bitrate or fallback_max_size != max_size or fallback_turn_screen_off != turn_screen_off:
            attempts.append(
                {
                    "bitrate": fallback_bitrate,
                    "max_size": fallback_max_size,
                    "turn_screen_off": fallback_turn_screen_off,
                    "reason": "fallback",
                }
            )
        return attempts

    @staticmethod
    def _should_retry_video_launch(stdout_text: str, stderr_text: str) -> bool:
        combined = "\n".join(part for part in (stdout_text, stderr_text) if part)
        retry_signals = (
            "Server connection failed",
            "Device disconnected",
            "Demuxer error",
            "stream disabled due to connection error",
            "CreateProcessW() error 5",
        )
        return any(signal in combined for signal in retry_signals)

    def _reset_video_adb_server(self, device_serial: str) -> bool:
        self._run_adb_command(
            self._cmd_manager.get_target_cmd("restart_adb_kill_cmd"),
            f"重置视频ADB服务 ({device_serial})",
        )
        return self._ensure_video_adb_server_ready(device_serial)

    def _wait_for_video_renderer(
        self,
        proc,
        device_serial: str,
        timeout: float = 15.0,
        interval: float = 0.2,
        stable_seconds: float = 3.0,
    ) -> bool:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            stdout_text = self._read_debug_file(getattr(proc, "_debug_stdout_log_path", None))
            stderr_text = self._read_debug_file(getattr(proc, "_debug_stderr_log_path", None))
            if "Renderer:" in stdout_text or "Texture:" in stdout_text:
                stable_deadline = time.monotonic() + stable_seconds
                while time.monotonic() < stable_deadline:
                    stderr_text = self._read_debug_file(getattr(proc, "_debug_stderr_log_path", None))
                    if "Server connection failed" in stderr_text or "Device disconnected" in stderr_text:
                        break
                    if proc.poll() is not None:
                        break
                    time.sleep(interval)
                else:
                    _report_video_debug_event(
                        "C",
                        "route_service._start_routing_session_task",
                        "[DEBUG] video renderer remained stable before audio start",
                        {
                            "device_serial": device_serial,
                            "pid": getattr(proc, "pid", None),
                            "stable_seconds": stable_seconds,
                        },
                    )
                    return True
                _report_video_debug_event(
                    "C",
                    "route_service._start_routing_session_task",
                    "[DEBUG] video renderer detected before audio start",
                    {
                        "device_serial": device_serial,
                        "pid": getattr(proc, "pid", None),
                    },
                )
                break
            if "Server connection failed" in stderr_text or "Device disconnected" in stderr_text:
                break
            if proc.poll() is not None:
                break
            time.sleep(interval)
        _report_video_debug_event(
            "C",
            "route_service._start_routing_session_task",
            "[DEBUG] video renderer not detected before audio start",
            {
                "device_serial": device_serial,
                "pid": getattr(proc, "pid", None),
                "stdout": self._read_debug_file(getattr(proc, "_debug_stdout_log_path", None)),
                "stderr": self._read_debug_file(getattr(proc, "_debug_stderr_log_path", None)),
            },
        )
        return False

    def _stop_audio_internal(self, device_serial: str) -> None:
        try:
            reg = self._process_registry.ensure(device_serial)
            with reg["lock"]:
                port = str(reg.get("audio_port") or DEFAULT_AUDIO_PORT)
            self._process_supervisor.kill_group(device_serial, "audio")
            fallback_audio_pids = self._cleanup_audio_player_processes(port)
            if fallback_audio_pids:
                self.log_message.emit(
                    f"已兜底清理本地音频播放器进程 ({device_serial}): {fallback_audio_pids}",
                    "warning",
                )
            self._run_adb_command(
                self._cmd_manager.get_target_cmd("stop_audio_app_cmd", device_serial=device_serial),
                f"关闭手机端音频服务 ({device_serial})",
            )
            self._run_adb_command(
                self._cmd_manager.get_target_cmd("remove_audio_forward_cmd", device_serial=device_serial, port=port),
                f"移除端口转发 ({device_serial})",
            )
            with reg["lock"]:
                reg["audio_port"] = None
        except Exception as exc:
            logger.error("清理音频进程失败: %s", exc, exc_info=True)
            self.log_message.emit(f"清理音频进程失败: {exc!s}", "error")

    def stop_audio_sync(self, device_serial: str) -> None:
        self._stop_audio_internal(device_serial)

    def stop_audio(self, device_serial: str) -> None:
        self._task_runner.start(
            name="route-stop-audio",
            group="route",
            target=self._stop_audio_internal,
            args=(device_serial,),
        )

    def _start_audio_route_task(self, device_serial: str, port: int = DEFAULT_AUDIO_PORT) -> bool:
        try:
            # #region debug-point E:route-start
            _report_debug_event(
                "E",
                "route_service.start_audio_route",
                "[DEBUG] start audio route task entered",
                {
                    "device_serial": device_serial,
                    "port": port,
                    "player_path": self._cmd_manager.get_variable("player_path"),
                    "player_extra": self._cmd_manager.get_variable("player_extra"),
                },
            )
            # #endregion
            self._stop_audio_internal(device_serial)
            reg = self._process_registry.ensure(device_serial)
            with reg["lock"]:
                reg["audio_port"] = port
            forward_result = self._run_adb_command(
                self._cmd_manager.get_target_cmd("start_audio_forward_cmd", device_serial=device_serial, port=port),
                "音频端口转发",
            )
            if not self._require_adb_success(
                forward_result, action_text=f"音频端口转发 ({device_serial})", operation="audio_route"
            ):
                with reg["lock"]:
                    reg["audio_port"] = None
                return False

            start_result = self._run_adb_command(
                self._cmd_manager.get_target_cmd("start_audio_start_cmd", device_serial=device_serial),
                "唤醒 sndcpy App",
            )
            if not self._require_adb_success(
                start_result, action_text=f"唤醒 sndcpy App ({device_serial})", operation="audio_route"
            ):
                self._stop_audio_internal(device_serial)
                return False

            time.sleep(1)
            if not self._is_running():
                return False

            player_cmd = self._build_audio_player_cmd(port)
            # #region debug-point E:route-player-command
            _report_debug_event(
                "E",
                "route_service.start_audio_route",
                "[DEBUG] player command prepared",
                {
                    "device_serial": device_serial,
                    "player_cmd": player_cmd,
                },
            )
            # #endregion
            flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
            proc = subprocess.Popen(player_cmd, creationflags=flags)
            self._process_registry.register(device_serial, "audio", proc)

            if not self._wait_until_process_ready(proc):
                self.log_message.emit(f"音频播放器启动后立即退出 (设备: {device_serial})", "error")
                self._stop_audio_internal(device_serial)
                self.operation_completed.emit("audio_route", False)
                return False

            backend_label = "AudioRouter" if _is_audio_router(player_cmd[0]) else "VLC"
            self.log_message.emit(
                f"音频播放器已启动 [{backend_label}] (PID: {proc.pid}, 设备: {device_serial})", "success"
            )
            self.operation_completed.emit("audio_route", True)

            return_code = self._wait_for_process_exit(
                proc,
                on_shutdown_timeout=lambda: self._process_supervisor.kill_group(device_serial, "audio"),
            )

            reg = self._process_registry.ensure(device_serial)
            with reg["lock"]:
                proc_still_registered = proc in reg.get("audio", [])
            if self._is_running() and proc_still_registered and return_code is not None:
                self.log_message.emit(f"播放器已意外退出 (设备: {device_serial})", "warning")
                self.player_process_exited.emit(device_serial)
            if return_code is not None or not self._is_running():
                self._process_supervisor.remove_if_present(device_serial, "audio", proc)
            return True
        except Exception as exc:
            logger.error("音频路由启动失败: %s", exc, exc_info=True)
            self.log_message.emit(f"音频路由启动失败: {exc!s}", "error")
            self.operation_completed.emit("audio_route", False)
            return False

    def start_audio_route(self, device_serial: str, port: int = DEFAULT_AUDIO_PORT) -> None:
        self._task_runner.start(
            name="route-start-audio",
            group="route",
            target=self._start_audio_route_task,
            args=(device_serial, port),
        )

    def _start_video_route_task(
        self,
        device_serial: str,
        bitrate: int = 8000,
        max_size: str = "原始",
        lock_ori_index: int = 0,
        show_fps: bool = False,
        stay_awake: bool = True,
        turn_screen_off: bool = True,
    ) -> bool:
        try:
            # #region debug-point A:video-start
            _report_video_debug_event(
                "A",
                "route_service.start_video_route",
                "[DEBUG] video route task entered",
                {
                    "device_serial": device_serial,
                    "bitrate": bitrate,
                    "max_size": max_size,
                    "lock_ori_index": lock_ori_index,
                    "show_fps": show_fps,
                    "stay_awake": stay_awake,
                    "turn_screen_off": turn_screen_off,
                    "scrcpy_path": self._cmd_manager.get_variable("scrcpy_path"),
                    "scrcpy_extra": self._cmd_manager.get_variable("scrcpy_extra"),
                },
            )
            # #endregion
            self._mark_intentional_video_stop(device_serial)
            self._process_supervisor.kill_group(device_serial, "video")
            features = self._probe_scrcpy_features()
            lock_ori_flag = ""
            lock_ori_val = ""

            if lock_ori_index > 0:
                if features["display_ori"]:
                    lock_ori_flag = "--display-orientation"
                elif features["capture_ori"]:
                    lock_ori_flag = "--capture-orientation"
                elif features["lock_video_ori"]:
                    lock_ori_flag = "--lock-video-orientation"

                if lock_ori_flag:
                    if features["degrees"]:
                        lock_ori_val = ["", "0", "90", "180", "270"][lock_ori_index]
                    else:
                        lock_ori_val = ["", "0", "1", "2", "3"][lock_ori_index]

            fps_flag = "--print-fps" if show_fps else ""
            stay_awake_flag = "--stay-awake" if stay_awake else ""
            flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
            scrcpy_path = self._cmd_manager.get_variable("scrcpy_path")
            adb_path = self._cmd_manager.get_variable("adb_path")
            if not self._ensure_video_adb_server_ready(device_serial):
                return False
            scrcpy_cwd = None
            if scrcpy_path:
                resolved_scrcpy_path = os.path.abspath(scrcpy_path)
                if os.path.isfile(resolved_scrcpy_path):
                    scrcpy_cwd = os.path.dirname(resolved_scrcpy_path)
            env = os.environ.copy()
            if adb_path:
                env["ADB"] = adb_path
            stale_pids = self._cleanup_stale_scrcpy_processes(scrcpy_path)
            if stale_pids:
                _report_video_debug_event(
                    "A",
                    "route_service.start_video_route",
                    "[DEBUG] cleaned stale scrcpy processes",
                    {
                        "device_serial": device_serial,
                        "stale_pids": stale_pids,
                        "scrcpy_path": scrcpy_path,
                    },
                )
            attempts = self._build_video_attempt_plan(bitrate, max_size, turn_screen_off)
            for attempt_index, attempt in enumerate(attempts, start=1):
                attempt_bitrate = int(attempt["bitrate"])
                attempt_max_size = str(attempt["max_size"])
                attempt_turn_screen_off = bool(attempt["turn_screen_off"])
                if attempt_index > 1:
                    if not self._reset_video_adb_server(device_serial):
                        return False
                    self.log_message.emit(
                        f"首次画面链路未稳定，正在以兼容参数重试 ({attempt_max_size}/{attempt_bitrate} kbps)。",
                        "warning",
                    )
                max_size_flag = ""
                max_size_val = ""
                if attempt_max_size != "原始":
                    max_size_flag = "-m"
                    max_size_val = attempt_max_size
                screen_off_flag = "--turn-screen-off" if attempt_turn_screen_off else ""
                cmd = self._cmd_manager.get_target_cmd(
                    "start_video_scrcpy_cmd",
                    device_serial=device_serial,
                    video_bitrate=attempt_bitrate * 1000,
                    max_size_flag=max_size_flag,
                    max_size_val=max_size_val,
                    lock_ori_flag=lock_ori_flag,
                    lock_ori_val=lock_ori_val,
                    fps_flag=fps_flag,
                    stay_awake_flag=stay_awake_flag,
                    screen_off_flag=screen_off_flag,
                )
                _report_video_debug_event(
                    "A",
                    "route_service.start_video_route",
                    "[DEBUG] scrcpy command prepared",
                    {
                        "device_serial": device_serial,
                        "attempt_index": attempt_index,
                        "attempt_reason": attempt["reason"],
                        "cmd": cmd,
                        "features": features,
                    },
                )
                stdout_log_path = self._create_temp_log_path(device_serial, "stdout")
                stderr_log_path = self._create_temp_log_path(device_serial, "stderr")
                stdout_log = open(stdout_log_path, "w", encoding="utf-8", errors="replace")
                stderr_log = open(stderr_log_path, "w", encoding="utf-8", errors="replace")
                try:
                    proc = subprocess.Popen(
                        cmd,
                        cwd=scrcpy_cwd,
                        env=env,
                        creationflags=flags,
                        stdout=stdout_log,
                        stderr=stderr_log,
                        text=True,
                        encoding="utf-8",
                        errors="replace",
                    )
                finally:
                    stdout_log.close()
                    stderr_log.close()
                proc._debug_stdout_log_path = stdout_log_path
                proc._debug_stderr_log_path = stderr_log_path
                self._process_registry.register(device_serial, "video", proc)
                _report_video_debug_event(
                    "B",
                    "route_service.start_video_route",
                    "[DEBUG] scrcpy process spawned",
                    {
                        "device_serial": device_serial,
                        "attempt_index": attempt_index,
                        "pid": proc.pid,
                        "creationflags": flags,
                        "cwd": scrcpy_cwd,
                        "adb_env": env.get("ADB", ""),
                        "stdout_log_path": stdout_log_path,
                        "stderr_log_path": stderr_log_path,
                        "initial_poll": proc.poll(),
                    },
                )
                self.log_message.emit(log_await_screen_capture_auth(), "info")

                if not self._wait_until_process_ready(proc, seconds=2.5):
                    output = {
                        "stdout": self._read_debug_file(getattr(proc, "_debug_stdout_log_path", None)),
                        "stderr": self._read_debug_file(getattr(proc, "_debug_stderr_log_path", None)),
                    }
                    _report_video_debug_event(
                        "B",
                        "route_service.start_video_route",
                        "[DEBUG] scrcpy exited during ready wait",
                        {
                            "device_serial": device_serial,
                            "attempt_index": attempt_index,
                            "pid": proc.pid,
                            "returncode": proc.poll(),
                            "stdout": output["stdout"],
                            "stderr": output["stderr"],
                        },
                    )
                    self._process_supervisor.remove_if_present(device_serial, "video", proc)
                    self._cleanup_video_debug_logs(proc)
                    if attempt_index < len(attempts) and self._should_retry_video_launch(
                        output["stdout"], output["stderr"]
                    ):
                        continue
                    self.log_message.emit(f"画面路由启动后立即退出 (设备: {device_serial})", "error")
                    self.operation_completed.emit("video_route", False)
                    return False

                _report_video_debug_event(
                    "C",
                    "route_service.start_video_route",
                    "[DEBUG] scrcpy survived ready wait",
                    {
                        "device_serial": device_serial,
                        "attempt_index": attempt_index,
                        "pid": proc.pid,
                        "stdout_snapshot": self._read_debug_file(getattr(proc, "_debug_stdout_log_path", None)),
                        "stderr_snapshot": self._read_debug_file(getattr(proc, "_debug_stderr_log_path", None)),
                        "poll_after_ready": proc.poll(),
                    },
                )
                self.log_message.emit(
                    f"画面路由 (Scrcpy) 已启动，若已授权录屏，桌面端应很快出现窗口 (设备: {device_serial})", "success"
                )
                self.operation_completed.emit("video_route", True)
                self._task_runner.start(
                    name="route-watch-video",
                    group="route",
                    target=self._watch_video_process,
                    args=(device_serial, proc),
                )
                return True
            self.log_message.emit(f"画面路由启动后立即退出 (设备: {device_serial})", "error")
            self.operation_completed.emit("video_route", False)
            return False
        except Exception as exc:
            logger.error("视频路由启动失败: %s", exc, exc_info=True)
            self.log_message.emit(f"视频路由启动失败: {exc!s}", "error")
            self.operation_completed.emit("video_route", False)
            return False

    def start_video_route(
        self,
        device_serial: str,
        bitrate: int = 8000,
        max_size: str = "原始",
        lock_ori_index: int = 0,
        show_fps: bool = False,
        stay_awake: bool = True,
        turn_screen_off: bool = True,
    ) -> None:
        self._task_runner.start(
            name="route-start-video",
            group="route",
            target=self._start_video_route_task,
            args=(device_serial, bitrate, max_size, lock_ori_index, show_fps, stay_awake, turn_screen_off),
        )

    def _start_routing_session_task(self, request: RoutingRequest) -> None:
        if request.enable_audio and request.enable_video:
            self.log_message.emit(log_one_click_serial_video_first(), "info")
        video_started = False
        if request.enable_video:
            video_started = self._start_video_route_task(
                request.device_serial,
                bitrate=request.video_bitrate,
                max_size=request.max_size,
                lock_ori_index=request.lock_ori_index,
                show_fps=request.show_fps,
                stay_awake=request.stay_awake,
                turn_screen_off=request.turn_screen_off,
            )
        if request.enable_audio:
            if request.enable_video:
                reg = self._process_registry.ensure(request.device_serial)
                with reg["lock"]:
                    video_proc = reg.get("video", [])[-1] if reg.get("video") else None
                if (
                    not video_started
                    or video_proc is None
                    or not self._wait_for_video_renderer(video_proc, request.device_serial)
                ):
                    self.log_message.emit(
                        "画面链路尚未稳定，已暂停自动启动音频，请先确认录屏授权和图像窗口。", "warning"
                    )
                    return
                if self._is_running():
                    self.log_message.emit(log_video_link_stable_starting_audio(), "info")
            self._start_audio_route_task(request.device_serial, port=request.audio_port)

    def start_routing_session(self, request: RoutingRequest) -> None:
        if request.enable_audio and request.enable_video:
            self._task_runner.start(
                name="route-start-routing-session",
                group="route",
                target=self._start_routing_session_task,
                args=(request,),
            )
            return
        if request.enable_video:
            self.start_video_route(
                device_serial=request.device_serial,
                bitrate=request.video_bitrate,
                max_size=request.max_size,
                lock_ori_index=request.lock_ori_index,
                show_fps=request.show_fps,
                stay_awake=request.stay_awake,
                turn_screen_off=request.turn_screen_off,
            )
            return
        if request.enable_audio:
            self.start_audio_route(request.device_serial, port=request.audio_port)

    def _watch_video_process(self, device_serial: str, proc) -> None:
        reg = self._process_registry.ensure(device_serial)
        return_code = self._wait_for_process_exit(
            proc,
            on_shutdown_timeout=lambda: self._process_supervisor.kill_group(device_serial, "video"),
        )
        if return_code is not None:
            with contextlib.suppress(Exception):
                # best-effort: setting returncode on a dead process is non-critical
                proc.returncode = return_code
        output = {
            "stdout": self._read_debug_file(getattr(proc, "_debug_stdout_log_path", None)),
            "stderr": self._read_debug_file(getattr(proc, "_debug_stderr_log_path", None)),
        }
        with reg["lock"]:
            stop_markers = reg.setdefault("intentional_video_stop_pids", set())
            was_intentionally_stopped = proc.pid in stop_markers
            stop_markers.discard(proc.pid)
        # #region debug-point C:video-watch-exit
        _report_video_debug_event(
            "C",
            "route_service._watch_video_process",
            "[DEBUG] scrcpy process exited",
            {
                "device_serial": device_serial,
                "pid": proc.pid,
                "returncode": return_code,
                "was_intentionally_stopped": was_intentionally_stopped,
                "stdout": output["stdout"],
                "stderr": output["stderr"],
            },
        )
        # #endregion
        if self._is_running() and not was_intentionally_stopped and return_code not in (0, None):
            self.log_message.emit(f"画面路由进程已异常退出 (设备: {device_serial}, 返回码: {return_code})", "warning")
        self._process_supervisor.remove_if_present(device_serial, "video", proc)
        self._cleanup_video_debug_logs(proc)

    def _stop_streaming_internal(self, device_serial: str | None = None) -> None:
        try:
            if device_serial is None:
                for ds in list(self._process_registry.keys()):
                    self._mark_intentional_video_stop(ds)
                    self._process_supervisor.kill_group(ds, "video")
                    self._stop_audio_internal(ds)
                self.log_message.emit(log_all_streams_force_stopped(), "info")
            else:
                self._mark_intentional_video_stop(device_serial)
                self._process_supervisor.kill_group(device_serial, "video")
                self._stop_audio_internal(device_serial)
                self.log_message.emit(f"已停止设备的流媒体路由 ({device_serial})", "info")
        except Exception as exc:
            logger.error("停止路由发生错误: %s", exc, exc_info=True)
            self.log_message.emit(f"停止路由发生错误: {exc!s}", "error")

    def stop_streaming(self, device_serial: str | None = None) -> None:
        self._task_runner.start(
            name="route-stop-streaming",
            group="route",
            target=self._stop_streaming_internal,
            args=(device_serial,),
        )

    def stop_streaming_sync(self, device_serial: str | None = None) -> None:
        self._stop_streaming_internal(device_serial)

    def is_audio_running(self, device_serial: str) -> bool:
        reg = self._process_registry.ensure(device_serial)
        with reg["lock"]:
            audio_procs = list(reg.get("audio", []))
        return any(proc.poll() is None for proc in audio_procs)

    def is_video_running(self, device_serial: str) -> bool:
        reg = self._process_registry.ensure(device_serial)
        with reg["lock"]:
            video_procs = list(reg.get("video", []))
        return any(proc.poll() is None for proc in video_procs)
