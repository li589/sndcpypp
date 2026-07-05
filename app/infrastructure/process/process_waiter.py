"""进程退出等待公共逻辑。

从 route_service / recording_service / file_manager_service 三处
去重的 _wait_for_process_exit 实现。
"""

import time
from collections.abc import Callable

from app.infrastructure.config.constants import PROCESS_POLL_INTERVAL, PROCESS_SHUTDOWN_GRACE_SECONDS


def wait_for_process_exit(
    proc,
    *,
    is_running: Callable[[], bool],
    poll_interval: float = PROCESS_POLL_INTERVAL,
    shutdown_grace_seconds: float = PROCESS_SHUTDOWN_GRACE_SECONDS,
    on_shutdown_timeout: Callable[[], None] | None = None,
) -> int | None:
    """等待子进程退出，支持优雅关闭与强制终止回调。

    流程:
      1. 轮询 proc.poll() 直到进程退出或 is_running() 返回 False
      2. 进入优雅关闭窗口 (shutdown_grace_seconds / poll_interval 次轮询)
      3. 优雅窗口超时后调用 on_shutdown_timeout (通常是 kill_group)
      4. 强制关闭后再等同样的窗口
      5. 返回最终 return_code (可能为 None 如果进程仍未退出)
    """
    while True:
        return_code = proc.poll()
        if return_code is not None:
            return return_code
        if not is_running():
            break
        time.sleep(poll_interval)

    grace_checks = max(1, int(shutdown_grace_seconds / poll_interval))
    for _ in range(grace_checks):
        return_code = proc.poll()
        if return_code is not None:
            return return_code
        time.sleep(poll_interval)

    if on_shutdown_timeout is not None:
        on_shutdown_timeout()

    for _ in range(grace_checks):
        return_code = proc.poll()
        if return_code is not None:
            return return_code
        time.sleep(poll_interval)
    return proc.poll()
