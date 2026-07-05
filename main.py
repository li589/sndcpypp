"""Sndcpy++ 旧入口兼容垫片。

主窗口类 `SndcpyGUI` 已迁移至 `app/ui/main_window.py`，应用入口已迁移至
`app/main.py`。本文件保留为兼容入口，让 `python main.py` 仍能直接启动应用。
"""

import sys

from app.main import ApplicationEntry

if __name__ == "__main__":
    sys.exit(ApplicationEntry().run())
