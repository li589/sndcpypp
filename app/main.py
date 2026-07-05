import sys

from PyQt6.QtWidgets import QApplication

from app.bootstrap import Bootstrapper


class ApplicationEntry:
    def run(self) -> int:
        app = QApplication(sys.argv)
        app.setStyle("Fusion")
        bootstrapper = Bootstrapper()
        bootstrapper.install_translators(app)
        window = bootstrapper.create_main_window()
        window.show()
        return app.exec()


if __name__ == "__main__":
    sys.exit(ApplicationEntry().run())
