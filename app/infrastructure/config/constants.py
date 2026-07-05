"""项目运行时常量集中定义。

消除散落在多个文件中的魔法数字（端口、超时、轮询间隔等）。
所有需要跨模块共享的运行时常量都应定义在此处。
"""

# ───────────────── 音频路由 ─────────────────

#: sndcpy 默认音频转发端口
DEFAULT_AUDIO_PORT: int = 28200

# ───────────────── 进程等待与轮询 ─────────────────

#: 轮询子进程退出状态的间隔（秒）
PROCESS_POLL_INTERVAL: float = 0.2

#: 主动停止子进程后的优雅等待窗口（秒）
PROCESS_SHUTDOWN_GRACE_SECONDS: float = 3.0

#: 子进程启动后等待稳定的窗口（秒）
PROCESS_STABLE_SECONDS: float = 3.0

#: 音视频路由启动后的强制等待（秒），确保进程就绪
ROUTE_STARTUP_WAIT_SECONDS: float = 1.0

# ───────────────── ADB 命令超时 ─────────────────

#: ADB 普通命令默认超时（秒）
ADB_DEFAULT_TIMEOUT: float = 15.0

# ───────────────── 文件操作 ─────────────────

#: symlink 探测超时（秒）
SYMLINK_RESOLVE_TIMEOUT: int = 5

# ───────────────── 视频路由回退阈值 ─────────────────

#: 视频码率回退上限（kbps）
VIDEO_FALLBACK_BITRATE: int = 4000

#: 视频最大尺寸回退值
VIDEO_FALLBACK_MAX_SIZE: str = "1280"

# ───────────────── VLC 网络缓存 ─────────────────

#: VLC 网络缓存（毫秒）
VLC_NETWORK_CACHING_MS: int = 200
