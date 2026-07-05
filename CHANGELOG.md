# Changelog

本项目所有重要变更都记录在此文件中。

格式基于 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/)，
版本号遵循 [Semantic Versioning](https://semver.org/lang/zh-CN/)。

## [Unreleased]

### Added
- 设备列表项状态指示器：每台设备右侧显示音频(🎵)/视频(🎥)/录制(●)运行状态图标
- `CoreController.get_device_route_status()` 查询接口
- `RouteService.is_video_running()` / `RecordingService.is_recording_running()` 状态查询
- 调试控制台输入框支持随 splitter 拖动变高；执行按钮对齐输入框顶部
- 设备下拉框长名称处理（`AdjustToMinimumContentsLengthWithIcon` + tooltip）
- 开源合规文件：LICENSE、CONTRIBUTING、CODE_OF_CONDUCT、SECURITY、CHANGELOG、Issue/PR 模板

### Changed
- `FileInfo.is_root_owned` 现在识别数字 UID `"0"`（某些 Android 环境 `ls -all` 输出数字 UID）
- `AutoExpandTextEdit` 从 `setFixedHeight` 改为 `setMinimumHeight` + `Expanding` sizePolicy

### Fixed
- 文件传输并发模型从全局串行锁改为按设备分片锁
- 批量上传进度不一致、失败满格进度条问题
- PyInstaller 打包后 `_MEIPASS` 路径解析

## [0.1.0] - 2026-07-05

### Added
- 基于 PyQt6 的桌面控制中心，统一管理 Android 设备的音频路由、视频投屏、录制、文件传输和调试命令
- 图形化设备管理（设备列表、自动刷新、USB 热插拔检测）
- 一键启动音频/视频路由（集成 sndcpy.apk + scrcpy）
- 音视频录制（后台录制，无额外窗口；录制状态栏计时与长时间录制托盘提醒）
- Android 文件浏览、上传、下载（按设备分片锁支持多设备并发传输）
- ADB 命令调试控制台（支持自定义命令、日志记录、上下文菜单）
- 系统托盘驻留（最小化到托盘、托盘图标激活、右键菜单）
- USB 监测不可用时的启动兜底
- 后台任务状态观测与失败日志
- 主动停止录制/视频路由时不再误报异常退出
- 设置持久化到用户可写目录（JSON 格式，自动创建父目录）
- 运行时自动发现系统 VLC 路径
- 预留 AudioRouter 原生音频后端（`-Idummy` 静默运行）
- 内置三平台 vendor 运行时依赖（sndcpy.apk + windows/macos/linux 子目录）
- 跨平台 vendor 路径自动匹配（`sys.platform` → `vendor/<platform>/`）
- `app/` 分层架构（domain / infrastructure / services / ui）
- `CoreController` 统一收口主流程门面
- `BackgroundTaskRunner` 统一收口后台线程并提供观测能力
- 9 个 UI 协调器模块（录制会话、文件传输、设置、设备运维、核心生命周期、控制台日志、启动、关闭、菜单）
- GitHub Actions CI：三平台 AudioRouter 矩阵构建 + Windows 桌面包发行构建
- Dependabot 依赖更新（pip + github-actions，周更）
- 168 项单元测试覆盖核心逻辑

### Infrastructure
- 渐进式重构：顶层 `main.py` 收敛为兼容垫片，`SndcpyGUI` 迁入 `app/ui/main_window.py`
- 打破 `app.main` / `app.bootstrap` / `main.py` 回环依赖
- vendor 二进制入库（`.gitattributes` 标记 binary，macOS/Linux 可执行位 `100755`）
- PyInstaller onefile 打包（`main.spec`，`datas=[vendor]` 内嵌依赖，54.2MB）

[Unreleased]: https://github.com/li589/sndcpypp/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/li589/sndcpypp/releases/tag/v0.1.0
