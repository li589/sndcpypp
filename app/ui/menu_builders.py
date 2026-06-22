from collections.abc import Callable
from typing import Literal

from PyQt6.QtCore import QPoint
from PyQt6.QtGui import QAction
from PyQt6.QtWidgets import QMenu, QWidget

from app.ui.message_templates import (
    FILE_MENU_COPY_FULL_PATH,
    FILE_MENU_COPY_LINK_TARGET,
    FILE_MENU_COPY_NAME,
    FILE_MENU_DOWNLOAD_FILE,
    FILE_MENU_DOWNLOAD_FOLDER,
    FILE_MENU_ENTER_FOLDER,
    TRAY_MENU_EXIT,
    TRAY_MENU_HIDE_TO_TRAY,
    TRAY_MENU_MINIMIZE_ALL,
    TRAY_MENU_SHOW_MAIN,
    WINDOW_MENU_HIDE_TO_TRAY,
    WINDOW_MENU_MINIMIZE_ALL,
    window_menu_toggle_top_label,
)

TrayMenuAction = Literal["minimize_all", "show_main", "hide_to_tray", "exit"]
WindowMenuAction = Literal["minimize_all", "toggle_top", "hide_to_tray"]
FileTableMenuAction = Literal[
    "enter_folder",
    "download",
    "copy_name",
    "copy_full_path",
    "copy_link_target",
]

MENU_STYLESHEET = """
QMenu { background-color: #2D2D30; color: #CCCCCC; border: 1px solid #3A3A3D; padding: 5px; }
QMenu::item { padding: 6px 25px 6px 20px; }
QMenu::item:selected { background-color: #3EAA7F; color: white; }
"""


def apply_menu_style(menu: QMenu) -> QMenu:
    menu.setStyleSheet(MENU_STYLESHEET)
    return menu


def create_styled_menu(parent: QWidget) -> QMenu:
    return apply_menu_style(QMenu(parent))


def build_tray_menu(
    parent: QWidget,
    *,
    on_minimize_all: Callable[[], None],
    on_show_main: Callable[[], None],
    on_hide_to_tray: Callable[[], None],
    on_exit: Callable[[], None],
) -> QMenu:
    menu = create_styled_menu(parent)
    _add_action(menu, TRAY_MENU_MINIMIZE_ALL, on_minimize_all)
    _add_action(menu, TRAY_MENU_SHOW_MAIN, on_show_main)
    _add_action(menu, TRAY_MENU_HIDE_TO_TRAY, on_hide_to_tray)
    menu.addSeparator()
    _add_action(menu, TRAY_MENU_EXIT, on_exit)
    return menu


def exec_window_context_menu(
    parent: QWidget,
    global_pos: QPoint,
    *,
    is_top: bool,
) -> WindowMenuAction | None:
    menu = create_styled_menu(parent)
    action_map = {
        _add_action(menu, WINDOW_MENU_MINIMIZE_ALL): "minimize_all",
        _add_action(menu, window_menu_toggle_top_label(is_top)): "toggle_top",
        _add_action(menu, WINDOW_MENU_HIDE_TO_TRAY): "hide_to_tray",
    }
    return action_map.get(menu.exec(global_pos))


def exec_file_table_context_menu(
    parent: QWidget,
    global_pos: QPoint,
    *,
    is_directory_entry: bool,
    include_copy_link_target: bool,
) -> FileTableMenuAction | None:
    menu = create_styled_menu(parent)
    action_map: dict[QAction, FileTableMenuAction] = {}

    if is_directory_entry:
        action_map[_add_action(menu, FILE_MENU_ENTER_FOLDER)] = "enter_folder"
        action_map[_add_action(menu, FILE_MENU_DOWNLOAD_FOLDER)] = "download"
    else:
        action_map[_add_action(menu, FILE_MENU_DOWNLOAD_FILE)] = "download"

    menu.addSeparator()
    action_map[_add_action(menu, FILE_MENU_COPY_NAME)] = "copy_name"
    action_map[_add_action(menu, FILE_MENU_COPY_FULL_PATH)] = "copy_full_path"

    if include_copy_link_target:
        action_map[_add_action(menu, FILE_MENU_COPY_LINK_TARGET)] = "copy_link_target"

    return action_map.get(menu.exec(global_pos))


def _add_action(menu: QMenu, text: str, handler: Callable[[], None] | None = None) -> QAction:
    action = menu.addAction(text)
    if handler is not None:
        action.triggered.connect(handler)
    return action
