import os
import shlex
import subprocess
import time
from typing import Callable, Optional

from PyQt6.QtCore import QObject, pyqtSignal


class RecordingService(QObject):
    log_message = pyqtSignal(str, str)

    def __init__(
        self,
        cmd_manager,
        process_registry,
        process_supervisor,
        task_runner,
        probe_scrcpy_features: Callable[[], dict],
        start_audio_route: Callable[[str, int], None],
        stop_audio: Callable[[str], None],
    ):
        super().__init__()
        self._cmd_manager = cmd_manager
        self._process_registry = process_registry
        self._process_supervisor = process_supervisor
        self._task_runner = task_runner
        self._probe_scrcpy_features = probe_scrcpy_features
        self._start_audio_route = start_audio_route
        self._stop_audio = stop_audio

    def start_recording(
        self,
        device_serial: str,
        save_path: str,
        bg_mode: bool,
        record_video: bool,
        record_audio: bool,
        record_ori_index: int = 0,
    ):
        def _rec():
            lock = self._process_registry.ensure(device_serial)["lock"]
            with lock:
                self._process_supervisor.kill_group(device_serial, "record")
                self.log_message.emit(f"开始录制: {save_path} ({device_serial})", "command")

                scrcpy_path = self._cmd_manager.get_variable("scrcpy_path")
                extra = self._cmd_manager.get_variable("scrcpy_extra")
                cmd = [scrcpy_path]
                if extra.strip():
                    cmd.extend(shlex.split(extra))
                cmd.extend(["-s", device_serial, "--record", save_path])

                features = self._probe_scrcpy_features()
                if bg_mode:
                    cmd.append(features.get("no_playback", "--no-playback"))

                if not record_video:
                    cmd.append("--no-video")
                if record_audio:
                    if "--no-audio" in cmd:
                        cmd.remove("--no-audio")
                    cmd.extend(["--audio-source", "output"])
                else:
                    cmd.append("--no-audio")

                if record_ori_index > 0:
                    rec_flag = ""
                    if features["record_ori"]:
                        rec_flag = "--record-orientation"
                    elif features["capture_ori"]:
                        rec_flag = "--capture-orientation"
                    elif features["lock_video_ori"]:
                        rec_flag = "--lock-video-orientation"

                    if rec_flag:
                        cmd.append(rec_flag)
                        if features["degrees"]:
                            cmd.append(["", "0", "90", "180", "270"][record_ori_index])
                        else:
                            cmd.append(["", "0", "1", "2", "3"][record_ori_index])

                audio_was_running = False
                if record_audio:
                    audio_procs = self._process_registry.ensure(device_serial).get("audio", [])
                    if any(proc.poll() is None for proc in audio_procs):
                        audio_was_running = True
                        self.log_message.emit("检测到音频路由正在运行，为避免冲突将先暂停...", "warning")
                        self._stop_audio(device_serial)
                        time.sleep(1)

                try:
                    flags = 0
                    if os.name == "nt":
                        flags = subprocess.CREATE_NO_WINDOW | subprocess.CREATE_NEW_PROCESS_GROUP

                    proc = subprocess.Popen(cmd, creationflags=flags)
                    self._process_registry.register(device_serial, "record", proc)

                    def _monitor_and_restore():
                        proc.wait()
                        self._process_supervisor.remove_if_present(device_serial, "record", proc)
                        if audio_was_running:
                            self.log_message.emit("录制已结束，正在尝试恢复之前的音频路由...", "info")
                            self._start_audio_route(device_serial, port=28200)

                    self._task_runner.start(
                        name="record-monitor-and-restore",
                        group="recording",
                        target=_monitor_and_restore,
                    )
                except Exception as exc:
                    self.log_message.emit(f"录制启动失败: {str(exc)}", "error")
                    if audio_was_running:
                        self._start_audio_route(device_serial, port=28200)

        self._task_runner.start(name="record-start", group="recording", target=_rec)

    def stop_recording(self, device_serial: Optional[str] = None):
        def _stop_rec_thread():
            if device_serial is None:
                for ds in list(self._process_registry.keys()):
                    with self._process_registry.ensure(ds)["lock"]:
                        self._process_supervisor.kill_group(ds, "record")
            else:
                with self._process_registry.ensure(device_serial)["lock"]:
                    self._process_supervisor.kill_group(device_serial, "record")
            self.log_message.emit("录制已结束保存 (等待后台封包完成)", "success")

        self._task_runner.start(name="record-stop", group="recording", target=_stop_rec_thread)
