from dataclasses import dataclass
from enum import Enum
from typing import Optional


class ConsoleTargetKind(str, Enum):
    ADB_DEVICE = "adb_device"
    ADB_GLOBAL = "adb_global"
    SCRCPY = "scrcpy"


class RecordingState(str, Enum):
    STARTED = "started"
    STOPPED = "stopped"
    FAILED = "failed"


@dataclass(slots=True)
class RuntimeConfigurationRequest:
    adb_path: str
    player_path: str
    sndcpy_dir: str
    adb_extra: str = ""
    player_extra: str = ""
    scrcpy_extra: str = ""


@dataclass(slots=True)
class ConsoleCommandRequest:
    command_str: str
    target_kind: ConsoleTargetKind
    device_serial: str = ""


@dataclass(slots=True)
class RecordingStateEvent:
    state: RecordingState
    device_serial: str
    payload: str


@dataclass(slots=True)
class RoutingRequest:
    device_serial: str
    enable_audio: bool
    enable_video: bool
    video_bitrate: int = 8000
    max_size: str = "原始"
    lock_ori_index: int = 0
    show_fps: bool = False
    stay_awake: bool = True
    turn_screen_off: bool = True
    audio_port: int = 28200


@dataclass(slots=True)
class RecordingRequest:
    device_serial: str
    save_path: str
    bg_mode: bool
    record_video: bool
    record_audio: bool
    record_ori_index: int = 0


@dataclass(slots=True)
class BrowseFilesRequest:
    device_serial: str
    remote_path: str


@dataclass(slots=True)
class PushFileRequest:
    device_serial: str
    local_path: str
    remote_dir: str
    rename_to: Optional[str] = None


@dataclass(slots=True)
class PullFileRequest:
    device_serial: str
    remote_path: str
    local_dir: str
    rename_to: Optional[str] = None
