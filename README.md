# Sndcpy++

Sndcpy++ 是一个基于 Python 和 PyQt6 的桌面控制中心，用于统一管理 Android 设备的音频路由、视频投屏、录制、文件传输和调试命令。

当前项目定位不是从零重写 scrcpy/sndcpy 协议，而是以桌面应用的方式整合 `adb`、`sndcpy`、`scrcpy`、本地播放器，并逐步演进到更稳定的设备会话管理与可替换的音频后端。

## 当前能力

- 图形化设备管理
- 一键启动音频/视频路由
- 音视频录制
- 录制始终后台进行，不会为录制额外弹出新窗口
- 录制状态栏计时与长时间录制托盘提醒
- Android 文件浏览、上传、下载
- ADB 命令调试控制台
- 系统托盘驻留
- USB 热插拔自动检测
- USB 监测不可用时的启动兜底
- 后台任务状态观测与失败日志
- 主动停止录制/视频路由时不再误报异常退出
- 设置文件自动写入用户可写目录
- 运行时默认优先自动发现系统 VLC 路径
- 预留 `AudioRouter` 原生音频后端
- 内置三平台 vendor 运行时依赖，便于直接打包发行

## 当前状态

当前链路依赖：

- 设备端：`sndcpy.apk`
- 视频端：`scrcpy.exe`
- 音频端：`VLC` 或未来的 `AudioRouter`

本仓库目前处于渐进式重构中，已经完成的重点包括：

- 建立 `app/` 分层结构
- 抽离领域模型、服务层与 UI 协调层
- 用 `CoreController` 统一收口主流程门面
- 用 `BackgroundTaskRunner` 统一收口后台线程并提供观测能力
- 将 USB 监听实现迁移到 `app/infrastructure/adb/UsbMonitor.py`
- 让录制状态与控制台目标切换使用显式事件/请求模型，而不是依赖展示文案
- 为录制与视频路由补上显式“主动停止”标记，避免 watcher 误报失败或异常退出
- 将设置持久化迁移到用户目录，并在保存前自动创建父目录
- 运行时默认播放器路径支持自动搜索系统 `VLC`

## 目录说明

```text
app/            新增的重构代码与分层骨架
docs/           架构与设计文档
AudioRouter/    C++ 原生音频接收/播放实验项目（跨平台，三平台均原生编译）
vendor/         跨平台外部二进制依赖（sndcpy.apk + windows/macos/linux 子目录）
main.py         现有 GUI 主入口（兼容垫片，已迁移到 app/ui/main_window.py）
core.py         现有后端控制核心
app/infrastructure/adb/UsbMonitor.py   USB 监听通用模块
```

> vendor/ 目录结构：
> - `vendor/sndcpy.apk` —— 平台无关，从 [rom1v/sndcpy](https://github.com/rom1v/sndcpy/releases) 下载
> - `vendor/windows/` —— `adb.exe` / `scrcpy.exe` / `*.dll`
> - `vendor/macos/` —— `adb` / `scrcpy`
> - `vendor/linux/` —— `adb` / `scrcpy`
>
> 代码会按 `sys.platform` 自动选对应子目录，详见 `app/infrastructure/adb/path_resolver.py` 的 `get_platform_vendor_subdir()`。

## 依赖

运行时依赖见 `requirements.txt`：

- `PyQt6==6.9.0`
- `WMI==1.5.1`
- `pywin32==311`
- `pyusb==1.3.1`

打包依赖已固定在 `requirements.txt`：

- `pyinstaller==6.19.0`

Dependabot 会每周检查 pip 依赖和 GitHub Actions 版本。

## 安装依赖

PowerShell:

```powershell
.\venv\Scripts\python.exe -m pip install -r requirements.txt
```

如果你使用自己的 Python 环境：

```powershell
python -m pip install -r requirements.txt
```

## 运行方式

当前桌面程序入口：

```bash
python main.py
```

包方式入口：

```bash
python -m app.main
```

## 发行构建

推送 `v*` tag 会触发 GitHub Actions：

- `Build Desktop App (Windows)`：构建 `sndcpypp-windows-x64.zip`
- `Build AudioRouter (cross-platform)`：构建三平台 AudioRouter 产物

本地 Windows 打包：

```powershell
.\venv\Scripts\python.exe -m PyInstaller main.spec --clean --noconfirm
```

产物位于 `dist/sndcpypp.exe`。

## 最小验证

静态编译检查：

```powershell
.\venv\Scripts\python.exe -m compileall .\main.py .\core.py .\app .\tests
```

启动主程序：

```powershell
.\venv\Scripts\python.exe main.py
```

建议最小手工检查项：

- 主窗口是否正常打开
- 托盘图标是否出现
- 四个页面是否都能切换
- 无设备状态下是否不会报错
- 路径验证按钮是否可点击
- 文件页表格与控制台输入区是否正常初始化
- 默认播放器路径是否能自动解析到系统 `VLC`
- 设置修改后重启程序是否仍能保留

## 当前验证状态

当前仓库已经完成以下验证：

- `main.py`、`core.py`、`app/`、`tests/` 的编译检查
- `49` 项 `unittest` 回归测试
- 设备页、文件页、运行时设置、设备运维协调层的纯逻辑测试
- 主窗口构造与 USB 监听失败兜底测试
- 后台任务观测、失败记录与历史清理测试
- 录制后台无窗口、录制状态事件与长时间录制提醒测试
- 路由进程立即退出、主动停止不误报警告、设备特定音频端口恢复测试
- ADB 设备刷新重试、批量上传重名冲突、下载缓存转移失败测试
- 设置目录自动创建与用户目录默认路径测试

当前尚未覆盖的部分：

- 真实 Android 设备连接下的 `adb devices`
- `sndcpy.apk` 安装与启动
- 音频/视频路由
- 录制开始/停止与真机录制文件产出
- 真机文件上传下载

## 重构方向

- 第一阶段：完成分层抽离、核心门面收口和主窗口瘦身
- 第二阶段：继续减少 `main.py` 中剩余的参数拼装与接线代码
- 第三阶段：接入 `AudioRouter` 作为标准音频后端
- 第四阶段：评估 Android 端自研音频采集服务

## 相关文档

- `docs/architecture.md`

## License

待补充。
