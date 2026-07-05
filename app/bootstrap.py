import os

from PyQt6.QtCore import QLocale, QTranslator
from PyQt6.QtWidgets import QApplication

from app.infrastructure.config.logging_config import configure_logging
from app.ui.main_window import SndcpyGUI


class Bootstrapper:
    """Temporary bootstrapper used during the first refactor stage."""

    def __init__(self) -> None:
        self._translators: list[QTranslator] = []

    def install_translators(self, app: QApplication) -> None:
        """根据系统语言加载 translations/ 下的 .qm 翻译文件。

        翻译文件命名约定: messages_<lang>.qm (如 messages_zh_CN.qm)。
        若无匹配文件则跳过，界面回退到源码中的中文原文。
        """
        translations_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "translations")
        if not os.path.isdir(translations_dir):
            return

        locale = QLocale.system().name()
        # 优先精确匹配 (zh_CN)，回退到语言前缀 (zh)
        candidates = [f"messages_{locale}", f"messages_{locale.split('_')[0]}"]
        for candidate in candidates:
            qm_path = os.path.join(translations_dir, f"{candidate}.qm")
            if not os.path.isfile(qm_path):
                continue
            translator = QTranslator(app)
            if translator.load(qm_path):
                app.installTranslator(translator)
                self._translators.append(translator)

    def create_main_window(self) -> SndcpyGUI:
        log_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "logs")
        configure_logging(log_dir)
        return SndcpyGUI()
