import os

from app.infrastructure.config.logging_config import configure_logging
from app.ui.main_window import SndcpyGUI


class Bootstrapper:
    """Temporary bootstrapper used during the first refactor stage."""

    def create_main_window(self) -> SndcpyGUI:
        log_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "logs")
        configure_logging(log_dir)
        return SndcpyGUI()
