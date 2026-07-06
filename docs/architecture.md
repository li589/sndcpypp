# Architecture

## Overview

Sndcpy++ 采用分层架构，将原本单体式的 `main.py + core.py` 演进为清晰的 `app/` 包结构。顶层 `main.py` 收敛为兼容垫片，`SndcpyGUI` 主窗口迁入 `app/ui/main_window.py`，控制逻辑收口于 `CoreController`，领域模型、服务层与基础设施层按职责分离。

## Runtime Topology

```text
main.py (兼容垫片)
  -> app/main.py (ApplicationEntry)
    -> app/bootstrap.py (Bootstrapper)
      -> app/ui/main_window.py (SndcpyGUI)
        -> core.py (CoreController 控制编排)
          -> app/services/*
          -> app/infrastructure/process/task_runner.py
          -> adb / scrcpy / sndcpy.apk
          -> VLC / AudioRouter
        -> app/infrastructure/adb/UsbMonitor.py
        -> app/ui/* (协调器层)
```

`app/` 包不再反向依赖顶层模块，回环依赖已打破。

## Layered Architecture

### UI Layer

负责界面展示、表单输入、托盘与日志视图。

主窗口与协调器模块：

- `app/ui/main_window.py` — `SndcpyGUI` 主窗口（从顶层 `main.py` 迁入）
- `app/ui/main_window_ui.py` — 主窗口 UI 组装、页面挂载与控件引用绑定
- `app/ui/main_window_shell.py` — 托盘、窗口置顶、最小化、隐藏到托盘等壳行为
- `app/ui/runtime_settings.py` — 运行时路径解析、默认路径兜底与运行时配置请求构造
- `app/ui/widgets.py` — 可复用自定义控件（文件表格项、自动扩展输入框、拖放表格、刷新开关按钮）
- `app/ui/dialogs.py` — 自定义弹窗组件（`ExitConfirmDialog` / `ParamSettingsDialog` / `FileConflictDialog`）
- `app/ui/popup_manager.py` — 弹窗统一入口（标准消息框、确认框、自定义对话框返回值封装）
- `app/ui/message_templates.py` — 控制台日志前缀、状态栏提示、文件列表摘要与菜单文案模板
- `app/ui/menu_builders.py` — 托盘菜单、窗口右键菜单、文件页右键菜单的统一样式
- `app/ui/menu_coordinator.py` — 控制台右键菜单导出 / 清空与文件页右键菜单语义动作分发
- `app/ui/interaction_helpers.py` — 可复用纯 UI 协调规则
- `app/ui/request_builders.py` — 请求对象构造方法集中入口

页面级协调器：

- `app/ui/device_page_controller.py` — 设备列表刷新、选中项保持与设备下拉框同步
- `app/ui/device_runtime_coordinator.py` — 路径校验结果到状态栏、按钮恢复与首启后续动作编排
- `app/ui/device_service_coordinator.py` — 重启 ADB、清理 ADB、安装 sndcpy 等运维动作编排
- `app/ui/file_page_controller.py` — 文件页刷新、返回上级、双击行为、右键菜单与下载动作编排
- `app/ui/file_table_presenter.py` — 文件表格渲染、文件类型着色、符号链接目标展示
- `app/ui/file_actions.py` — 文件下载前的本地目录校验、冲突处理与批量上传重名冲突分发
- `app/ui/console_actions.py` — 控制台命令发送前的标准化、冷却触发与发送后清理

会话级协调器：

- `app/ui/recording_session_coordinator.py` — 录制会话状态机（开始 / 停止 / 失败）与状态栏计时、托盘提醒编排
- `app/ui/file_transfer_coordinator.py` — 文件传输进度事件到进度条、状态栏与文件列表刷新的编排
- `app/ui/settings_coordinator.py` — 设置持久化（加载 / 保存）与 UI 控件双向同步
- `app/ui/core_lifecycle_coordinator.py` — 核心控制器启动、关闭请求与超时编排
- `app/ui/console_logger_coordinator.py` — 控制台日志去重（签名 + 时间窗）与 HTML 渲染
- `app/ui/startup_coordinator.py` — 启动例程（路径校验 + USB 监听启动）的纯函数式编排
- `app/ui/teardown_coordinator.py` — 关闭事件全流程编排（退出确认 → 设置保存 → USB 停止 → 核心关闭 → 计时器停止 → 托盘隐藏）

动作协调模块：

- `app/ui/device_actions.py` — 启动 / 停止类动作的前置冷却、状态栏文案与 UI 收尾
- `app/ui/recording_actions.py` — 录制启动前的目标校验、音频冲突确认与覆盖处理

### Domain Layer

负责通用模型与枚举，无副作用。

- `app/domain/enums/file_type.py`
- `app/domain/models/file_info.py`
- `app/domain/models/operation_requests.py`

### Services Layer

负责业务逻辑编排。包含设备服务、路由服务、录制服务、文件管理服务、调试命令服务等。

### Infrastructure Layer

负责技术细节与平台能力。

- `app/infrastructure/adb/command_builder.py` — ADB 命令构造
- `app/infrastructure/adb/adb_client.py` — ADB 客户端封装
- `app/infrastructure/adb/path_resolver.py` — 含 `get_platform_vendor_subdir()` / `resolve_apk_path()` / `resolve_vendor_tool_path()`，按 `sys.platform` 分流
- `app/infrastructure/adb/UsbMonitor.py` — 三平台 USB 监听分流（pyudev / pywin32 + wmi / pyobjc）
- `app/infrastructure/adb/scrcpy_capabilities.py` — scrcpy 能力探测
- `app/infrastructure/process/task_runner.py` — `BackgroundTaskRunner` 后台线程统一入口与任务注册表
- `app/infrastructure/process/registry.py` — 进程注册表
- `app/infrastructure/process/supervisor.py` — 进程组终止按平台分流（Windows `CTRL_BREAK` + `taskkill` / POSIX `SIGINT` + `kill`）
- `app/infrastructure/config/settings_store.py` — 设置持久化
- `app/infrastructure/config/logging_config.py` — 日志初始化
- `app/infrastructure/config/constants.py` — 运行时常量（端口、超时等）

## Cross-Platform Vendor Layout

外部二进制依赖统一存放于仓库根目录 `vendor/`，按平台分子目录：

```text
vendor/
├── sndcpy.apk              # 平台无关，从 rom1v/sndcpy release 下载
├── windows/                # adb.exe / scrcpy.exe / *.dll / AudioRouter*.exe
├── macos/                  # adb / scrcpy / AudioRouter*
└── linux/                  # adb / scrcpy / AudioRouter*
```

平台分流入口：

- `app/infrastructure/adb/path_resolver.py::get_platform_vendor_subdir()` — 返回 `windows` / `macos` / `linux`
- `app/ui/runtime_settings.py::get_default_sndcpy_dir()` — 返回 `vendor/<platform>` 绝对路径
- `app/ui/runtime_settings.py::get_default_apk_path()` — 返回 `vendor/sndcpy.apk`
- `app/infrastructure/adb/path_resolver.py::resolve_apk_path()` — 优先用户 `sndcpy_dir/sndcpy.apk`，回退到 `vendor/sndcpy.apk`
- `app/infrastructure/adb/path_resolver.py::resolve_vendor_tool_path()` — 在 `vendor/<platform>/` 与 `vendor/<platform>/platform-tools/` 中查找 `adb` / `scrcpy`
- `app/ui/runtime_settings.py::get_audio_router_candidate_paths()` — 优先查找 `vendor/<platform>/AudioRouter*`，再回退到本地 CMake 构建目录

平台分支约定：

- 二进制后缀：`ext = ".exe" if os.name == "nt" else ""`
- 子进程窗口标志：`subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0`
- 进程组信号：Windows 走 `CTRL_BREAK_EVENT` + `taskkill /F /T`；POSIX 走 `SIGINT` + `proc.kill()`
- 托盘 / 置顶 / 全屏检测：`sys.platform == "win32"` 分支
- USB 监听后端：`sys.platform` 三分支（pyudev / pywin32 + wmi / pyobjc）
- 设置存储目录：Windows 走 `%APPDATA%/sndcpypp/`，POSIX 走 `~/.sndcpypp/`

## AudioRouter Backend

AudioRouter 是 C++ 原生音频接收 / 播放后端，源码位于 `AudioRouter/`。

- 基于 asio + miniaudio，两者均为 header-only 且跨平台
- `AudioRouter/CMakeLists.txt` 已三平台分支（WIN32 链 ws2_32，APPLE 链 CoreAudio，UNIX 链 dl / m / pthread）
- 源码中 Windows 特有代码用 `#ifdef _WIN32` 隔离
- 在目标平台原生 `cmake .. && make` 即可，无需交叉编译
- macOS / Linux 上找不到 AudioRouter 时自动回退到系统 VLC（见 `runtime_settings.py::get_default_player_path()`）
- 跨平台构建通过 GitHub Actions 矩阵：`.github/workflows/build-audiorouter.yml`
  - 六体系构建：Windows x64 / x86、Linux x64 / arm64、macOS arm64 / x64
  - macOS 通过 `-DCMAKE_OSX_ARCHITECTURES` 交叉编译 x86_64 / arm64
  - Linux 装 `libasound2-dev libpulse-dev`（miniaudio 在 Linux 上的音频后端）
  - 推 `v*` tag 时自动创建 Release 并附上六平台产物

## Interaction Flow

主要按钮与入口的运行链路：

| UI 入口 | `app/ui/main_window.py` | `core.py` | service / infrastructure | 外部进程或资源 |
| --- | --- | --- | --- | --- |
| 路径验证 | `validate_paths()` | `request_configure_runtime(RuntimeConfigurationRequest)` + `request_validate_runtime()` | `ADBDeviceService.validate_paths()` | `adb.exe` / `scrcpy.exe` / `sndcpy.apk` / 播放器 |
| 刷新设备 | `manual_refresh_devices()` / `auto_refresh_devices()` | `request_refresh_devices()` | `ADBDeviceService.refresh_devices()` → `ADBClient.run_logged()` | `adb devices` |
| 安装 SNDCPY | `install_sndcpy()` | `request_install_apk()` | `ADBDeviceService.install_apk()` | `adb install` |
| 一键启动路由 | `start_routing()` | `request_start_routing_session(RoutingRequest)` | `RouteService.start_audio_route()` / `start_video_route()` | `adb forward` / `sndcpy.apk` / `scrcpy.exe` / 播放器 |
| 独立音频启动 | `start_audio_only()` | `request_start_audio_route()` | `RouteService.start_audio_route()` | `adb` / 播放器 |
| 独立音频停止 | `stop_audio_only()` | `request_stop_audio_routes()` | `RouteService.stop_audio()` | 播放器 / `adb shell am force-stop` |
| 停止路由 | `stop_routing()` | `request_stop_streaming()` | `RouteService.stop_streaming()` | `scrcpy.exe` / 播放器 / `adb forward --remove` |
| 开始录制 | `start_recording_ui()` | `request_start_recording(RecordingRequest)` | `RecordingService.start_recording()` + `RecordingStateEvent` | `scrcpy --record --no-playback` |
| 停止录制 | `stop_recording_ui()` | `request_stop_recording()` | `RecordingService.stop_recording()` | 录制进程 |
| 文件浏览 | `refresh_file_list()` | `request_list_device_files(BrowseFilesRequest)` | `FileManagerService.list_device_files_detailed()` | `adb shell ls -all` |
| 文件上传 | `handle_files_dropped()` | `request_push_file(PushFileRequest)` | `FileManagerService.push_file()` | `adb push` |
| 文件下载 | `download_file_item()` | `request_pull_file(PullFileRequest)` | `FileManagerService.pull_file()` | `adb pull` |
| 控制台命令 | `execute_custom_command()` | `request_execute_console_target(ConsoleCommandRequest)` | `DebugCommandService.execute_custom_cmd()` | `adb` / `scrcpy` |
| 重启 ADB | `restart_adb_service()` | `request_restart_adb()` | `ADBDeviceService.restart_adb()` | `adb kill-server` + `adb devices` |
| 清理 ADB | `kill_adb_service()` | `request_force_kill_adb()` | `ADBDeviceService.force_kill_adb()` | `taskkill adb.exe` |

## Concurrency Rules

### Strictly Serialized

- 所有通过 `ADBClient.run_logged()` 发出的 ADB 命令统一串行，避免 `adb devices`、`kill-server`、`forward`、`shell` 互相打架
- 同一设备的录制流程使用设备锁保护，保证"停止旧录制 → 处理音频冲突 → 启动新录制"按顺序执行
- 同一设备的录音和独立音频路由存在资源冲突，录制启动时必须先暂停音频路由，录制结束后再尝试恢复
- 同一设备的文件传输使用设备锁保护，保证同设备多文件上传 / 下载按真实传输顺序更新进度
- 录制始终使用后台无预览模式，避免在已有路由窗口之外再拉起新的录制窗口
- 录制 watcher 与视频路由 watcher 使用显式"主动停止"标记，避免用户手动停止时被误记为失败或异常退出

### Can Run In Parallel

- UI 更新、状态栏刷新、日志输出、进度条更新可以并行发生
- `scrcpy` 视频进程、播放器音频进程、文件传输监控线程可以并行存在
- 不同设备上的非 ADB 进程可以并行运行（例如多个设备同时存在 `scrcpy` 或录制进程）
- 文件页中符号链接解析和目录列表渲染可以并行，解析结果再异步回写到表格

### Mixed Strategy

- 一键启动路由会同时提交"音频启动任务"和"视频启动任务"，但其中涉及的 ADB 子命令仍受全局 ADB 串行锁保护
- 多设备文件传输在进程层可并行；同一设备的多个文件传输由设备锁串行化，避免单设备进度状态互相覆盖

## Main And Core Boundary

边界原则：

- `app/ui/main_window.py`
  - 负责 UI 状态读取
  - 负责用户确认弹窗
  - 负责界面结果展示
- `core.py`
  - 作为统一门面暴露动作
  - 负责把 UI 请求路由到具体 service
  - 屏蔽内部注册表、进程组、命令构建器等实现细节

## Core Public API

`CoreController` 面向 UI 层的公开能力按以下分区组织：

- **运行时与生命周期**
  - `request_configure_runtime(RuntimeConfigurationRequest)`
  - `request_validate_runtime()`
  - `request_prewarm_scrcpy_capabilities()`
  - `request_shutdown()`
- **设备与 ADB**
  - `request_refresh_devices()`
  - `request_install_apk()`
  - `request_start_adb_server()`
  - `request_restart_adb()`
  - `request_force_kill_adb()`
- **路由**
  - `request_start_audio_route()`
  - `request_start_routing_session(RoutingRequest)`
  - `request_stop_audio_routes()`
  - `request_stop_streaming()`
  - `is_audio_running()`
- **录制**
  - `request_start_recording(RecordingRequest)`
  - `request_stop_recording()`
- **文件传输**
  - `request_list_device_files(BrowseFilesRequest)`
  - `request_push_file(PushFileRequest)`
  - `request_pull_file(PullFileRequest)`
- **控制台**
  - `request_execute_console_target(ConsoleCommandRequest)`

调用语义约定：

- `request_*` 统一表示"发起一个动作"
- `is_*` 统一表示"查询当前状态"
- 多参数动作优先通过请求对象进入 `core`
- 内部 service、进程注册表、命令构造器都留在 `core.py` 之后，不再由 UI 直接触达

## Event And Request Contracts

主流程通过显式请求对象与事件对象流转，不依赖日志展示文案：

- `ConsoleCommandRequest`
  - 使用 `ConsoleTargetKind` 表达目标类型
  - `app/ui/main_window.py` 负责把控制台下拉框展示文本映射为语义化目标
  - `core.py` 不再解析 `"[Scrcpy命令]"` 这类 UI 文案
- `RecordingStateEvent`
  - 使用 `RecordingState.STARTED / STOPPED / FAILED`
  - `RecordingService` 发出录制状态事件
  - `app/ui/main_window.py` 负责更新状态栏计时、托盘提醒和录制会话表
- `intentional_*_stop_pids`
  - `RecordingService` 和 `RouteService` 在主动停止前写入显式 PID 标记
  - watcher 只把未标记的非零退出视为真实异常
- `log_message`
  - 仅承担控制台输出与人工可读审计信息
  - 不承担程序控制流判断

## Runtime Defaults And Persistence

- **默认播放器路径**：`runtime_settings.py` 优先尝试 `shutil.which("vlc")`；Windows 下扫描常见 `VideoLAN\VLC\vlc.exe` 安装目录；最后回退到仓库内的 AudioRouter
- **设置文件路径**：`settings_store.py` 通过 `get_default_settings_path()` 将 `settings.json` 放到用户可写目录；Windows 优先使用 `%APPDATA%\sndcpypp\settings.json`；保存前自动创建父目录，避免安装目录只读导致保存失败

## Background Task Observability

后台任务统一经过 `app/infrastructure/process/task_runner.py` 中的 `BackgroundTaskRunner` 发起，除了代替裸 `daemon` 线程，还承担轻量任务注册表的职责。

能力：

- 为任务记录 `group`、状态、起止时间与异常文本
- 提供 `snapshot()`、`snapshot_by_group()`、`get_task()`、`wait_all()`
- 提供 `recent_failed_tasks()` 和 `clear_history()`
- 通过监听器把失败任务回灌到 `CoreController.log_message`

`CoreController` 暴露的观测接口：

- `get_background_task_snapshot()`
- `get_background_tasks_by_group()`
- `get_recent_background_failures()`
- `clear_background_task_history()`

UI 层不需要直接管理后台线程对象；后台任务失败进入统一控制台日志；后续若做"任务状态面板"或调试页，可直接复用现有观测接口。

## Design Constraints

- 不破坏现有用户工作流
- 优先做可增量迁移的模块
- 先保证兼容，再做深度解耦
- `UsbMonitor.py` 保持单文件实现以便跨项目复用
- 库代码必须使用 `log_to_console` 回调，不得直接 `print()`
- 跨平台二进制依赖统一放在 `vendor/`，不在业务代码里重复 `sys.platform` 判断
