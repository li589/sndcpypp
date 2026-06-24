from dataclasses import dataclass
from datetime import datetime

FILE_MENU_ENTER_FOLDER = "📂 进入文件夹"
FILE_MENU_DOWNLOAD_FOLDER = "⬇️ 下载整个文件夹"
FILE_MENU_DOWNLOAD_FILE = "⬇️ 下载文件"
FILE_MENU_COPY_NAME = "📋 复制名称"
FILE_MENU_COPY_FULL_PATH = "📋 复制完整路径"
FILE_MENU_COPY_LINK_TARGET = "📋 复制链接目标"
TRAY_MENU_MINIMIZE_ALL = "最小化所有窗口"
TRAY_MENU_SHOW_MAIN = "显示主界面"
TRAY_MENU_HIDE_TO_TRAY = "仅关闭 (隐藏至托盘)"
TRAY_MENU_EXIT = "完全退出"
WINDOW_MENU_MINIMIZE_ALL = "最小化所有窗口"
WINDOW_MENU_HIDE_TO_TRAY = "仅关闭 (隐藏到托盘)"
CONSOLE_MENU_CLEAR_LOGS = "清空控制台日志"
CONSOLE_MENU_EXPORT_LOGS = "导出全部日志..."


@dataclass(frozen=True)
class ConsoleRenderSpec:
    prefix: str
    color: str


CONSOLE_RENDER_SPECS = {
    "info": ConsoleRenderSpec("[信息]", "#CCCCCC"),
    "error": ConsoleRenderSpec("[错误]", "#FF5555"),
    "success": ConsoleRenderSpec("[成功]", "#55FF55"),
    "command": ConsoleRenderSpec("[命令]", "#FFAA00"),
    "output": ConsoleRenderSpec("[输出]", "#AAAAFF"),
    "warning": ConsoleRenderSpec("[警告]", "#FFAA00"),
    "popup": ConsoleRenderSpec("[弹窗]", "#7DCFFF"),
}


def validation_status_text(adb_valid: bool, player_valid: bool, sndcpy_valid: bool) -> str:
    return (
        f"路径验证: ADB {'有效' if adb_valid else '无效'} | "
        f"播放器 {'有效' if player_valid else '无效'} | "
        f"sndcpy {'有效' if sndcpy_valid else '无效'}"
    )


def device_count_status_text(device_count: int) -> str:
    return f"找到 {device_count} 台设备" if device_count else "未找到设备"


def window_menu_toggle_top_label(is_top: bool) -> str:
    return "取消置顶" if is_top else "窗口置顶"


def scoped_status_text(
    device_serial: str | None,
    device_template: str,
    all_devices_text: str,
) -> str:
    if device_serial:
        return device_template.format(device=device_serial)
    return all_devices_text


def status_installing(device_serial: str) -> str:
    return f"正在安装到设备: {device_serial}..."


def status_routing_submitted(device_serial: str) -> str:
    return f"已提交路由后台任务 (设备: {device_serial})..."


def status_audio_route_submitted(device_serial: str) -> str:
    return f"已提交独立音频启动任务 (设备: {device_serial})..."


def status_recording_cancelled(reason: str = "用户取消") -> str:
    return f"录制已取消（{reason}）"


def status_recording_preparing(device_serial: str) -> str:
    return f"正在准备录制 ({device_serial})..."


def status_recording_active(device_serial: str, elapsed_text: str) -> str:
    return f"正在录制 ({device_serial}) {elapsed_text}"


def status_recording_active_multi(device_count: int, elapsed_text: str) -> str:
    return f"正在录制 {device_count} 台设备，最长已录制 {elapsed_text}"


def status_recording_finished(device_serial: str) -> str:
    return f"录制已结束并保存完成 ({device_serial})"


def status_recording_failed(device_serial: str) -> str:
    return f"录制启动失败 ({device_serial})"


def status_adb_restart_submitted() -> str:
    return "ADB 重启指令已发送，正在后台处理..."


def status_adb_cleanup_running() -> str:
    return "正在后台执行 ADB 清理操作..."


def status_usb_refresh_pending() -> str:
    return "检测到 USB 硬件变动，即将静默刷新设备..."


def status_operation_result(operation: str, success: bool) -> str | None:
    if operation == "install":
        return "APK安装成功" if success else "APK安装失败"
    if operation == "audio_route":
        return "音频路由启动成功" if success else "音频路由启动失败"
    if operation == "video_route":
        return "画面路由启动成功" if success else "画面路由启动失败"
    return None


def file_list_summary(dir_count: int, file_count: int, link_count: int) -> str:
    summary_parts: list[str] = []
    if dir_count > 0:
        summary_parts.append(f"📁 {dir_count} 文件夹")
    if file_count > 0:
        summary_parts.append(f"📄 {file_count} 文件")
    if link_count > 0:
        summary_parts.append(f"🔗 {link_count} 链接")
    return " | ".join(summary_parts) if summary_parts else "空目录"


def file_status_read_failed() -> str:
    return "读取失败"


def log_initial_validation() -> str:
    return "正在执行初始路径验证..."


def log_usb_monitor_started() -> str:
    return "USB热插拔事件监听已启动"


def log_usb_monitor_init_failed(error_text: str) -> str:
    return f"USB热插拔监听初始化失败: {error_text}"


def log_usb_monitor_start_failed(error_text: str) -> str:
    return f"USB热插拔监听启动失败，已跳过后台监测: {error_text}"


def log_background_task_failed(group: str, name: str, error_text: str | None) -> str:
    detail = error_text or "未知错误"
    return f"后台任务失败 [{group}] {name}: {detail}"


def log_adb_resolution_fallback(source: str, path: str) -> str:
    return f"指定的 ADB 不可用，已自动回退到 {source}: {path}"


def log_adb_resolution_builtin(path: str) -> str:
    return f"ADB 当前使用内置版本: {path}"


def log_adb_resolution_external(source: str, path: str) -> str:
    return f"ADB 当前使用{source}: {path}"


def log_adb_resolution_unresolved(path: str) -> str:
    return f"ADB 路径尚未解析成功，将继续按当前配置尝试: {path}"


def log_extra_params_updated(title: str) -> str:
    return f"已更新 {title} 附加参数。"


def log_auto_validation_starting_adb() -> str:
    return "自动验证通过，正在启动ADB..."


def log_listing_path(path: str) -> str:
    return f"正在列出: {path}"


def log_upload_skipped(target_name: str) -> str:
    return f"已跳过上传: {target_name}"


def log_upload_preparing(target_name: str, rename_to: str | None = None) -> str:
    suffix = f" (已重命名为 {rename_to})" if rename_to else ""
    return f"准备上传: {target_name}{suffix}"


def log_loaded_items(count: int, path: str) -> str:
    return f"已加载 {count} 个项目于 {path}"


def log_symlink_resolved(name: str, is_dir: bool) -> str:
    return f"符号链接已解析: {name} → {'目录' if is_dir else '文件'}"


def log_download_preparing(name: str, size_display: str, type_description: str) -> str:
    return f"准备下载文件: {name} | 大小: {size_display} | 类型: {type_description}"


def log_symlink_unavailable(name: str) -> str:
    return f"该链接的目标状态尚未探测完成或不可用: {name}"


def symlink_type_text(is_dir: bool) -> str:
    return "🔗 目录" if is_dir else "🔗 文件"


def symlink_target_display(target: str, is_dir: bool) -> str:
    return target + (" (目录)" if is_dir else " (文件)")


def log_download_skipped(name: str) -> str:
    return f"已跳过下载: {name}"


def log_pull_from_device(desc: str, target_name: str, rename_to: str | None = None) -> str:
    suffix = f" (另存为 {rename_to})" if rename_to else ""
    return f"正在从设备拉取{desc}：{target_name}{suffix}"


def log_settings_save_failed(error_text: str) -> str:
    return f"保存设置失败: {error_text}"


def log_settings_load_warning(message: str) -> str:
    return f"加载设置告警: {message}"


def log_cleanup_processes() -> str:
    return "正在清理后台进程，请稍候..."


def tray_hidden_title() -> str:
    return "Sndcpy++"


def tray_hidden_message() -> str:
    return "已隐藏至系统托盘，后台服务保持运行中"


def tray_recording_reminder_title() -> str:
    return "Sndcpy++ 录制提醒"


def tray_recording_reminder_message(device_serial: str, elapsed_text: str) -> str:
    return f"设备 {device_serial} 已连续录制 {elapsed_text}。当前未检测到全屏窗口，请留意录制状态。"


def render_console_html(message: str, msg_type: str, timestamp: datetime) -> str:
    spec = CONSOLE_RENDER_SPECS.get(msg_type, CONSOLE_RENDER_SPECS["info"])
    safe_message = (
        message.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace("\n", "<br>")
    )
    time_text = timestamp.strftime("%H:%M:%S")
    return (
        f'<span style="color: #AAAAAA;">[{time_text}]</span> '
        f'<span style="color: {spec.color};">{spec.prefix} {safe_message}</span><br>'
    )
