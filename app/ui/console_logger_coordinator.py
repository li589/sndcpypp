from collections.abc import Callable
from datetime import datetime

from PyQt6.QtGui import QTextCursor
from PyQt6.QtWidgets import QTextEdit

from app.ui.message_templates import render_console_html

_DEDUP_WINDOW_SECONDS = 1.5


class ConsoleLoggerCoordinator:
    """控制台日志去重与 HTML 渲染协调器。

    负责对 `log_to_console` 调用进行：
    1. 文本规范化（去空白、空消息丢弃）；
    2. 基于签名 (msg_type, normalized_message) 的短时间去重；
    3. 通过 `render_console_html` 渲染并追加到 QTextEdit。
    """

    def __init__(self, *, console_output: QTextEdit) -> None:
        self._console_output = console_output
        self._last_log_signature: tuple[str, str] | None = None
        self._last_log_time: datetime | None = None

    def emit(self, message: str, msg_type: str = "info") -> None:
        normalized_message = (message or "").strip()
        if not normalized_message:
            return

        current_time = datetime.now()
        signature = (msg_type, normalized_message)
        if (
            self._last_log_signature == signature
            and self._last_log_time is not None
            and (current_time - self._last_log_time).total_seconds() < _DEDUP_WINDOW_SECONDS
        ):
            return

        self._last_log_signature = signature
        self._last_log_time = current_time

        html_message = render_console_html(normalized_message, msg_type, current_time)
        console = self._console_output
        console.moveCursor(QTextCursor.MoveOperation.End)
        console.insertHtml(html_message)
        console.moveCursor(QTextCursor.MoveOperation.End)

    @property
    def last_log_signature(self) -> tuple[str, str] | None:
        return self._last_log_signature

    @property
    def last_log_time(self) -> datetime | None:
        return self._last_log_time


def make_log_to_console_slot(
    coordinator: ConsoleLoggerCoordinator,
) -> Callable[[str, str], None]:
    """生成兼容旧 `log_to_console(message, msg_type)` 签名的回调。"""
    return coordinator.emit
