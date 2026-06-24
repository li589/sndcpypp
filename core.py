import subprocess
from typing import List, Optional

from PyQt6.QtCore import pyqtSignal, QObject
from app.domain.enums.file_type import FileType
from app.domain.models.file_info import FileInfo
from app.domain.models.operation_requests import (
    BrowseFilesRequest,
    ConsoleCommandRequest,
    ConsoleTargetKind,
    PullFileRequest,
    PushFileRequest,
    RecordingRequest,
    RecordingStateEvent,
    RuntimeConfigurationRequest,
    RoutingRequest,
)
from app.infrastructure.adb.adb_client import ADBClient
from app.infrastructure.adb.command_builder import ADBCommandBuilder
from app.infrastructure.adb.scrcpy_capabilities import ScrcpyCapabilitiesProbe
from app.infrastructure.process.registry import ProcessRegistry
from app.infrastructure.process.supervisor import ProcessSupervisor
from app.infrastructure.process.task_runner import BackgroundTaskRunner, TaskSnapshot
from app.services.adb_device_service import ADBDeviceService
from app.services.debug_command_service import DebugCommandService
from app.services.file_manager_service import FileManagerService
from app.services.recording_service import RecordingService
from app.services.route_service import RouteService
from app.ui.message_templates import log_background_task_failed


ADBCommand = ADBCommandBuilder

class CoreController(QObject):
    """UI 与底层 service 之间的统一接口。"""
    devices_updated = pyqtSignal(list)
    log_message = pyqtSignal(str, str)
    operation_completed = pyqtSignal(str, bool)
    validation_result = pyqtSignal(list)
    player_process_exited = pyqtSignal(str)
    
    files_listed = pyqtSignal(str, list, bool)
    files_listed_detailed = pyqtSignal(str, list, bool)
    symlink_resolved = pyqtSignal(str, str, bool)
    file_transfer_progress = pyqtSignal(str, str, int)
    recording_state_changed = pyqtSignal(object)

    def __init__(self, adb_path: str, player_path: str, sndcpy_dir: str):
        super().__init__()
        self._cmd_manager = ADBCommand({"adb_path": adb_path, "player_path": player_path, "sndcpy_dir": sndcpy_dir})
        self._running = True
        self._process_registry = ProcessRegistry()
        self._process_supervisor = ProcessSupervisor(self._process_registry)
        self._task_runner = BackgroundTaskRunner()
        self._task_runner.add_listener(self._handle_task_runner_event)
        self._scrcpy_capabilities_probe = ScrcpyCapabilitiesProbe()
        self._adb_client = ADBClient(self.log_message.emit)
        self._adb_device_service = ADBDeviceService(
            cmd_manager=self._cmd_manager,
            run_adb_command=self._adb_client.run_logged,
            task_runner=self._task_runner,
        )
        self._route_service = RouteService(
            cmd_manager=self._cmd_manager,
            process_registry=self._process_registry,
            process_supervisor=self._process_supervisor,
            task_runner=self._task_runner,
            run_adb_command=self._adb_client.run_logged,
            probe_scrcpy_features=self._probe_scrcpy_features,
            is_running=lambda: self._running,
        )
        self._recording_service = RecordingService(
            cmd_manager=self._cmd_manager,
            process_registry=self._process_registry,
            process_supervisor=self._process_supervisor,
            task_runner=self._task_runner,
            probe_scrcpy_features=self._probe_scrcpy_features,
            start_audio_route=self._route_service.start_audio_route,
            stop_audio=self._route_service.stop_audio_sync,
            is_running=lambda: self._running,
        )
        self._debug_command_service = DebugCommandService(
            cmd_manager=self._cmd_manager,
            adb_client=self._adb_client,
            task_runner=self._task_runner,
        )
        self._file_manager_service = FileManagerService(
            cmd_manager=self._cmd_manager,
            ls_parser=None,
            transfer_progress_parser=None,
            process_registry=self._process_registry,
            process_supervisor=self._process_supervisor,
            task_runner=self._task_runner,
            run_adb_command=self._adb_client.run_logged,
            is_running=lambda: self._running,
        )
        self._adb_device_service.devices_updated.connect(self.devices_updated.emit)
        self._adb_device_service.operation_completed.connect(self.operation_completed.emit)
        self._adb_device_service.validation_result.connect(self.validation_result.emit)
        self._adb_device_service.log_message.connect(self.log_message.emit)
        self._debug_command_service.log_message.connect(self.log_message.emit)
        self._route_service.log_message.connect(self.log_message.emit)
        self._route_service.operation_completed.connect(self.operation_completed.emit)
        self._route_service.player_process_exited.connect(self.player_process_exited.emit)
        self._recording_service.log_message.connect(self.log_message.emit)
        self._recording_service.recording_state_changed.connect(self.recording_state_changed.emit)
        self._file_manager_service.files_listed.connect(self.files_listed.emit)
        self._file_manager_service.files_listed_detailed.connect(self.files_listed_detailed.emit)
        self._file_manager_service.symlink_resolved.connect(self.symlink_resolved.emit)
        self._file_manager_service.file_transfer_progress.connect(self.file_transfer_progress.emit)
        self._file_manager_service.log_message.connect(self.log_message.emit)

    # Runtime lifecycle
    def update_config(self, adb_path: str, player_path: str, sndcpy_dir: str):
        self._cmd_manager.update_variable("adb_path", adb_path)
        self._cmd_manager.update_variable("player_path", player_path)
        self._cmd_manager.update_variable("sndcpy_dir", sndcpy_dir)

    def update_extra_args(self, adb_extra: str, player_extra: str, scrcpy_extra: str):
        self._cmd_manager.update_variable("adb_extra", adb_extra)
        self._cmd_manager.update_variable("player_extra", player_extra)
        self._cmd_manager.update_variable("scrcpy_extra", scrcpy_extra)

    def configure_runtime(
        self,
        adb_path: str,
        player_path: str,
        sndcpy_dir: str,
        adb_extra: str = "",
        player_extra: str = "",
        scrcpy_extra: str = "",
    ):
        self.update_config(adb_path, player_path, sndcpy_dir)
        self.update_extra_args(adb_extra, player_extra, scrcpy_extra)

    def stop(self):
        self._running = False
        self.stop_streaming(None)
        self.stop_recording(None)
        self.stop_file_transfers(None)
        self.log_message.emit("ADB控制器已安全停止", "info")

    def wait_for_background_tasks(self, timeout: float | None = None) -> bool:
        return self._task_runner.wait_all(timeout=timeout)

    def request_shutdown_and_wait(self, timeout: float | None = None) -> bool:
        self.stop()
        return self.wait_for_background_tasks(timeout=timeout)

    def _handle_task_runner_event(self, task: TaskSnapshot):
        if task.status != "failed":
            return
        self.log_message.emit(
            log_background_task_failed(task.group, task.display_name, task.error_text),
            "error",
        )

    def get_background_task_snapshot(self, *, include_completed: bool = True) -> list[TaskSnapshot]:
        return self._task_runner.snapshot(include_completed=include_completed)

    def get_background_tasks_by_group(self, *, include_completed: bool = True) -> dict[str, list[TaskSnapshot]]:
        return self._task_runner.snapshot_by_group(include_completed=include_completed)

    def get_recent_background_failures(self, limit: int = 10) -> list[TaskSnapshot]:
        return self._task_runner.recent_failed_tasks(limit=limit)

    def clear_background_task_history(
        self,
        *,
        group: str | None = None,
        keep_failed: bool = True,
        only_completed: bool = False,
    ) -> int:
        return self._task_runner.clear_history(
            group=group,
            keep_failed=keep_failed,
            only_completed=only_completed,
        )

    def request_configure_runtime(self, request: RuntimeConfigurationRequest):
        self.configure_runtime(
            adb_path=request.adb_path,
            player_path=request.player_path,
            sndcpy_dir=request.sndcpy_dir,
            adb_extra=request.adb_extra,
            player_extra=request.player_extra,
            scrcpy_extra=request.scrcpy_extra,
        )

    def request_shutdown(self):
        self.stop()

    # Debug console
    def execute_custom_cmd(self, device_serial: str, command_str: str, cmd_type: str = "adb"):
        self._debug_command_service.execute_custom_cmd(device_serial, command_str, cmd_type)

    def request_execute_custom_cmd(self, device_serial: str, command_str: str, cmd_type: str = "adb"):
        self.execute_custom_cmd(device_serial, command_str, cmd_type)

    # Device and ADB
    def validate_paths(self):
        self._adb_device_service.validate_paths()

    def request_validate_runtime(self):
        self.validate_paths()

    def refresh_devices(self):
        self._adb_device_service.refresh_devices()

    def request_refresh_devices(self):
        self.refresh_devices()

    def install_apk(self, device_serial: str):
        self._adb_device_service.install_apk(device_serial)

    def request_install_apk(self, device_serial: str):
        self.install_apk(device_serial)

    def _probe_scrcpy_features(self):
        scrcpy_path = self._cmd_manager.get_variable("scrcpy_path")
        return self._scrcpy_capabilities_probe.probe(scrcpy_path)

    def prewarm_scrcpy_capabilities(self):
        self._task_runner.start(
            name="core-prewarm-scrcpy-features",
            group="core",
            target=self._probe_scrcpy_features,
        )

    def request_prewarm_scrcpy_capabilities(self):
        self.prewarm_scrcpy_capabilities()

    # Routing
    def stop_audio(self, device_serial: str):
        self._route_service.stop_audio(device_serial)

    def stop_all_audio(self):
        for device_serial in self.list_managed_devices():
            self._route_service.stop_audio(device_serial)

    def stop_audio_routes(self, device_serial: Optional[str] = None):
        if device_serial:
            self.stop_audio(device_serial)
            return
        self.stop_all_audio()

    def request_stop_audio_routes(self, device_serial: Optional[str] = None):
        self.stop_audio_routes(device_serial)

    def start_audio_route(self, device_serial: str, port: int = 28200):
        self._route_service.start_audio_route(device_serial, port)

    def request_start_audio_route(self, device_serial: str, port: int = 28200):
        self.start_audio_route(device_serial, port)

    def start_routing_session(self, request: RoutingRequest):
        self._route_service.start_routing_session(request)

    def request_start_routing_session(self, request: RoutingRequest):
        self.start_routing_session(request)

    def start_video_route(self, device_serial: str, bitrate: int = 8000, max_size: str = "原始", lock_ori_index: int = 0, show_fps: bool = False, stay_awake: bool = True, turn_screen_off: bool = True):
        self._route_service.start_video_route(
            device_serial=device_serial,
            bitrate=bitrate,
            max_size=max_size,
            lock_ori_index=lock_ori_index,
            show_fps=show_fps,
            stay_awake=stay_awake,
            turn_screen_off=turn_screen_off,
        )
    
    def stop_streaming(self, device_serial: Optional[str] = None):
        self._route_service.stop_streaming(device_serial)

    def request_stop_streaming(self, device_serial: Optional[str] = None):
        self.stop_streaming(device_serial)

    # Recording
    def start_recording(self, request: RecordingRequest):
        self._recording_service.start_recording(
            device_serial=request.device_serial,
            save_path=request.save_path,
            bg_mode=request.bg_mode,
            record_video=request.record_video,
            record_audio=request.record_audio,
            record_ori_index=request.record_ori_index,
        )
    
    def is_audio_running(self, device_serial: str) -> bool:
        return self._route_service.is_audio_running(device_serial)

    def stop_recording(self, device_serial: Optional[str] = None):
        self._recording_service.stop_recording(device_serial)

    def request_start_recording(self, request: RecordingRequest):
        self.start_recording(request)

    def request_stop_recording(self, device_serial: str = ""):
        self.stop_recording(device_serial or None)

    # File transfer
    def list_device_files(self, device_serial: str, path: str):
        self._file_manager_service.list_device_files(device_serial, path)
        
    def list_device_files_detailed(self, device_serial: str, path: str):
        self._file_manager_service.list_device_files_detailed(device_serial, path)

    def request_list_device_files(self, request: BrowseFilesRequest):
        normalized_path = request.remote_path.strip() or "/"
        if not normalized_path.endswith("/"):
            normalized_path += "/"
        self.list_device_files_detailed(request.device_serial, normalized_path)
        return normalized_path

    def pull_file(self, device_serial: str, remote_path: str, local_dir: str, rename_to: str = None):
        self._file_manager_service.pull_file(device_serial, remote_path, local_dir, rename_to)

    def request_pull_file(self, request: PullFileRequest):
        self.pull_file(request.device_serial, request.remote_path, request.local_dir, request.rename_to)

    def push_file(self, device_serial: str, local_path: str, remote_dir: str, rename_to: str = None):
        self._file_manager_service.push_file(device_serial, local_path, remote_dir, rename_to)

    def request_push_file(self, request: PushFileRequest):
        normalized_dir = request.remote_dir if request.remote_dir.endswith("/") else f"{request.remote_dir}/"
        self.push_file(request.device_serial, request.local_path, normalized_dir, request.rename_to)
        
    def stop_file_transfers(self, device_serial: Optional[str] = None):
        self._file_manager_service.stop_file_transfers(device_serial)

    def list_managed_devices(self) -> list[str]:
        return list(self._process_registry.keys())

    # ADB process management
    def force_kill_adb(self):
        route_service = getattr(self, "_route_service", None)
        stop_streaming_sync = getattr(route_service, "stop_streaming_sync", None)
        if callable(stop_streaming_sync):
            stop_streaming_sync(None)
        else:
            self.stop_streaming(None)
        self._adb_device_service.force_kill_adb()

    def request_force_kill_adb(self):
        self.force_kill_adb()

    def start_adb_server(self):
        self._adb_device_service.start_adb_server()

    def request_start_adb_server(self):
        self.start_adb_server()

    def restart_adb(self):
        route_service = getattr(self, "_route_service", None)
        stop_streaming_sync = getattr(route_service, "stop_streaming_sync", None)
        if callable(stop_streaming_sync):
            stop_streaming_sync(None)
        else:
            self.stop_streaming(None)
        self._adb_device_service.restart_adb()

    def request_restart_adb(self):
        self.restart_adb()

    def execute_console_target(self, request: ConsoleCommandRequest):
        device_serial = request.device_serial
        cmd_type = "adb"
        if request.target_kind == ConsoleTargetKind.SCRCPY:
            cmd_type = "scrcpy"
            device_serial = ""
        elif request.target_kind == ConsoleTargetKind.ADB_GLOBAL:
            device_serial = ""

        self.execute_custom_cmd(device_serial, request.command_str, cmd_type)

    def request_execute_console_target(self, request: ConsoleCommandRequest):
        self.execute_console_target(request)

    # Legacy/internal compatibility
    def _run_adb_command_internal(self, command: List[str], description: str = "") -> Optional[subprocess.CompletedProcess]:
        return self._adb_client.run_logged(command, description)
