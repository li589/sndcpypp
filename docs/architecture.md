# Architecture

## Overview

Sndcpy++ 采用渐进式分层重构策略，在不破坏现有功能的前提下，将旧的单体式 `main.py + core.py` 逐步演进为更清晰的结构。

当前阶段重点：

- 保留现有 GUI 和控制逻辑可运行
- 抽取通用模型、服务层与命令构建逻辑
- 建立新的 `app/` 包结构
- 明确 `main.py -> core.py -> services -> infrastructure` 边界
- 统一后台任务入口与任务观测能力

## Current Runtime Topology

```text
main.py (PyQt6 GUI)
  -> core.py (控制编排)
    -> app/services/*
    -> app/infrastructure/process/task_runner.py
    -> adb.exe
    -> scrcpy.exe
    -> sndcpy.apk
    -> VLC / AudioRouter
  -> app/infrastructure/adb/UsbMonitor.py
```

## Target Topology

```text
app.main
  -> app.bootstrap
    -> MainWindow
    -> AppController
    -> Services
    -> Infrastructure

兼容层:
main.py
core.py
```

## Refactor Layers

### UI Layer

负责界面展示、表单输入、托盘和日志视图。

计划模块：

- `app/ui/main_window.py`
- `app/ui/pages/*.py`
- `app/ui/dialogs/*.py`
- `app/ui/widgets/*.py`

### Application Layer

负责流程编排、会话状态机、事件分发。

计划模块：

- `app/application/app_controller.py`
- `app/application/session_manager.py`
- `app/application/state_machine.py`
- `app/application/event_bus.py`

### Domain Layer

负责通用模型与枚举。

当前已抽出：

- `app/domain/enums/file_type.py`
- `app/domain/models/file_info.py`
- `app/domain/models/operation_requests.py`

### Infrastructure Layer

负责技术细节与平台能力。

当前已抽出：

- `app/infrastructure/adb/command_builder.py`
- `app/infrastructure/adb/adb_client.py`
- `app/infrastructure/adb/path_resolver.py`
- `app/infrastructure/adb/UsbMonitor.py`
- `app/infrastructure/process/task_runner.py`
- `app/infrastructure/process/registry.py`
- `app/infrastructure/process/supervisor.py`
- `app/infrastructure/config/settings_store.py`

## Current Compatibility Strategy

为避免一次性大改导致功能回归，当前采用兼容方案：

- `main.py` 继续作为旧入口
- `app/main.py` 新增为重构入口
- `core.py` 继续保留控制逻辑
- `core.py` 已开始依赖 `app/` 中的抽离模块
- USB 监听维持单文件实现，但路径已迁移到 `app/infrastructure/adb/UsbMonitor.py`

## Interaction Flow

当前主要按钮和入口的运行链路如下：

| UI入口 | `main.py` | `core.py` | service / infrastructure | 外部进程或资源 |
| --- | --- | --- | --- | --- |
| 路径验证 | `validate_paths()` | `request_configure_runtime(RuntimeConfigurationRequest)` + `request_validate_runtime()` | `ADBDeviceService.validate_paths()` | `adb.exe` / `scrcpy.exe` / `sndcpy.apk` / 播放器 |
| 刷新设备 | `manual_refresh_devices()` / `auto_refresh_devices()` | `request_refresh_devices()` | `ADBDeviceService.refresh_devices()` -> `ADBClient.run_logged()` | `adb devices` |
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

- 所有通过 `ADBClient.run_logged()` 发出的 ADB 命令统一串行，避免 `adb devices`、`kill-server`、`forward`、`shell` 互相打架。
- 同一设备的录制流程使用设备锁保护，保证“停止旧录制 -> 处理音频冲突 -> 启动新录制”按顺序执行。
- 同一设备的录音和独立音频路由存在资源冲突，录音启动时必须先暂停音频路由，录制结束后再尝试恢复。
- 录制始终使用后台无预览模式，避免在已有路由窗口之外再拉起新的录制窗口。

### Can Run In Parallel

- UI 更新、状态栏刷新、日志输出、进度条更新可以并行发生。
- `scrcpy` 视频进程、播放器音频进程、文件传输监控线程可以并行存在。
- 不同设备上的非 ADB 进程可以并行运行，例如多个设备同时存在 `scrcpy` 或录制进程。
- 文件页中符号链接解析和目录列表渲染可以并行，解析结果再异步回写到表格。

### Mixed Strategy

- 一键启动路由会同时提交“音频启动任务”和“视频启动任务”，但其中涉及的 ADB 子命令仍受全局 ADB 串行锁保护。
- 多设备文件传输在进程层可并行，但依赖 ADB 命令的准备阶段仍然是串行的。

## Blocking Hotspots

重点排查和已经识别出的慢响应点：

1. 点击路由相关按钮后，若立即在主线程执行 `kill_group()`，会导致 UI 短暂卡顿。
2. 第一次启动视频或录制时，`scrcpy --help` 能力探测若在主线程中执行，会明显拖慢首击响应。
3. ADB 服务重启和设备刷新如果同步等待 `subprocess.run()` 结果，会让按钮反馈变慢。
4. 停止录制或停止路由时，进程清理若发生在主线程，会让界面误以为“按钮没点上”。
5. 文件页目录扫描和冲突判断如果混入主线程重计算，会让大目录切换卡顿。

## First Optimization Batch

当前已经优先优化的第一批入口：

1. `一键启动路由`
   - 把旧进程清理和能力探测挪到后台线程
   - `main.py` 只负责收集 UI 参数并调用 `core`
2. `独立音频`
   - 停止和启动都改为后台任务
   - 补充按钮冷却，避免快速连点
3. `录制`
   - 录制命令拼装与能力探测移到后台
   - 固定使用无预览录制，避免新增录制窗口
   - 保留同设备录制锁，避免竞态
4. `重启ADB`
   - 改成“立即反馈 + 后台执行 + 异步刷新设备”
5. `清理ADB`
   - 保持后台执行，避免 `taskkill` 阻塞主窗口

## Main And Core Boundary

当前边界原则：

- `main.py`
  - 负责 UI 状态读取
  - 负责用户确认弹窗
  - 负责界面结果展示
- `core.py`
  - 作为统一门面暴露动作
  - 负责把 UI 请求路由到具体 service
  - 屏蔽内部注册表、进程组、命令构建器等实现细节

当前已经完成的门面收口：

- `request_configure_runtime()`
- `request_validate_runtime()`
- `request_refresh_devices()`
- `request_install_apk()`
- `request_start_routing_session()`
- `request_start_audio_route()`
- `request_stop_audio_routes()`
- `request_start_recording()` / `request_stop_recording()`
- `request_list_device_files()`
- `request_push_file()` / `request_pull_file()`
- `request_execute_console_target()`
- `request_restart_adb()` / `request_force_kill_adb()`
- `request_start_adb_server()`
- `request_stop_streaming()`
- `request_shutdown()`

## UI Coordination Layer

为了继续削薄 `main.py`，当前把一部分“纯 UI 协调逻辑”下沉到了 [interaction_helpers.py](file:///d:/temp_desktop/Proj/sndcpy++/app/ui/interaction_helpers.py)，并新增了统一弹窗入口 [popup_manager.py](file:///d:/temp_desktop/Proj/sndcpy++/app/ui/popup_manager.py)、消息模板层 [message_templates.py](file:///d:/temp_desktop/Proj/sndcpy++/app/ui/message_templates.py)、菜单构建辅助层 [menu_builders.py](file:///d:/temp_desktop/Proj/sndcpy++/app/ui/menu_builders.py)、菜单协调层 [menu_coordinator.py](file:///d:/temp_desktop/Proj/sndcpy++/app/ui/menu_coordinator.py)、主窗口 UI 组装层 [main_window_ui.py](file:///d:/temp_desktop/Proj/sndcpy++/app/ui/main_window_ui.py)、主窗口壳行为层 [main_window_shell.py](file:///d:/temp_desktop/Proj/sndcpy++/app/ui/main_window_shell.py)、运行时设置与默认路径层 [runtime_settings.py](file:///d:/temp_desktop/Proj/sndcpy++/app/ui/runtime_settings.py)、设备页控制层 [device_page_controller.py](file:///d:/temp_desktop/Proj/sndcpy++/app/ui/device_page_controller.py)、设备页运行时协调层 [device_runtime_coordinator.py](file:///d:/temp_desktop/Proj/sndcpy++/app/ui/device_runtime_coordinator.py)、设备页运维动作协调层 [device_service_coordinator.py](file:///d:/temp_desktop/Proj/sndcpy++/app/ui/device_service_coordinator.py)、文件页控制层 [file_page_controller.py](file:///d:/temp_desktop/Proj/sndcpy++/app/ui/file_page_controller.py)、文件表格呈现层 [file_table_presenter.py](file:///d:/temp_desktop/Proj/sndcpy++/app/ui/file_table_presenter.py)、通用控件层 [widgets.py](file:///d:/temp_desktop/Proj/sndcpy++/app/ui/widgets.py) 以及按页面拆分的动作协调模块：

- 按钮冷却与恢复
- 远程路径规范化、拼接与返回上级目录
- 录制文件名生成
- 上传/下载自动重命名策略
- 常用弹窗消息与状态文案模板
- 常用确认弹窗与文件冲突选择流程
- 参数设置、退出确认、成功/警告/错误提示的统一入口
- `QFileDialog` 的打开文件、保存文件、选择目录统一入口
- 控制台前缀颜色、状态栏提示、文件列表摘要模板
- 文件页右键菜单、托盘菜单、窗口菜单、控制台菜单文案与常用业务日志模板
- 统一菜单样式与“菜单点击 -> 语义动作”转换

配套的自定义弹窗组件放在 [dialogs.py](file:///d:/temp_desktop/Proj/sndcpy++/app/ui/dialogs.py)：

- `ExitConfirmDialog`
- `ParamSettingsDialog`
- `FileConflictDialog`

当前分工：

- `main.py`
  - 负责触发用户交互
  - 负责把用户选择结果转成动作请求
  - 负责更新控件状态与状态栏
- `popup_manager.py`
  - 负责所有弹窗的统一入口
  - 负责标准消息框、确认框、自定义对话框的返回值封装
  - 负责弹窗文案、结果语义、系统文件选择弹窗和弹窗审计日志
- `interaction_helpers.py`
  - 负责可复用的纯 UI 协调规则
  - 不依赖业务 service
  - 不直接触发 `core` 动作
- `message_templates.py`
  - 负责控制台日志前缀与颜色模板
  - 负责状态栏提示与文件列表摘要模板
  - 负责菜单文案与高频业务日志模板
- `menu_builders.py`
  - 负责托盘菜单、窗口右键菜单、文件页右键菜单的统一样式
  - 负责把菜单点击结果转换为稳定的语义动作，减少 `main.py` 中的 `QAction` 分发细节
- `menu_coordinator.py`
  - 负责控制台右键菜单的导出/清空流程
  - 负责文件页右键菜单语义动作到 UI 行为的最终分发
- `main_window_ui.py`
  - 负责主窗口外壳的 UI 组装、页面挂载和控件引用绑定
  - 负责统一主题和主窗口级视觉样式
- `main_window_shell.py`
  - 负责托盘、窗口置顶、最小化、隐藏到托盘等主窗口壳行为
  - 负责窗口菜单动作到主窗口行为的分发
- `runtime_settings.py`
  - 负责运行时路径解析、默认路径兜底和运行时配置请求构造
  - 负责 UI 设置在控件与持久化字典之间的同步
- `device_page_controller.py`
  - 负责设备列表刷新、选中项保持和设备相关下拉框同步
  - 负责手动/自动刷新与“当前选中设备”提取等页面级交互编排
- `device_runtime_coordinator.py`
  - 负责路径校验结果到状态栏文本、按钮恢复和首启后续动作触发的编排
  - 负责将首启校验阶段的 UI 状态计算保持为纯协调逻辑
- `device_service_coordinator.py`
  - 负责重启 ADB、清理 ADB 等设备运维动作的提交前 UI 编排
  - 负责操作完成后的进度条隐藏、状态栏文案和安装结果提示收尾
- `file_page_controller.py`
  - 负责文件页刷新、返回上级、双击行为、右键菜单和下载动作编排
  - 负责把文件页控件事件组织为稳定的页面级交互流程
- `file_table_presenter.py`
  - 负责文件表格渲染、文件类型着色、符号链接目标展示和表格内更新
- `widgets.py`
  - 负责可复用的自定义控件，如文件表格项、自动扩展输入框、拖放表格和刷新开关按钮
- `console_actions.py`
  - 负责控制台命令发送前的标准化、冷却触发和发送后清理
- `device_actions.py`
  - 负责启动类动作的前置冷却、状态栏文案和进度条准备编排
  - 负责停止类动作的前置冷却、范围化状态文案和提交后 UI 收尾
- `recording_actions.py`
  - 负责录制启动前的目标校验、音频冲突确认与覆盖处理
- `file_actions.py`
  - 负责文件下载前的本地目录校验、冲突处理与提交前日志
  - 负责批量上传前的重名冲突分发与日志编排

这层的价值是：

- 减少 `main.py` 中重复的字符串、路径和命名分支
- 让 `main.py` 更接近“主窗口总壳 + 生命周期协调”，而不是 UI 搭建脚本
- 避免 `main.py` 直接散落 `QMessageBox` 和 `dialog.exec()` 细节
- 让弹窗操作具备统一主题和可追踪的审计日志
- 让控制台与状态栏提示拥有统一模板来源
- 保持交互行为一致
- 为后续抽离更完整的 UI 协调器类留下空间

## Core Public API

`CoreController` 当前面向 `main.py` 的公开能力，建议按下面几个分区理解：

- 运行时与生命周期
  - `request_configure_runtime(RuntimeConfigurationRequest)`
  - `request_validate_runtime()`
  - `request_prewarm_scrcpy_capabilities()`
  - `request_shutdown()`
- 设备与 ADB
  - `request_refresh_devices()`
  - `request_install_apk()`
  - `request_start_adb_server()`
  - `request_restart_adb()`
  - `request_force_kill_adb()`
- 路由
  - `request_start_audio_route()`
  - `request_start_routing_session(RoutingRequest)`
  - `request_stop_audio_routes()`
  - `request_stop_streaming()`
  - 查询接口 `is_audio_running()`
- 录制
  - `request_start_recording(RecordingRequest)`
  - `request_stop_recording()`
- 文件传输
  - `request_list_device_files(BrowseFilesRequest)`
  - `request_push_file(PushFileRequest)`
  - `request_pull_file(PullFileRequest)`
- 控制台
  - `request_execute_console_target(ConsoleCommandRequest)`

这样划分后，`main.py` 中的调用语义会更稳定：

- `request_*` 统一表示“发起一个动作”
- `is_*` 统一表示“查询当前状态”
- 运行时配置、路由、录制、文件传输、控制台命令这类多参数动作优先通过请求对象进入 `core`
- 内部 service、进程注册表、命令构造器都留在 `core.py` 之后，不再由 UI 直接触达

## Event And Request Contracts

当前主流程中的程序语义通过显式请求对象和事件对象流转，而不是依赖日志展示文案：

- `ConsoleCommandRequest`
  - 使用 `ConsoleTargetKind` 表达目标类型
  - `main.py` 负责把控制台下拉框展示文本映射为语义化目标
  - `core.py` 不再解析 `"[Scrcpy命令]"` 这类 UI 文案
- `RecordingStateEvent`
  - 使用 `RecordingState.STARTED / STOPPED / FAILED`
  - `RecordingService` 发出录制状态事件
  - `main.py` 负责更新状态栏计时、托盘提醒和录制会话表
- `log_message`
  - 仅承担控制台输出与人工可读审计信息
  - 不承担程序控制流判断

## Background Task Observability

当前后台任务统一经过 `app/infrastructure/process/task_runner.py` 中的 `BackgroundTaskRunner` 发起，除了代替裸 `daemon` 线程，还额外承担了轻量任务注册表的职责。

当前能力：

- 为任务记录 `group`、状态、起止时间和异常文本
- 提供 `snapshot()`、`snapshot_by_group()`、`get_task()`、`wait_all()`
- 提供 `recent_failed_tasks()` 和 `clear_history()`
- 通过监听器把失败任务回灌到 `CoreController.log_message`

当前 `CoreController` 暴露的观测接口：

- `get_background_task_snapshot()`
- `get_background_tasks_by_group()`
- `get_recent_background_failures()`
- `clear_background_task_history()`

这意味着：

- UI 层不需要直接管理后台线程对象
- 后台任务失败可以进入统一控制台日志
- 后续如果做“任务状态面板”或调试页，可以直接复用现有观测接口

## Next Refactor Steps

1. 继续减少 `main.py` 中的业务参数拼装代码
2. 逐步把重复的 UI 参数收集整理成请求对象或参数模型
3. 继续把冲突弹窗决策与状态文案生成整理到 UI 协调层
4. 拆分 `main.py` 为主窗口、页面、弹窗、自定义控件
5. 接入 `AudioRouter` 作为标准音频后端

## Design Constraints

- 不破坏现有用户工作流
- 优先做可增量迁移的模块
- 先保证兼容，再做深度解耦
