import threading
from typing import Any


class ProcessRegistry:
    def __init__(self):
        self._registry: dict[str, dict[str, Any]] = {}
        self._registry_lock = threading.RLock()

    def ensure(self, device_serial: str) -> dict[str, Any]:
        with self._registry_lock:
            if device_serial not in self._registry:
                self._registry[device_serial] = {
                    "video": [],
                    "audio": [],
                    "record": [],
                    "transfer": [],
                    "lock": threading.RLock(),
                }
            elif "lock" not in self._registry[device_serial]:
                self._registry[device_serial]["lock"] = threading.RLock()
            return self._registry[device_serial]

    def register(self, device_serial: str, group: str, proc: Any):
        reg = self.ensure(device_serial)
        with reg["lock"]:
            if group in reg:
                reg[group] = [
                    existing for existing in reg[group]
                    if getattr(existing, "poll", lambda: 0)() is None
                ]
                reg[group].append(proc)

    def keys(self):
        with self._registry_lock:
            return list(self._registry.keys())
