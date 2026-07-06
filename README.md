# Sndcpy++

Sndcpy++ 是一款基于 Python 与 PyQt6 的 Android 设备桌面控制中心，集成音频路由、视频镜像、屏幕录制、文件传输与 ADB 调试控制台于一体。本项目以桌面应用形式整合 `adb`、`sndcpy`、`scrcpy` 与本地播放器，提供统一的设备会话管理界面。

## 主要功能

- 图形化设备管理（设备列表、自动刷新、USB 热插拔检测）
- 一键启动音频 / 视频路由（集成 `sndcpy.apk` + `scrcpy`）
- 音视频录制（后台运行，无额外窗口；录制状态栏计时与长时间录制托盘提醒）
- Android 文件浏览、上传、下载（按设备分片锁支持多设备并发传输）
- ADB 命令调试控制台（自定义命令、日志记录、上下文菜单）
- 系统托盘驻留（最小化到托盘、托盘图标激活、右键菜单）
- 设备列表实时状态指示（音频 / 视频 / 录制）
- 后台任务状态观测与失败日志
- 主动停止录制 / 视频路由时不再误报异常退出
- 跨平台 vendor 路径自动匹配（按 `sys.platform` 选用 `vendor/<platform>/`）

## 平台支持

| 平台 | sndcpy++ 桌面端 | AudioRouter |
|------|-----------------|-------------|
| Windows x64 | 支持 | 支持 |
| Windows x86 | 不支持（PyQt6 不提供 32 位 wheels） | 支持 |
| macOS Apple Silicon | 支持 | 支持 |
| macOS Intel | 支持 | 支持 |
| Linux x64 | 支持 | 支持 |
| Linux ARM64 | 不支持（vendor 二进制为 x86_64） | 支持 |

## 安装与运行

### 依赖

- Python 3.12+
- PyQt6 6.9.0
- 跨平台二进制依赖已内置于 `vendor/` 目录（sndcpy.apk + 各平台 adb / scrcpy）

完整依赖清单见 [`requirements.txt`](requirements.txt)。

### 从源码运行

```bash
# 创建虚拟环境
python -m venv venv
# Windows
.\venv\Scripts\activate
# macOS / Linux
source venv/bin/activate

# 安装依赖
python -m pip install -r requirements.txt

# 启动主程序
python main.py
```

### 从发行版运行

前往 [Releases](https://github.com/li589/sndcpypp/releases) 下载对应平台的压缩包，解压后运行可执行文件：

- Windows：`sndcpypp.exe`
- macOS：`sndcpypp.app`
- Linux：`sndcpypp`

USB 连接 Android 设备（需开启 USB 调试）后，在应用中选择设备并开始音频 / 视频转发。

## 项目结构

```text
app/                分层应用代码（domain / infrastructure / services / ui）
AudioRouter/        C++ 原生音频接收 / 播放后端（asio + miniaudio，三平台原生编译）
vendor/             跨平台外部二进制依赖
├── sndcpy.apk      平台无关，从 rom1v/sndcpy release 下载
├── windows/        adb.exe / scrcpy.exe / *.dll / AudioRouter*.exe
├── macos/          adb / scrcpy / AudioRouter*
└── linux/          adb / scrcpy / AudioRouter*
docs/               架构与设计文档
main.py             GUI 主入口（兼容垫片，已迁移到 app/ui/main_window.py）
core.py             后端控制核心
main.spec           PyInstaller 打包配置
tests/              单元测试（196 项）
```

`vendor/` 子目录按 `sys.platform` 自动选择，统一入口位于 `app/infrastructure/adb/path_resolver.py::get_platform_vendor_subdir()`。

## 开发文档

- [架构设计](docs/architecture.md)
- [贡献指南](CONTRIBUTING.md)
- [行为准则](CODE_OF_CONDUCT.md)
- [安全策略](SECURITY.md)
- [变更日志](CHANGELOG.md)
- [vendor 目录说明](vendor/README.md)

## 开发与测试

```bash
# 全量单元测试
python -m unittest discover -s tests -v

# 静态编译检查
python -m compileall main.py core.py app tests

# 代码风格检查（需安装 ruff）
ruff check .
ruff format --check .

# 类型检查（需安装 mypy）
mypy app
```

### 本地打包

```bash
pyinstaller main.spec --clean --noconfirm
```

产物位于 `dist/`。

### 发行构建

推送 `v*` tag 触发 GitHub Actions 自动构建并发布 Release：

- `Build Desktop App (Windows)` → `sndcpy++-windows-x64.zip`
- `Build Desktop App (Linux)` → `sndcpy++-linux-x64.zip`
- `Build Desktop App (macOS)` → `sndcpy++-macos-arm64.zip` / `sndcpy++-macos-x64.zip`
- `Build AudioRouter (cross-platform)` → 6 体系 AudioRouter 产物

## 贡献

欢迎参与贡献！请阅读 [贡献指南](CONTRIBUTING.md) 与 [行为准则](CODE_OF_CONDUCT.md)。

- 报告 Bug：使用 [Bug 报告模板](https://github.com/li589/sndcpypp/issues/new?template=bug_report.yml)
- 功能建议：使用 [功能建议模板](https://github.com/li589/sndcpypp/issues/new?template=feature_request.yml)
- 安全漏洞：请按 [安全策略](SECURITY.md) 私密报告

## License

本项目基于 [MIT License](LICENSE) 开源。

`vendor/` 目录下的外部二进制（sndcpy.apk、adb、scrcpy 等）遵循各自的许可证：

- [sndcpy](https://github.com/rom1v/sndcpy) — Apache 2.0
- [scrcpy](https://github.com/Genymobile/scrcpy) — Apache 2.0
- [Android Platform Tools](https://developer.android.com/tools/releases/platform-tools) — Apache 2.0
