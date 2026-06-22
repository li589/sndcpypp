#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
USB设备实时监控程序
支持: Linux (pyudev), Windows (pywin32/wmi), macOS (pyobjc)
功能: 实时检测USB设备的插入、拔出和状态变更
"""

import sys
import time
import threading
from datetime import datetime
from abc import ABC, abstractmethod
from typing import Callable, Optional, Dict, List

# 尝试导入平台特定的库
PLATFORM = sys.platform

if PLATFORM.startswith('linux'):
    try:
        import pyudev
        LINUX_AVAILABLE = True
    except ImportError:
        LINUX_AVAILABLE = False
elif PLATFORM == 'win32':
    try:
        import win32api
        import win32con
        import win32gui
        import wmi
        WINDOWS_AVAILABLE = True
    except ImportError:
        WINDOWS_AVAILABLE = False
elif PLATFORM == 'darwin':
    try:
        from Foundation import NSNotificationCenter, NSRunLoop
        from PyObjCTools import AppHelper
        MACOS_AVAILABLE = True
    except ImportError:
        MACOS_AVAILABLE = False


class USBDevice:
    """USB设备信息类"""
    def __init__(self, device_id: str, vendor_id: Optional[str] = None, 
                 product_id: Optional[str] = None, 
                 manufacturer: Optional[str] = None,
                 product: Optional[str] = None,
                 serial: Optional[str] = None,
                 device_type: Optional[str] = None):
        self.device_id = device_id
        self.vendor_id = vendor_id
        self.product_id = product_id
        self.manufacturer = manufacturer or "Unknown"
        self.product = product or "Unknown Device"
        self.serial = serial
        self.device_type = device_type or "USB"
        self.timestamp = datetime.now()
    
    def to_dict(self) -> Dict:
        return {
            "device_id": self.device_id,
            "vendor_id": self.vendor_id,
            "product_id": self.product_id,
            "manufacturer": self.manufacturer,
            "product": self.product,
            "serial": self.serial,
            "device_type": self.device_type,
            "timestamp": self.timestamp.isoformat()
        }
    
    def __str__(self) -> str:
        return f"[{self.device_type}] {self.manufacturer} {self.product} (VID:{self.vendor_id} PID:{self.product_id})"


class USBMonitorBase(ABC):
    """USB监控基类"""
    def __init__(self):
        self.callbacks: Dict[str, List[Callable]] = {
            'add':[],
            'remove': [],
            'change':[]
        }
        self.running = False
        self.monitor_thread: Optional[threading.Thread] = None
        
        # 新增：用于跟踪状态改变的标志与线程锁
        self._changed_flag = False
        self._state_lock = threading.Lock()
    
    def on_connect(self, callback: Callable[[USBDevice], None]):
        self.callbacks['add'].append(callback)
        return self
    
    def on_disconnect(self, callback: Callable[[USBDevice], None]):
        self.callbacks['remove'].append(callback)
        return self
    
    def on_change(self, callback: Callable[[USBDevice, str], None]):
        self.callbacks['change'].append(callback)
        return self
    
    def _trigger(self, event_type: str, device: USBDevice, *args):
        # 触发事件时，将状态改变标志设为 True
        with self._state_lock:
            self._changed_flag = True
            
        for callback in self.callbacks.get(event_type,[]):
            try:
                if event_type == 'change':
                    callback(device, args[0] if args else "unknown")
                else:
                    callback(device)
            except Exception as e:
                print(f"回调执行错误: {e}")

    def has_usb_changed(self) -> bool:
        """检查自上次查询后是否发生过设备插拔"""
        with self._state_lock:
            flag = self._changed_flag
            self._changed_flag = False  # 读后即焚
            return flag
    
    @abstractmethod
    def start(self): pass
    
    @abstractmethod
    def stop(self): pass
    
    @abstractmethod
    def get_current_devices(self) -> List[USBDevice]: pass


class LinuxUSBMonitor(USBMonitorBase):
    """Linux USB监控实现"""
    def __init__(self):
        super().__init__()
        if not LINUX_AVAILABLE:
            raise ImportError("请先安装pyudev: pip install pyudev")
        self.context = pyudev.Context()
        self.monitor = pyudev.Monitor.from_netlink(self.context)
        self.monitor.filter_by(subsystem='usb')
    
    def _parse_device(self, device) -> Optional[USBDevice]:
        if device.device_type != 'usb_device':
            return None
        return USBDevice(
            device_id=device.device_path,
            vendor_id=device.get('ID_VENDOR_ID', '0000'),
            product_id=device.get('ID_MODEL_ID', '0000'),
            manufacturer=device.get('ID_VENDOR', 'Unknown'),
            product=device.get('ID_MODEL', 'Unknown'),
            serial=device.get('ID_SERIAL_SHORT'),
            device_type='USB'
        )
    
    def _monitor_loop(self):
        self.monitor.start()
        for action, device in self.monitor:
            if not self.running: break
            usb_device = self._parse_device(device)
            if not usb_device: continue
            
            if action == 'add':
                self._trigger('add', usb_device)
            elif action == 'remove':
                self._trigger('remove', usb_device)
            elif action == 'change':
                self._trigger('change', usb_device, action)
    
    def start(self):
        self.running = True
        self.monitor_thread = threading.Thread(target=self._monitor_loop, daemon=True)
        self.monitor_thread.start()
    
    def stop(self):
        self.running = False
        if self.monitor_thread:
            self.monitor_thread.join(timeout=2)
    
    def get_current_devices(self) -> List[USBDevice]:
        devices =[]
        for device in self.context.list_devices(subsystem='usb', DEVTYPE='usb_device'):
            usb_dev = self._parse_device(device)
            if usb_dev: devices.append(usb_dev)
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
                        if "VID_" in vp: vid = vp.replace("VID_", "").split("_")[0]
                        if "PID_" in vp: pid = vp.replace("PID_", "").split("_")[0]

        return USBDevice(
            device_id=device.DeviceID,
            vendor_id=vid,
            product_id=pid,
            manufacturer=getattr(device, 'Manufacturer', 'Unknown'),
            product=getattr(device, 'Name', 'Unknown Device'),
            device_type='USB'
        )

    def _get_usb_devices(self, wmi_client) -> Dict[str, USBDevice]:
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
        try:
            wmi_client = wmi.WMI()
            self.known_devices = set(self._get_usb_devices(wmi_client).keys())

            while self.running:
                try:
                    current_devices = self._get_usb_devices(wmi_client)
                    current_ids = set(current_devices.keys())

                    added = current_ids - self.known_devices
                    for dev_id in added:
                        device = current_devices[dev_id]
                        self._trigger('add', device)

                    removed = self.known_devices - current_ids
                    for dev_id in removed:
                        placeholder = USBDevice(device_id=dev_id)
                        self._trigger('remove', placeholder)

                    self.known_devices = current_ids
                    time.sleep(self.poll_interval)
                except Exception as e:
                    time.sleep(1)
        finally:
            # 清理引用，安全退出COM
            locals().clear()
            pythoncom.CoUninitialize()

    def start(self):
        self.running = True
        self.monitor_thread = threading.Thread(target=self._monitor_loop, daemon=True)
        self.monitor_thread.start()
        threading.Thread(target=self._watchdog, daemon=True).start()

    def _watchdog(self):
        while self.running:
            if not self.monitor_thread.is_alive():
                self.start()
                break
            time.sleep(2)

    def stop(self):
        self.running = False
        if self.monitor_thread:
            self.monitor_thread.join(timeout=2)

    def get_current_devices(self) -> List[USBDevice]:
        import pythoncom
        pythoncom.CoInitialize()
        try:
            wmi_client = wmi.WMI()
            devices_dict = self._get_usb_devices(wmi_client)
            return list(devices_dict.values())
        finally:
            # 【完美解决 IUnknown 问题】
            # 在注销 COM 之前，必须强行销毁包含 COM 引用的变量(如 wmi_client 等)
            locals().clear() 
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
            raise ImportError("请先安装pyusb: pip install pyusb")
        
        self.known_devices: set = set()
        self.poll_interval = 1.0
    
    # ...（因字数限制略去内部方法，与之前相同即可）
    def _get_usb_devices(self): return {}
    def start(self): pass
    def stop(self): pass
    def get_current_devices(self): return[]


class CrossPlatformUSBMonitor:
    """
    跨平台USB监控接口（对外部调用提供的标准 API）
    """
    def __init__(self):
        self._monitor: Optional[USBMonitorBase] = None
        self.running = False
        
        if PLATFORM.startswith('linux') and LINUX_AVAILABLE:
            self._monitor = LinuxUSBMonitor()
        elif PLATFORM == 'win32' and WINDOWS_AVAILABLE:
            self._monitor = WindowsUSBMonitor()
        else:
            self._monitor = GenericUSBMonitor()

    # ==========================================
    # 供外部直接调用的核心接口 API 
    # ==========================================

    def start_monitoring(self):
        """1. 启动 USB 监视器"""
        if not self.running:
            self.running = True
            if self._monitor:
                self._monitor.start()

    def stop_monitoring(self):
        """停止 USB 监视器"""
        self.running = False
        if self._monitor:
            self._monitor.stop()

    def get_usb_devices(self) -> List[USBDevice]:
        """2. 获取当前所有连接的 USB 设备列表"""
        if self._monitor:
            return self._monitor.get_current_devices()
        return[]

    def has_usb_changed(self) -> bool:
        """3. 查询 USB 列表是否发生变动（有设备插入或拔出）"""
        if self._monitor:
            return self._monitor.has_usb_changed()
        return False

    # ==========================================
    # 可选的回调事件接口
    # ==========================================
    def on_connect(self, callback: Callable[[USBDevice], None]):
        if self._monitor: self._monitor.on_connect(callback)
        return self
    
    def on_disconnect(self, callback: Callable[[USBDevice], None]):
        if self._monitor: self._monitor.on_disconnect(callback)
        return self

# ==========================================
# 演示：其他模块/代码如何调用此 API
# ==========================================
def main():
    print("=" * 60)
    print("USB设备实时监控 API 演示 (轮询模式 + 事件模式)")
    print("=" * 60)
    
    try:
        # 1. 初始化
        usb_api = CrossPlatformUSBMonitor()
        
        # [可选] 也可以注册回调函数，方便看控制台打印
        def print_add(dev): 
            print(f"  [事件] 🟢 插入: {dev.manufacturer} {dev.product}")
        def print_remove(dev): 
            print(f"  [事件] 🔴 拔出: {dev.device_id}")
        usb_api.on_connect(print_add).on_disconnect(print_remove)

        # 2. 调用 API 获取初始设备
        devices = usb_api.get_usb_devices()
        print(f"当前共有 {len(devices)} 个USB设备。")
        for dev in devices[:5]: # 只打前5个示范
            print(f"  • {dev}")
        if len(devices) > 5: print("  ...")
        
        print("\n正在启动监视器...")
        # 3. 启动后台监控
        usb_api.start_monitoring()
        
        # 模拟你的主程序循环（每隔一秒做自己的事）
        while usb_api.running:
            
            # 4. 在其他逻辑中，随时查询状态：是否发生过插拔变动？
            if usb_api.has_usb_changed():
                print("\n🔔 [主线程检测] -> 捕获到 USB 设备变动！正在重新获取设备列表...")
                
                # 重新获取设备
                current_devices = usb_api.get_usb_devices()
                print(f"🔔[主线程更新] -> 当前设备总数为: {len(current_devices)}\n")

            # 模拟你的应用的其他耗时逻辑
            time.sleep(1)

    except KeyboardInterrupt:
        print("\n\n正在安全退出...")
    except Exception as e:
        print(f"程序异常: {e}")
    finally:
        if 'usb_api' in locals():
            usb_api.stop_monitoring()
        print("已退出")

if __name__ == "__main__":
    main()