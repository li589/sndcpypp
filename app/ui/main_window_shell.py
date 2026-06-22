import sys

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import QSystemTrayIcon

from app.ui.menu_builders import build_tray_menu, exec_window_context_menu
from app.ui.message_templates import tray_hidden_message, tray_hidden_title


def init_tray_icon(window) -> None:
    window.tray_icon = QSystemTrayIcon(window)
    window.tray_icon.setIcon(QIcon("logo\\ui_logo.png"))
    window.tray_icon.setContextMenu(
        build_tray_menu(
            window,
            on_minimize_all=window.minimize_all_windows,
            on_show_main=window.show_main_window,
            on_hide_to_tray=window.close_only_action,
            on_exit=window.full_exit_action,
        )
    )
    window.tray_icon.activated.connect(window.tray_icon_activated)
    window.tray_icon.show()


def tray_icon_activated(window, reason) -> None:
    if reason == QSystemTrayIcon.ActivationReason.Trigger:
        show_main_window(window)


def show_main_window(window) -> None:
    window.showNormal()
    window.activateWindow()
    window.raise_()


def handle_window_context_menu(window, global_pos) -> None:
    action = exec_window_context_menu(window, global_pos, is_top=window.is_top)
    if action == "minimize_all":
        minimize_all_windows(window)
    elif action == "toggle_top":
        toggle_top_window(window)
    elif action == "hide_to_tray":
        hide_to_tray(window)


def minimize_all_windows(window) -> None:
    window.showMinimized()
    if sys.platform != "win32":
        return

    try:
        import win32con
        import win32gui
    except ImportError:
        return

    def enum_handler(hwnd, ctx):
        del ctx
        if win32gui.IsWindowVisible(hwnd):
            class_name = win32gui.GetClassName(hwnd)
            if class_name in ("SDL_app", "SDL_Window"):
                win32gui.ShowWindow(hwnd, win32con.SW_MINIMIZE)

    win32gui.EnumWindows(enum_handler, None)


def toggle_top_window(window) -> None:
    window.is_top = not window.is_top
    window.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, window.is_top)
    show_main_window(window)


def hide_to_tray(window) -> None:
    window.hide()
    if hasattr(window, "tray_icon"):
        window.tray_icon.showMessage(
            tray_hidden_title(),
            tray_hidden_message(),
            QSystemTrayIcon.MessageIcon.Information,
            2000,
        )


def force_exit(window) -> None:
    window.force_quit = True
    window.close()
