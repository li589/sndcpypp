# 贡献指南

感谢你对 sndcpy++ 项目的兴趣！本文档指导你如何参与贡献。

## 行为准则

参与本项目即代表你同意遵守 [Code of Conduct](CODE_OF_CONDUCT.md)。请在所有交流中保持尊重和友善。

## 开发环境搭建

### 前置要求

- Python 3.12+
- Git
- Windows / macOS / Linux 桌面环境
- 一台 Android 设备（可选，用于真机测试）

### 搭建步骤

```bash
# 1. 克隆仓库
git clone https://github.com/li589/sndcpypp.git
cd sndcpypp

# 2. 创建虚拟环境
python -m venv venv

# Windows
.\venv\Scripts\activate
# macOS / Linux
source venv/bin/activate

# 3. 安装依赖
pip install -r requirements.txt

# 4. 验证安装
python -m unittest discover -s tests -v
```

### vendor 依赖

项目运行需要 `vendor/` 目录下的外部二进制（sndcpy.apk、adb、scrcpy、AudioRouter）。详见 [vendor/README.md](vendor/README.md)。

首次克隆后需要手动下载 `sndcpy.apk` 放到 `vendor/` 顶层：

```bash
# 从 rom1v/sndcpy releases 下载 sndcpy.apk
# https://github.com/rom1v/sndcpy/releases
# 放到 vendor/sndcpy.apk
```

平台二进制（adb、scrcpy）已入库，无需额外下载。

## 运行测试

```bash
# 全量测试
python -m unittest discover -s tests -v

# 编译检查
python -m compileall .\main.py .\core.py .\app .\tests

# 启动主程序
python main.py
```

## 代码风格

### Python

- 遵循 [PEP 8](https://peps.python.org/pep-0008/)
- 使用 4 空格缩进
- 行宽不超过 120 字符
- 公开函数和方法应有类型注解（参数 + 返回值）
- 模块级文档字符串用中文，代码注释可中英混用

### 架构约定

项目采用分层架构，详见 [docs/architecture.md](docs/architecture.md)：

```
app/
├── domain/          领域模型（纯数据结构，无副作用）
├── infrastructure/  基础设施（ADB、文件解析、进程管理、配置）
├── services/        服务层（业务逻辑编排）
└── ui/              UI 层（PyQt6 窗口、协调器、页面）
```

关键约定：

- **UI 协调器模式**：特定功能的 UI 协调逻辑应抽取到 `app/ui/` 下的独立协调器模块
- **请求对象**：请求构造方法集中在 `app/ui/request_builders.py`
- **日志**：库代码必须使用 `log_to_console` 回调，不得直接 `print()`
- **核心生命周期**：`CoreController` 的生命周期通过 `core_lifecycle_coordinator.py` 管理
- **vendor 路径**：平台分流统一用 `path_resolver.py::get_platform_vendor_subdir()`，不在业务代码里重复 `sys.platform` 判断
- **并发锁**：文件传输按设备分片锁，不使用全局锁

### 提交规范

使用 [Conventional Commits](https://www.conventionalcommits.org/) 格式：

```
<type>(<scope>): <description>

[optional body]

[optional footer]
```

常用 type：

- `feat`：新功能
- `fix`：bug 修复
- `refactor`：重构（不改行为）
- `test`：测试相关
- `docs`：文档
- `chore`：构建、依赖、配置等杂项
- `ci`：CI/CD

示例：

```
feat(ui): 设备列表项显示路由/录制状态指示器

每台设备右侧显示音频(🎵)/视频(🎥)/录制(●)图标，
通过 2 秒定时器 + 关键操作点延迟刷新保持状态同步。
```

## 提交 Pull Request

1. **Fork 仓库** 并创建特性分支：

   ```bash
   git checkout -b feat/your-feature
   ```

2. **编写代码**，确保：
   - 通过全量测试（`python -m unittest discover -s tests -v`）
   - 通过编译检查（`python -m compileall`）
   - 新功能有对应测试
   - 遵循架构约定和代码风格

3. **提交**，使用 Conventional Commits 格式

4. **推送** 并创建 Pull Request：
   - 标题简洁描述变更
   - 在 PR 描述中说明：改了什么、为什么改、如何测试
   - 关联相关 Issue（`Closes #123`）

5. **等待 Review**，根据反馈调整

## 报告 Bug / 提功能建议

- 使用 GitHub Issue
- Bug 报告请包含：复现步骤、预期行为、实际行为、环境信息（OS、Python 版本、设备型号）
- 功能建议请说明使用场景和期望效果

## 许可证

贡献的代码将在 [MIT License](LICENSE) 下发布。提交 PR 即表示你同意该许可。
