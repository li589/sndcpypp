import os
import shlex
import subprocess
import time
from collections.abc import Callable

from PyQt6.QtCore import QObject, pyqtSignal

from app.domain.models.operation_requests import RecordingState, RecordingStateEvent
from app.infrastructure.config.constants import DEFAULT_AUDIO_PORT
from app.infrastructure.config.logging_config import get_logger
from app.infrastructure.process.process_waiter import wait_for_process_exit
from app.ui.message_templates import (
    log_pause_audio_route_before_recording,
    log_recording_ended_restoring_audio,
    log_recording_finished_awaiting_mux,
)

logger = get_logger(__name__)


class RecordingService(QObject):
    log_message = pyqtSignal(str, str)
    recording_state_changed = pyqtSignal(object)

    def __init__(
        self,
        cmd_manager,
        process_registry,
        process_supervisor,
        task_runner,
        probe_scrcpy_features: Callable[[], dict],
        start_audio_route: Callable[[str, int], None],
        stop_audio: Callable[[str], None],
        is_running: Callable[[], bool],
    ) -> None:
        super().__init__()
        self._cmd_manager = cmd_manager
        self._process_registry = process_registry
        self._process_supervisor = process_supervisor
        self._task_runner = task_runner
        self._probe_scrcpy_features = probe_scrcpy_features
        self._start_audio_route = start_audio_route
        self._stop_audio = stop_audio
        self._is_running = is_running

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

    def _mark_intentional_record_stop(self, device_serial: str) -> None:
        reg = self._process_registry.ensure(device_serial)
        with reg["lock"]:
            stop_markers = reg.setdefault("intentional_record_stop_pids", set())
            for proc in reg.get("record", []):
                stop_markers.add(proc.pid)

    def start_recording(
        self,
        device_serial: str,
        save_path: str,
        bg_mode: bool,
        record_video: bool,
        record_audio: bool,
        record_ori_index: int = 0,
    ) -> None:
        def _rec():
            lock = self._process_registry.ensure(device_serial)["lock"]
            with lock:
                self._mark_intentional_record_stop(device_serial)
                self._process_supervisor.kill_group(device_serial, "record")
                self.log_message.emit(f"开始录制: {save_path} ({device_serial})", "command")

                scrcpy_path = self._cmd_manager.get_variable("scrcpy_path")
                extra = self._cmd_manager.get_variable("scrcpy_extra")
                cmd = [scrcpy_path]
                if extra.strip():
                    cmd.extend(shlex.split(extra))
                cmd.extend(["-s", device_serial, "--record", save_path])

                features = self._probe_scrcpy_features()
                # Recording always runs without opening a new scrcpy preview window.
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
                    reg = self._process_registry.ensure(device_serial)
                    with reg["lock"]:
                        audio_procs = list(reg.get("audio", []))
                    if any(proc.poll() is None for proc in audio_procs):
                        audio_was_running = True
                        self.log_message.emit(log_pause_audio_route_before_recording(), "warning")
                        self._stop_audio(device_serial)
                        time.sleep(1)

                try:
                    flags = 0
                    if os.name == "nt":
                        flags = subprocess.CREATE_NO_WINDOW | subprocess.CREATE_NEW_PROCESS_GROUP

                    proc = subprocess.Popen(cmd, creationflags=flags)
                    self._process_registry.register(device_serial, "record", proc)
                    self.recording_state_changed.emit(
                        RecordingStateEvent(RecordingState.STARTED, device_serial, save_path)
                    )

                    def _monitor_and_restore():
                        return_code = self._wait_for_process_exit(
                            proc,
                            on_shutdown_timeout=lambda: self._process_supervisor.kill_group(device_serial, "record"),
                        )
                        reg = self._process_registry.ensure(device_serial)
                        with reg["lock"]:
                            stop_markers = reg.setdefault("intentional_record_stop_pids", set())
                            was_intentionally_stopped = proc.pid in stop_markers
                            stop_markers.discard(proc.pid)
                        self._process_supervisor.remove_if_present(device_serial, "record", proc)
                        if return_code == 0 or was_intentionally_stopped or not self._is_running():
                            self.recording_state_changed.emit(
                                RecordingStateEvent(RecordingState.STOPPED, device_serial, save_path)
                            )
                        else:
                            error_text = f"录制进程异常退出，返回码: {return_code}"
                            self.log_message.emit(error_text, "error")
                            self.recording_state_changed.emit(
                                RecordingStateEvent(RecordingState.FAILED, device_serial, error_text)
                            )
                        if audio_was_running and self._is_running() and not was_intentionally_stopped:
                            self.log_message.emit(log_recording_ended_restoring_audio(), "info")
                            self._start_audio_route(device_serial, port=DEFAULT_AUDIO_PORT)

                    self._task_runner.start(
                        name="record-monitor-and-restore",
                        group="recording",
                        target=_monitor_and_restore,
                    )
                except Exception as exc:
                    self.recording_state_changed.emit(
                        RecordingStateEvent(RecordingState.FAILED, device_serial, str(exc))
                    )
                    self.log_message.emit(f"录制启动失败: {exc!s}", "error")
                    if audio_was_running and self._is_running():
                        self._start_audio_route(device_serial, port=DEFAULT_AUDIO_PORT)

        self._task_runner.start(name="record-start", group="recording", target=_rec)

    def stop_recording(self, device_serial: str | None = None) -> None:
        def _stop_rec_thread():
            try:
                if device_serial is None:
                    for ds in list(self._process_registry.keys()):
                        with self._process_registry.ensure(ds)["lock"]:
                            self._mark_intentional_record_stop(ds)
                            self._process_supervisor.kill_group(ds, "record")
                else:
                    with self._process_registry.ensure(device_serial)["lock"]:
                        self._mark_intentional_record_stop(device_serial)
                        self._process_supervisor.kill_group(device_serial, "record")
            except Exception as exc:
                self.log_message.emit(f"停止录制出错: {exc!s}", "error")
                return
            self.log_message.emit(log_recording_finished_awaiting_mux(), "success")

        self._task_runner.start(name="record-stop", group="recording", target=_stop_rec_thread)

    def is_recording_running(self, device_serial: str) -> bool:
        reg = self._process_registry.ensure(device_serial)
        with reg["lock"]:
            record_procs = list(reg.get("record", []))
        return any(proc.poll() is None for proc in record_procs)
