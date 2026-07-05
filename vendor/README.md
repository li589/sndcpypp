# vendor/ 目录说明

跨平台外部二进制依赖统一存放点。`sndcpy.apk` 与平台无关，放顶层；
`scrcpy` / `adb` 等二进制按平台分子目录。

## 期望结构

```
vendor/
├── sndcpy.apk              # 平台无关，从 rom1v/sndcpy release 下载
├── windows/                # Windows 二进制（adb.exe, scrcpy.exe, *.dll, AudioRouter*.exe）
├── macos/                  # macOS 二进制（adb, scrcpy, AudioRouter*）
└── linux/                  # Linux 二进制（adb, scrcpy, AudioRouter*）
```

`adb` / `scrcpy` 可以直接放在 `vendor/<platform>/` 下，也可以放在
`vendor/<platform>/platform-tools/` 下；代码会自动按当前平台查找。

GitHub Actions 产出的 AudioRouter 文件名可直接保留：

- `vendor/windows/AudioRouter-windows-x64.exe`
- `vendor/macos/AudioRouter-macos-universal`
- `vendor/linux/AudioRouter-linux-x64`

## 下载来源

| 文件 | 下载地址 |
| --- | --- |
| `sndcpy.apk` | https://github.com/rom1v/sndcpy/releases |
| Windows scrcpy | https://github.com/Genymobile/scrcpy/releases (win64 zip) |
| macOS scrcpy | https://github.com/Genymobile/scrcpy/releases (mac zip) |
| Linux scrcpy | https://github.com/Genymobile/scrcpy/releases (linux zip) 或 apt |

adb 包含在 scrcpy 的 release zip 里（v2.x+），也可单独从 Android SDK Platform Tools 下载：
https://developer.android.com/tools/releases/platform-tools

## AudioRouter 编译产物

AudioRouter 源码仍在 `AudioRouter/` 顶层 CMake 项目中。
运行时优先查找 `vendor/<platform>/` 下的发行产物，然后回退到本地 CMake 构建目录。
跨平台编译参考 `AudioRouter/CMakeLists.txt`，原生编译即可：

```bash
cd AudioRouter && mkdir build && cd build && cmake .. && make   # mac/linux
```
