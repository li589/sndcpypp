# -*- mode: python ; coding: utf-8 -*-
import os
import sys

# 只打包当前平台需要的 vendor 内容，避免三平台冗余二进制膨胀发行包。
# - vendor/sndcpy.apk          平台无关，必须打包
# - vendor/<platform>/         当前平台对应的运行时二进制
# - vendor/README.md           说明文档
_platform_subdir = {
    "win32": "windows",
    "darwin": "macos",
}.get(sys.platform, "linux")

_vendor_root = os.path.join(os.getcwd(), "vendor")
_platform_vendor_dir = os.path.join(_vendor_root, _platform_subdir)

# 平台感知图标：Windows 用 .ico，macOS 用 .icns（由 CI 转换），Linux 无图标
_icon = []
if sys.platform == 'win32':
    _icon = ['logo/logo (3).ico']
elif sys.platform == 'darwin':
    _icns_path = 'logo/logo.icns'
    if os.path.isfile(_icns_path):
        _icon = [_icns_path]

datas = []
if os.path.isfile(os.path.join(_vendor_root, "sndcpy.apk")):
    datas.append((os.path.join(_vendor_root, "sndcpy.apk"), "vendor"))
if os.path.isfile(os.path.join(_vendor_root, "README.md")):
    datas.append((os.path.join(_vendor_root, "README.md"), "vendor"))
if os.path.isdir(_platform_vendor_dir):
    datas.append((_platform_vendor_dir, os.path.join("vendor", _platform_subdir)))


a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=[],
    datas=datas,
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='sndcpypp',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=_icon,
)

# macOS: 生成 .app bundle 以获得原生应用体验
if sys.platform == 'darwin':
    app = BUNDLE(
        exe,
        name='sndcpypp.app',
        icon=_icon if _icon else None,
    )
