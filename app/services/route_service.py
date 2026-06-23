import os
import subprocess
import time
from typing import Callable, Optional

from PyQt6.QtCore import QObject, pyqtSignal


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
        run_adb_command: Callable[[list[str], str], Optional[subprocess.CompletedProcess]],
        probe_scrcpy_features: Callable[[], dict],
        is_running: Callable[[], bool],
    ):
        super().__init__()
        self._cmd_manager = cmd_manager
        self._process_registry = process_registry
        self._process_supervisor = process_supervisor
        self._task_runner = task_runner
        self._run_adb_command = run_adb_command
        self._probe_scrcpy_features = probe_scrcpy_features
        self._is_running = is_running

    def _stop_audio_internal(self, device_serial: str):
        try:
            self._process_supervisor.kill_group(device_serial, "audio")
            port = self._cmd_manager.get_variable("port") or "28200"
            self._run_adb_command(
                self._cmd_manager.get_target_cmd("stop_audio_app_cmd", device_serial=device_serial),
                f"关闭手机端音频服务 ({device_serial})",
            )
            self._run_adb_command(
                self._cmd_manager.get_target_cmd("remove_audio_forward_cmd", device_serial=device_serial, port=port),
                f"移除端口转发 ({device_serial})",
            )
        except Exception as exc:
            self.log_message.emit(f"清理音频进程失败: {str(exc)}", "error")

    def stop_audio_sync(self, device_serial: str):
        self._stop_audio_internal(device_serial)

    def stop_audio(self, device_serial: str):
        self._task_runner.start(
            name="route-stop-audio",
            group="route",
            target=self._stop_audio_internal,
            args=(device_serial,),
        )

    def start_audio_route(self, device_serial: str, port: int = 28200):
        def _start_audio():
            try:
                self._stop_audio_internal(device_serial)
                self._run_adb_command(
                    self._cmd_manager.get_target_cmd("start_audio_forward_cmd", device_serial=device_serial, port=port),
                    "音频端口转发",
                )
                self._run_adb_command(
                    self._cmd_manager.get_target_cmd("start_audio_start_cmd", device_serial=device_serial),
                    "唤醒 sndcpy App",
                )

                time.sleep(1)
                if not self._is_running():
                    return

                player_cmd = self._cmd_manager.get_target_cmd("start_audio_player_cmd", device_serial=device_serial, port=port)
                flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
                proc = subprocess.Popen(player_cmd, creationflags=flags)
                self._process_registry.register(device_serial, "audio", proc)

                self.log_message.emit(f"音频播放器已启动 (PID: {proc.pid}, 设备: {device_serial})", "success")
                self.operation_completed.emit("audio_route", True)

                while self._is_running() and proc.poll() is None:
                    time.sleep(1)

                reg = self._process_registry.ensure(device_serial)
                if self._is_running() and proc in reg["audio"]:
                    self.log_message.emit(f"播放器已意外退出 (设备: {device_serial})", "warning")
                    self.player_process_exited.emit(device_serial)
                self._process_supervisor.remove_if_present(device_serial, "audio", proc)
            except Exception as exc:
                self.log_message.emit(f"音频路由启动失败: {str(exc)}", "error")
                self.operation_completed.emit("audio_route", False)

        self._task_runner.start(name="route-start-audio", group="route", target=_start_audio)

    def start_video_route(
        self,
        device_serial: str,
        bitrate: int = 8000,
        max_size: str = "原始",
        lock_ori_index: int = 0,
        show_fps: bool = False,
        stay_awake: bool = True,
        turn_screen_off: bool = True,
    ):
        def _start_video():
            try:
                self._process_supervisor.kill_group(device_serial, "video")

                max_size_flag = ""
                max_size_val = ""
                if max_size != "原始":
                    max_size_flag = "-m"
                    max_size_val = max_size

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
                screen_off_flag = "--turn-screen-off" if turn_screen_off else ""
                cmd = self._cmd_manager.get_target_cmd(
                    "start_video_scrcpy_cmd",
                    device_serial=device_serial,
                    video_bitrate=bitrate * 1000,
                    max_size_flag=max_size_flag,
                    max_size_val=max_size_val,
                    lock_ori_flag=lock_ori_flag,
                    lock_ori_val=lock_ori_val,
                    fps_flag=fps_flag,
                    stay_awake_flag=stay_awake_flag,
                    screen_off_flag=screen_off_flag,
                )
                flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
                proc = subprocess.Popen(cmd, creationflags=flags)
                self._process_registry.register(device_serial, "video", proc)
                self.log_message.emit(f"画面路由 (Scrcpy) 已启动 (设备: {device_serial})", "success")
                self.operation_completed.emit("video_route", True)
                self._task_runner.start(
                    name="route-watch-video",
                    group="route",
                    target=self._watch_video_process,
                    args=(device_serial, proc),
                )
            except Exception as exc:
                self.log_message.emit(f"视频路由启动失败: {str(exc)}", "error")
                self.operation_completed.emit("video_route", False)

        self._task_runner.start(name="route-start-video", group="route", target=_start_video)

    def _watch_video_process(self, device_serial: str, proc):
        proc.wait()
        self._process_supervisor.remove_if_present(device_serial, "video", proc)

    def stop_streaming(self, device_serial: Optional[str] = None):
        def _stop():
            try:
                if device_serial is None:
                    for ds in list(self._process_registry.keys()):
                        self._process_supervisor.kill_group(ds, "video")
                        self._stop_audio_internal(ds)
                    self.log_message.emit("已彻底强制结束所有设备的流媒体路由", "info")
                else:
                    self._process_supervisor.kill_group(device_serial, "video")
                    self._stop_audio_internal(device_serial)
                    self.log_message.emit(f"已停止设备的流媒体路由 ({device_serial})", "info")
            except Exception as exc:
                self.log_message.emit(f"停止路由发生错误: {str(exc)}", "error")

        self._task_runner.start(name="route-stop-streaming", group="route", target=_stop)

    def is_audio_running(self, device_serial: str) -> bool:
        reg = self._process_registry.ensure(device_serial)
        audio_procs = reg.get("audio", [])
        return any(proc.poll() is None for proc in audio_procs)
