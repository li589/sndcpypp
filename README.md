# Sndcpy++

Sndcpy++ 是一个基于 Python 和 PyQt6 的桌面控制中心，用于统一管理 Android 设备的音频路由、视频投屏、录制、文件传输和调试命令。

当前项目定位不是从零重写 scrcpy/sndcpy 协议，而是以桌面应用的方式整合 `adb`、`sndcpy`、`scrcpy`、本地播放器，并逐步演进到自研音频播放与更稳定的设备会话管理。

## 当前能力

- 图形化设备管理
- 一键启动音频/视频路由
- 音视频录制
- Android 文件浏览、上传、下载
- ADB 命令调试控制台
- 系统托盘驻留
- USB 热插拔自动检测
- 预留 `AudioRouter` 原生音频后端

## 当前状态

当前链路依赖：

- 设备端：`sndcpy.apk`
- 视频端：`scrcpy.exe`
- 音频端：`VLC` 或未来的 `AudioRouter`

本仓库正在进行第一阶段重构，目标包括：

- 建立 `app/` 分层结构
- 抽离领域模型与命令构建逻辑
- 保留现有运行方式兼容
- 后续逐步拆分 `main.py` 与 `core.py`
- 保持 `UsbMonitor.py` 原文件不拆分，方便外部复用

## 目录说明

```text
app/            新增的重构代码与分层骨架
docs/           架构与设计文档
AudioRouter/    C++ 原生音频接收/播放实验项目
Sndcpy/         adb/scrcpy/sndcpy.apk 等运行资源
main.py         现有 GUI 主入口
core.py         现有后端控制核心
UsbMonitor.py   保留的 USB 监听通用模块
```

## 依赖

运行时依赖见 `requirements.txt`：

- `PyQt6==6.9.0`
- `WMI==1.5.1`
- `pywin32==311`
- `pyusb==1.3.1`

可选打包依赖：

- `pyinstaller==6.19.0`

建议优先使用仓库自带虚拟环境 `venv/`，或自行创建新的虚拟环境后安装依赖。

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

兼容旧入口：

```bash
python main.py
```

新增重构入口：

```bash
python -m app.main
```

## 最小验证

静态编译检查：

```powershell
.\venv\Scripts\python.exe -m py_compile main.py core.py UsbMonitor.py
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

## 当前验证状态

当前仓库已经完成以下验证：

- `main.py`、`core.py`、`UsbMonitor.py` 与 `app/` 下重构模块的语法编译检查
- 四个页面组件的实例化冒烟测试
- 主窗口构造与延迟初始化测试
- 托盘隐藏、恢复显示、强制退出链路测试

当前尚未覆盖的部分：

- 真实 Android 设备连接下的 `adb devices`
- `sndcpy.apk` 安装与启动
- 音频/视频路由
- 录制开始/停止
- 真机文件上传下载

## 重构方向

- 第一阶段：抽离模型、命令构建、入口骨架和文档
- 第二阶段：拆分设备、音频、视频、录制、文件传输服务
- 第三阶段：接入 `AudioRouter` 作为默认播放器后端
- 第四阶段：评估 Android 端自研音频采集服务

## 相关文档

- `docs/architecture.md`

## License

待补充。
