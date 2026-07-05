from dataclasses import dataclass
from datetime import datetime

from PyQt6.QtCore import QCoreApplication


def tr(text: str, context: str = "messages") -> str:
    """i18n 辅助函数：包装 QCoreApplication.translate()。

    pylupdate6 不会提取通过自定义函数调用的字符串，因此本函数仅用于
    在运行时查找翻译。.ts 文件需通过 pylupdate6 扫描源码中的
    QCoreApplication.translate() 调用生成。
    """
    return QCoreApplication.translate(context, text)


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
    return f"ADB 当前使用内置 vendor: {path}"


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
    safe_message = message.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace("\n", "<br>")
    time_text = timestamp.strftime("%H:%M:%S")
    return (
        f'<span style="color: #AAAAAA;">[{time_text}]</span> '
        f'<span style="color: {spec.color};">{spec.prefix} {safe_message}</span><br>'
    )


# --- Popup titles ---
POPUP_TITLE_AUDIO_CONFLICT = "音频冲突警告"
POPUP_TITLE_FILE_EXISTS = "文件已存在"
POPUP_TITLE_PLAYER_EXIT = "播放器意外退出"
POPUP_TITLE_SUCCESS = "成功"
POPUP_TITLE_ERROR = "错误"
POPUP_TITLE_WARNING = "警告"
POPUP_TITLE_FAILURE = "失败"

# --- Popup messages ---
POPUP_MSG_EXPORT_LOGS_SUCCESS = "日志已成功导出！"


def popup_msg_export_logs_failure(error_text: str) -> str:
    return f"日志导出失败: {error_text}"


POPUP_MSG_DEVICE_REQUIRED = "请先在设备列表选择一个已经连接的设备"
POPUP_MSG_RECORDING_DEVICE_REQUIRED = "请先选择一个已经连接的设备！"
POPUP_MSG_RECORDING_TARGET_REQUIRED = "请至少选择录制视频或录制音频中的一项！"
POPUP_MSG_RECORD_DIRECTORY_INVALID = "保存目录不存在！"


def popup_msg_record_overwrite_failed(error_text: str) -> str:
    return f"无法覆盖原文件，它可能正在被占用。\n{error_text}"


POPUP_MSG_DOWNLOAD_DIRECTORY_INVALID = "本地下载目录无效，请检查下载路径！"
POPUP_MSG_SNDCPY_INSTALL_SUCCESS = "SNDCPY安装成功"
POPUP_MSG_SNDCPY_INSTALL_FAILED = "SNDCPY安装失败"

# --- Param settings dialog ---
CMD_SETTINGS_TITLES = {"adb": "ADB", "player": "播放器", "scrcpy": "Scrcpy"}
POPUP_AUDIOROUTER_QUICK_FILL_LABEL = "AudioRouter 推荐"


def param_settings_dialog_title(title: str) -> str:
    return f"{title} 附加参数设置"


def param_settings_dialog_label(param_name: str) -> str:
    return f"输入 {param_name} 附加命令行参数 (空格分隔)："


# --- Exit confirm dialog ---
EXIT_DIALOG_TITLE = "退出确认"
EXIT_DIALOG_MESSAGE = "您点击了关闭按钮，请选择您的操作："
EXIT_DIALOG_BTN_TRAY = "仅隐藏到托盘\n(保持后台路由运行)"
EXIT_DIALOG_BTN_EXIT = "完全退出程序\n(彻底结束所有投屏)"
DIALOG_BTN_CANCEL = "取消"
DIALOG_BTN_OK = "确定保存"
DIALOG_LABEL_QUICK_FILL = "快捷填充:"

# --- File conflict dialog ---
DIALOG_BTN_OVERWRITE = "覆盖替换"
DIALOG_BTN_RENAME = "自动重命名"
DIALOG_BTN_SKIP = "跳过"


def file_conflict_dialog_title(is_upload: bool) -> str:
    op = "上传" if is_upload else "下载"
    return f"文件冲突 ({op})"


def file_conflict_dialog_message(filename: str) -> str:
    return f"<b>目标位置已存在同名项目：</b><br><br>{filename}<br><br>请选择操作："


# --- adb_device_service log messages ---
def log_sndcpy_not_found_in_dir() -> str:
    return tr("在目录中未找到 sndcpy.apk 或 scrcpy 核心文件")


def log_vendor_dir_invalid() -> str:
    return tr("vendor 目录无效")


def log_device_refresh_failed_retrying() -> str:
    return tr("设备刷新失败，等待后直接重试设备枚举...")


def log_device_refresh_failed_ignored() -> str:
    return tr("设备刷新失败，本次结果已忽略。")


def log_adb_just_started_retrying() -> str:
    return tr("ADB 刚启动完成，等待设备枚举后自动重试...")


def log_retry_install_after_uninstall() -> str:
    return tr("尝试卸载旧版本并重新安装...")


def log_sndcpy_already_installed_skipped() -> str:
    return tr("设备中已存在 sndcpy，跳过重复安装。")


def log_awaiting_install_confirmation() -> str:
    return tr("安装结果尚未明确，正在等待手机端确认安装...")


def log_force_killing_adb_processes() -> str:
    return tr("正在强制结束 ADB 进程池...")


def log_kill_adb_access_denied() -> str:
    return tr("结束失败：拒绝访问！请【以管理员身份运行本程序】。")


def log_adb_cleanup_completed() -> str:
    return tr("ADB 进程清理指令执行完毕。")


def log_starting_adb_server() -> str:
    return tr("正在唤起 ADB 并枚举设备...")


def log_adb_restart_submitted_restarting() -> str:
    return tr("ADB服务重启指令已发送，正在重新枚举设备")


def log_device_enumeration_no_devices() -> str:
    return tr("设备枚举完成: 当前没有在线设备")


# --- route_service log messages ---
def log_await_screen_capture_auth() -> str:
    return tr("若手机弹出录屏授权，请先在手机上确认，画面窗口会在授权后出现。")


def log_one_click_serial_video_first() -> str:
    return tr("一键路由已切换为串行启动，正在优先建立画面链路。")


def log_video_link_stable_starting_audio() -> str:
    return tr("画面链路已稳定，开始建立音频链路。")


def log_all_streams_force_stopped() -> str:
    return tr("已彻底强制结束所有设备的流媒体路由")


# --- recording_service log messages ---
def log_pause_audio_route_before_recording() -> str:
    return tr("检测到音频路由正在运行，为避免冲突将先暂停...")


def log_recording_ended_restoring_audio() -> str:
    return tr("录制已结束，正在尝试恢复之前的音频路由...")


def log_recording_finished_awaiting_mux() -> str:
    return tr("录制已结束保存 (等待后台封包完成)")


# --- file_manager_service log messages ---
def log_read_directory_failed() -> str:
    return tr("读取目录失败 (可能无权限或路径错误)")


# --- core.py log messages ---
def log_adb_controller_safely_stopped() -> str:
    return tr("ADB控制器已安全停止")


# --- UI text ---
def window_title_text() -> str:
    return tr("Android音画路由控制中心")


def root_owned_tooltip_text() -> str:
    return tr("Root 所有 - 跨界操作可能受限")


def audio_route_active_tooltip(active: bool) -> str:
    return tr("音频路由中") if active else ""


def video_route_active_tooltip(active: bool) -> str:
    return tr("视频路由中") if active else ""


def recording_active_tooltip(active: bool) -> str:
    return tr("录制中") if active else ""


def recording_bg_check_tooltip_text() -> str:
    return tr("录制会始终复用后台模式；即使已打开 Scrcpy 路由窗口，也不会再为录制弹出新窗口。")


def audio_bitrate_spinbox_tooltip_text() -> str:
    return tr("当前 sndcpy + VLC 链路不支持在此调整音频比特率，该值不会生效。")


def audio_bitrate_label_tooltip_text() -> str:
    return tr("当前 sndcpy + VLC 链路不支持在此调整音频比特率。")
