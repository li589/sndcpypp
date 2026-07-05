import contextlib
import os
import signal
import subprocess
import time
from typing import Any

from app.infrastructure.process.registry import ProcessRegistry


class ProcessSupervisor:
    def __init__(self, registry: ProcessRegistry):
        self.registry = registry

    def kill_group(self, device_serial: str, group: str):
        flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
        reg = self.registry.ensure(device_serial)
        with reg["lock"]:
            procs = list(reg.get(group, []))
        for proc in procs:
            if proc.poll() is None:
                try:
                    if group == "record":
                        if os.name == "nt":
                            with contextlib.suppress(Exception):
                                os.kill(proc.pid, getattr(signal, "CTRL_BREAK_EVENT", 1))
                            with contextlib.suppress(Exception):
                                os.kill(proc.pid, getattr(signal, "CTRL_C_EVENT", 0))
                            subprocess.run(
                                ["taskkill", "/PID", str(proc.pid)],
                                creationflags=subprocess.CREATE_NO_WINDOW,
                                capture_output=True,
                            )
                        else:
                            proc.send_signal(signal.SIGINT)
                        for _ in range(30):
                            if proc.poll() is not None:
                                break
                            time.sleep(0.5)

                    if proc.poll() is None:
                        if os.name == "nt":
                            subprocess.run(
                                ["taskkill", "/F", "/T", "/PID", str(proc.pid)],
                                creationflags=flags,
                                capture_output=True,
                            )
                        else:
                            proc.kill()
                except Exception:
                    pass
        with reg["lock"]:
            if group in reg:
                reg[group].clear()

    def remove_if_present(self, device_serial: str, group: str, proc: Any):
        reg = self.registry.ensure(device_serial)
        with reg["lock"]:
            if proc in reg.get(group, []):
                reg[group].remove(proc)
