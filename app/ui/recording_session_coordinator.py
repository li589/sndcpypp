from dataclasses import dataclass
from datetime import datetime

from PyQt6.QtCore import QTimer
from PyQt6.QtWidgets import QSystemTrayIcon, QWidget

from app.domain.models.operation_requests import RecordingState, RecordingStateEvent
from app.ui.main_window_shell import is_foreground_fullscreen, show_tray_message
from app.ui.message_templates import (
    status_recording_active,
    status_recording_active_multi,
    status_recording_failed,
    status_recording_finished,
    tray_recording_reminder_message,
    tray_recording_reminder_title,
)

LONG_RECORDING_REMINDER_SECONDS = 30 * 60


@dataclass(slots=True)
class RecordingSessionState:
    save_path: str
    started_at: datetime
    reminder_sent: bool = False


class RecordingSessionCoordinator:
    """管理录制会话状态、状态栏计时与长时间录制托盘提醒。"""

    def __init__(
        self,
        *,
        host_widget: QWidget,
        set_status: callable,
        tray_widget: QWidget,
    ) -> None:
        self._sessions: dict[str, RecordingSessionState] = {}
        self._set_status = set_status
        self._tray_widget = tray_widget

        self._status_timer = QTimer(host_widget)
        self._status_timer.setInterval(1000)
        self._status_timer.timeout.connect(self._refresh_recording_status)

        self._reminder_timer = QTimer(host_widget)
        self._reminder_timer.setInterval(60_000)
        self._reminder_timer.timeout.connect(self._check_long_recording_reminders)

    def handle_state_change(self, event: RecordingStateEvent) -> None:
        if event.state == RecordingState.STARTED:
            self._sessions[event.device_serial] = RecordingSessionState(
                save_path=event.payload,
                started_at=datetime.now(),
            )
            if not self._status_timer.isActive():
                self._status_timer.start()
            if not self._reminder_timer.isActive():
                self._reminder_timer.start()
            self._refresh_recording_status()
            return

        if event.state == RecordingState.STOPPED:
            self._sessions.pop(event.device_serial, None)
            self._stop_timers_if_idle()
            self._set_status(status_recording_finished(event.device_serial))
            return

        if event.state == RecordingState.FAILED:
            self._sessions.pop(event.device_serial, None)
            self._stop_timers_if_idle()
            self._set_status(status_recording_failed(event.device_serial))

    def _stop_timers_if_idle(self) -> None:
        if self._sessions:
            return
        self._status_timer.stop()
        self._reminder_timer.stop()

    def _refresh_recording_status(self) -> None:
        if not self._sessions:
            return

        now = datetime.now()
        elapsed_seconds = max(int((now - session.started_at).total_seconds()) for session in self._sessions.values())
        elapsed_text = _format_elapsed_seconds(elapsed_seconds)

        if len(self._sessions) == 1:
            device_serial = next(iter(self._sessions))
            self._set_status(status_recording_active(device_serial, elapsed_text))
            return

        self._set_status(status_recording_active_multi(len(self._sessions), elapsed_text))

    def _check_long_recording_reminders(self) -> None:
        if not self._sessions:
            return
        if is_foreground_fullscreen(self._tray_widget):
            return

        now = datetime.now()
        for device_serial, session in self._sessions.items():
            elapsed_seconds = int((now - session.started_at).total_seconds())
            if elapsed_seconds < LONG_RECORDING_REMINDER_SECONDS or session.reminder_sent:
                continue
            show_tray_message(
                self._tray_widget,
                tray_recording_reminder_title(),
                tray_recording_reminder_message(
                    device_serial,
                    _format_elapsed_seconds(elapsed_seconds),
                ),
                icon=QSystemTrayIcon.MessageIcon.Warning,
                timeout=6000,
            )
            session.reminder_sent = True


def _format_elapsed_seconds(seconds: int) -> str:
    hours, remainder = divmod(max(seconds, 0), 3600)
    minutes, secs = divmod(remainder, 60)
    return f"{hours:02d}:{minutes:02d}:{secs:02d}"
