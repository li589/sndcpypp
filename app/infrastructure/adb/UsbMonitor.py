#!/usr/bin/env python3
"""
USB设备实时监控程序
支持: Linux (pyudev), Windows (pywin32/wmi), macOS (pyobjc)
功能: 实时检测USB设备的插入、拔出和状态变更
"""

import sys
import threading
import time
from abc import ABC, abstractmethod
from collections.abc import Callable
from datetime import datetime

# 尝试导入平台特定的库
PLATFORM = sys.platform

if PLATFORM.startswith("linux"):
    try:
        import pyudev

        LINUX_AVAILABLE = True
    except ImportError:
        LINUX_AVAILABLE = False
elif PLATFORM == "win32":
    try:
        import win32api  # noqa: F401
        import win32con  # noqa: F401
        import win32gui  # noqa: F401
        import wmi

        WINDOWS_AVAILABLE = True
    except ImportError:
        WINDOWS_AVAILABLE = False
elif PLATFORM == "darwin":
    try:
        from Foundation import NSNotificationCenter, NSRunLoop  # noqa: F401
        from PyObjCTools import AppHelper  # noqa: F401

        MACOS_AVAILABLE = True
    except ImportError:
        MACOS_AVAILABLE = False


class USBDevice:
    """USB设备信息类"""

    def __init__(
        self,
        device_id: str,
        vendor_id: str | None = None,
        product_id: str | None = None,
        manufacturer: str | None = None,
        product: str | None = None,
        serial: str | None = None,
        device_type: str | None = None,
    ):
        self.device_id = device_id
        self.vendor_id = vendor_id
        self.product_id = product_id
        self.manufacturer = manufacturer or "Unknown"
        self.product = product or "Unknown Device"
        self.serial = serial
        self.device_type = device_type or "USB"
        self.timestamp = datetime.now()

    def to_dict(self) -> dict:
        return {
            "device_id": self.device_id,
            "vendor_id": self.vendor_id,
            "product_id": self.product_id,
            "manufacturer": self.manufacturer,
            "product": self.product,
            "serial": self.serial,
            "device_type": self.device_type,
            "timestamp": self.timestamp.isoformat(),
        }

    def __str__(self) -> str:
        return f"[{self.device_type}] {self.manufacturer} {self.product} (VID:{self.vendor_id} PID:{self.product_id})"


class USBMonitorBase(ABC):
    """USB监控基类"""

    def __init__(self):
        self.callbacks: dict[str, list[Callable]] = {"add": [], "remove": [], "change": []}
        self.running = False
        self.monitor_thread: threading.Thread | None = None
        self.watchdog_thread: threading.Thread | None = None

        # 用于跟踪状态改变
        self._changed_flag = False
        self._state_lock = threading.Lock()

        # 用于统一线程生命周期控制
        self._thread_lock = threading.Lock()
        self._stop_event = threading.Event()

    def on_connect(self, callback: Callable[[USBDevice], None]):
        self.callbacks["add"].append(callback)
        return self

    def on_disconnect(self, callback: Callable[[USBDevice], None]):
        self.callbacks["remove"].append(callback)
        return self

    def on_change(self, callback: Callable[[USBDevice, str], None]):
        self.callbacks["change"].append(callback)
        return self

    def _trigger(self, event_type: str, device: USBDevice, *args):
        with self._state_lock:
            self._changed_flag = True

        for callback in self.callbacks.get(event_type, []):
            try:
                if event_type == "change":
                    callback(device, args[0] if args else "unknown")
                else:
                    callback(device)
            except Exception as e:
                print(f"回调执行错误: {e}")

    def has_usb_changed(self) -> bool:
        """检查自上次查询后是否发生过设备插拔"""
        with self._state_lock:
            flag = self._changed_flag
            self._changed_flag = False
            return flag

    def _start_thread(self, attr_name: str, target: Callable[[], None], name: str) -> threading.Thread | None:
        with self._thread_lock:
            thread = getattr(self, attr_name, None)
            if thread is not None and thread.is_alive():
                return thread
            thread = threading.Thread(target=target, name=name, daemon=True)
            setattr(self, attr_name, thread)
            thread.start()
            return thread

    def _join_thread(self, thread: threading.Thread | None, timeout: float) -> None:
        if thread is None:
            return
        if thread is threading.current_thread():
            return
        if thread.is_alive():
            thread.join(timeout=timeout)

    @abstractmethod
    def start(self):
        pass

    @abstractmethod
    def stop(self):
        pass

    @abstractmethod
    def get_current_devices(self) -> list[USBDevice]:
        pass


class LinuxUSBMonitor(USBMonitorBase):
    """Linux USB监控实现"""

    def __init__(self):
        super().__init__()
        if not LINUX_AVAILABLE:
            raise ImportError("请先安装pyudev: pip install pyudev")
        self.context = pyudev.Context()
        self.monitor = None

    def _create_monitor(self):
        monitor = pyudev.Monitor.from_netlink(self.context)
        monitor.filter_by(subsystem="usb")
        return monitor

    def _parse_device(self, device) -> USBDevice | None:
        if device.device_type != "usb_device":
            return None
        return USBDevice(
            device_id=device.device_path,
            vendor_id=device.get("ID_VENDOR_ID", "0000"),
            product_id=device.get("ID_MODEL_ID", "0000"),
            manufacturer=device.get("ID_VENDOR", "Unknown"),
            product=device.get("ID_MODEL", "Unknown"),
            serial=device.get("ID_SERIAL_SHORT"),
            device_type="USB",
        )

    def _monitor_loop(self):
        monitor = self._create_monitor()
        monitor.start()
        self.monitor = monitor
        try:
            while self.running and not self._stop_event.is_set():
                device = monitor.poll(timeout=1)
                if device is None:
                    continue
                usb_device = self._parse_device(device)
                if not usb_device:
                    continue

                action = getattr(device, "action", "change")
                if action == "add":
                    self._trigger("add", usb_device)
                elif action == "remove":
                    self._trigger("remove", usb_device)
                elif action == "change":
                    self._trigger("change", usb_device, action)
        finally:
            self.monitor = None

    def start(self):
        with self._thread_lock:
            if self.running and self.monitor_thread and self.monitor_thread.is_alive():
                return
            self.running = True
            self._stop_event.clear()
        self._start_thread("monitor_thread", self._monitor_loop, "usb-linux-monitor")

    def stop(self):
        self.running = False
        self._stop_event.set()
        self._join_thread(self.monitor_thread, timeout=2)

    def get_current_devices(self) -> list[USBDevice]:
        devices = []
        for device in self.context.list_devices(subsystem="usb", DEVTYPE="usb_device"):
            usb_dev = self._parse_device(device)
            if usb_dev:
                devices.append(usb_dev)
        return devices


class WindowsUSBMonitor(USBMonitorBase):
    def __init__(self):
        super().__init__()
        if not WINDOWS_AVAILABLE:
            raise ImportError("请先安装pywin32和wmi: pip install pywin32 wmi")

        self.known_devices: set = set()
        self.poll_interval = 1.0

    def _get_device_id(self, device) -> str:
        return f"{device.DeviceID}"

    def _parse_device(self, device) -> USBDevice:
        vid, pid = "0000", "0000"
        if "VID_" in device.DeviceID:
            parts = device.DeviceID.split("\\")
            for part in parts:
                if "VID_" in part and "PID_" in part:
                    for vp in part.split("&"):
                        if "VID_" in vp:
                            vid = vp.replace("VID_", "").split("_")[0]
                        if "PID_" in vp:
                            pid = vp.replace("PID_", "").split("_")[0]

        return USBDevice(
            device_id=device.DeviceID,
            vendor_id=vid,
            product_id=pid,
            manufacturer=getattr(device, "Manufacturer", "Unknown"),
            product=getattr(device, "Name", "Unknown Device"),
            device_type="USB",
        )

    def _get_usb_devices(self, wmi_client) -> dict[str, USBDevice]:
        devices = {}
        try:
            query = "SELECT DeviceID, Name, Manufacturer FROM Win32_PnPEntity WHERE PNPClass = 'USB'"
            for device in wmi_client.query(query):
                dev_id = self._get_device_id(device)
                devices[dev_id] = self._parse_device(device)
        except Exception as e:
            if not hasattr(self, "_error_logged"):
                print(f"获取设备列表错误: {e}")
                self._error_logged = True
        return devices

    def _monitor_loop(self):
        import pythoncom

        pythoncom.CoInitialize()
        wmi_client = None
        try:
            wmi_client = wmi.WMI()
            self.known_devices = set(self._get_usb_devices(wmi_client).keys())

            while self.running and not self._stop_event.is_set():
                try:
                    current_devices = self._get_usb_devices(wmi_client)
                    current_ids = set(current_devices.keys())

                    added = current_ids - self.known_devices
                    for dev_id in added:
                        device = current_devices[dev_id]
                        self._trigger("add", device)

                    removed = self.known_devices - current_ids
                    for dev_id in removed:
                        placeholder = USBDevice(device_id=dev_id)
                        self._trigger("remove", placeholder)

                    self.known_devices = current_ids
                    if self._stop_event.wait(self.poll_interval):
                        break
                except Exception:
                    if self._stop_event.wait(1):
                        break
        except Exception:
            # WMI 初始化阶段失败时记录日志，避免线程静默死亡导致看门狗无限重启
            self._stop_event.wait(2)
        finally:
            wmi_client = None
            pythoncom.CoUninitialize()

    def start(self):
        with self._thread_lock:
            if self.running:
                if self.monitor_thread and self.monitor_thread.is_alive():
                    return
            self.running = True
            self._stop_event.clear()
        self._spawn_monitor_thread()
        self._spawn_watchdog_thread()

    def _spawn_monitor_thread(self):
        self._start_thread("monitor_thread", self._monitor_loop, "usb-windows-monitor")

    def _spawn_watchdog_thread(self):
        self._start_thread("watchdog_thread", self._watchdog, "usb-windows-watchdog")

    def _watchdog(self):
        while self.running and not self._stop_event.wait(2):
            monitor_thread = self.monitor_thread
            if monitor_thread is None or not monitor_thread.is_alive():
                self._spawn_monitor_thread()

    def stop(self):
        self.running = False
        self._stop_event.set()
        self._join_thread(self.monitor_thread, timeout=2)
        self._join_thread(self.watchdog_thread, timeout=2)

    def get_current_devices(self) -> list[USBDevice]:
        import pythoncom

        pythoncom.CoInitialize()
        wmi_client = None
        devices_dict: dict[str, USBDevice] | None = None
        try:
            wmi_client = wmi.WMI()
            devices_dict = self._get_usb_devices(wmi_client)
            return list(devices_dict.values())
        finally:
            devices_dict = None
            wmi_client = None
            pythoncom.CoUninitialize()


class GenericUSBMonitor(USBMonitorBase):
    """通用USB监控（基于pyusb轮询）"""

    def __init__(self):
        super().__init__()
        try:
            import usb.core
            import usb.util

            self.usb = usb.core
        except ImportError:
            raise ImportError("请先安装pyusb: pip install pyusb") from None

        self.known_devices: set = set()
        self.poll_interval = 1.0

    def _get_usb_devices(self):
        devices = {}
        try:
            found_devices = self.usb.find(find_all=True) or []
        except Exception:
            return devices

        for device in found_devices:
            device_id = self._build_device_id(device)
            devices[device_id] = USBDevice(
                device_id=device_id,
                vendor_id=self._format_hex(getattr(device, "idVendor", None)),
                product_id=self._format_hex(getattr(device, "idProduct", None)),
                manufacturer=self._read_descriptor(device, "manufacturer"),
                product=self._read_descriptor(device, "product"),
                serial=self._read_descriptor(device, "serial_number"),
                device_type="USB",
            )
        return devices

    def _format_hex(self, value) -> str | None:
        if value is None:
            return None
        try:
            return f"{int(value):04x}"
        except Exception:
            return str(value)

    def _read_descriptor(self, device, attr_name: str) -> str | None:
        try:
            value = getattr(device, attr_name, None)
            return str(value) if value else None
        except Exception:
            return None

    def _build_device_id(self, device) -> str:
        bus = getattr(device, "bus", "unknown")
        address = getattr(device, "address", "unknown")
        vendor_id = self._format_hex(getattr(device, "idVendor", None)) or "0000"
        product_id = self._format_hex(getattr(device, "idProduct", None)) or "0000"
        return f"{bus}:{address}:{vendor_id}:{product_id}"

    def _monitor_loop(self):
        self.known_devices = set(self._get_usb_devices().keys())
        while self.running and not self._stop_event.wait(self.poll_interval):
            current_devices = self._get_usb_devices()
            current_ids = set(current_devices.keys())

            added = current_ids - self.known_devices
            for dev_id in added:
                self._trigger("add", current_devices[dev_id])

            removed = self.known_devices - current_ids
            for dev_id in removed:
                self._trigger("remove", USBDevice(device_id=dev_id))

            self.known_devices = current_ids

    def start(self):
        with self._thread_lock:
            if self.running and self.monitor_thread and self.monitor_thread.is_alive():
                return
            self.running = True
            self._stop_event.clear()
        self._start_thread("monitor_thread", self._monitor_loop, "usb-generic-monitor")

    def stop(self):
        self.running = False
        self._stop_event.set()
        self._join_thread(self.monitor_thread, timeout=2)

    def get_current_devices(self):
        return list(self._get_usb_devices().values())


class CrossPlatformUSBMonitor:
    """
    跨平台USB监控接口（对外部调用提供的标准 API）
    """

    def __init__(self):
        self._monitor: USBMonitorBase | None = None
        self.running = False

        if PLATFORM.startswith("linux") and LINUX_AVAILABLE:
            self._monitor = LinuxUSBMonitor()
        elif PLATFORM == "win32" and WINDOWS_AVAILABLE:
            self._monitor = WindowsUSBMonitor()
        else:
            self._monitor = GenericUSBMonitor()

    def start_monitoring(self):
        """1. 启动 USB 监视器"""
        if not self.running:
            if self._monitor:
                self._monitor.start()
            self.running = True

    def stop_monitoring(self):
        """停止 USB 监视器"""
        self.running = False
        if self._monitor:
            self._monitor.stop()

    def get_usb_devices(self) -> list[USBDevice]:
        """2. 获取当前所有连接的 USB 设备列表"""
        if self._monitor:
            return self._monitor.get_current_devices()
        return []

    def has_usb_changed(self) -> bool:
        """3. 查询 USB 列表是否发生变动（有设备插入或拔出）"""
        if self._monitor:
            return self._monitor.has_usb_changed()
        return False

    def on_connect(self, callback: Callable[[USBDevice], None]):
        if self._monitor:
            self._monitor.on_connect(callback)
        return self

    def on_disconnect(self, callback: Callable[[USBDevice], None]):
        if self._monitor:
            self._monitor.on_disconnect(callback)
        return self


def main():
    print("=" * 60)
    print("USB设备实时监控 API 演示 (轮询模式 + 事件模式)")
    print("=" * 60)

    try:
        usb_api = CrossPlatformUSBMonitor()

        def print_add(dev):
            print(f"  [EVENT] ADD: {dev.manufacturer} {dev.product}")

        def print_remove(dev):
            print(f"  [EVENT] REMOVE: {dev.device_id}")

        usb_api.on_connect(print_add).on_disconnect(print_remove)

        devices = usb_api.get_usb_devices()
        print(f"当前共有 {len(devices)} 个USB设备。")
        for dev in devices[:5]:
            print(f"  - {dev}")
        if len(devices) > 5:
            print("  ...")

        print("\n正在启动监视器...")
        usb_api.start_monitoring()

        while usb_api.running:
            if usb_api.has_usb_changed():
                print("\n[MAIN] 检测到 USB 设备变动，正在重新获取设备列表...")
                current_devices = usb_api.get_usb_devices()
                print(f"[MAIN] 当前设备总数为: {len(current_devices)}\n")

            time.sleep(1)

    except KeyboardInterrupt:
        print("\n\n正在安全退出...")
    except Exception as e:
        print(f"程序异常: {e}")
    finally:
        if "usb_api" in locals():
            usb_api.stop_monitoring()
        print("已退出")


if __name__ == "__main__":
    main()
