from main import SndcpyGUI


class Bootstrapper:
    """Temporary bootstrapper used during the first refactor stage."""

    def create_main_window(self) -> SndcpyGUI:
        return SndcpyGUI()
