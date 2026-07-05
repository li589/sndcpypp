# Security Policy

## Supported Versions

本项目处于早期开发阶段，仅对最新发布版本提供安全更新。

| Version | Supported          |
| ------- | ------------------ |
| latest  | :white_check_mark: |
| < 1.0   | :x:                |

## Reporting a Vulnerability

如果你发现安全漏洞，**请不要在 GitHub Issue 中公开报告**。

请通过以下方式私密报告：

1. 使用 GitHub 的 [私密安全报告](https://github.com/li589/sndcpypp/security/advisories/new) 功能
2. 或发送邮件至仓库所有者（在 GitHub profile 页面查看邮箱）

报告时请包含：

- 漏洞的清晰描述
- 复现步骤（最小化复现案例）
- 影响范围评估
- 如果有修复建议，请一并附上

## Response Timeline

- **确认收到**：3 个工作日内
- **初步评估**：7 个工作日内
- **修复发布**：根据严重程度，30 天内发布补丁版本

## Scope

以下属于安全漏洞范围：

- ADB 命令注入（用户输入未经过滤直接拼接到 shell 命令）
- 文件传输路径穿越（任意文件写入/覆盖）
- 进程逃逸（通过恶意设备触发执行任意命令）
- 敏感信息泄露（设备 serial、文件路径等日志输出到非预期位置）

以下不属于安全漏洞：

- 需要 physical access 设备的攻击
- 社会工程学
- DoS 攻击（除非可通过单个恶意设备触发）
- ADB 本身的安全限制（这是 Android 平台的设计行为）
