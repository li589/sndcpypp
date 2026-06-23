import time
import unittest

from app.infrastructure.adb.UsbMonitor import (
    CrossPlatformUSBMonitor,
    GenericUSBMonitor,
    LinuxUSBMonitor,
    USBDevice,
    USBMonitorBase,
)


class UsbMonitorModuleTests(unittest.TestCase):
    def test_new_module_exports_expected_symbols(self):
        device = USBDevice("dev-1", vendor_id="1234", product_id="5678")

        self.assertEqual(device.device_id, "dev-1")
        self.assertEqual(device.vendor_id, "1234")
        self.assertTrue(issubclass(CrossPlatformUSBMonitor, object))

    def test_linux_monitor_can_restart_after_stop(self):
        class _FakeMonitor:
            def start(self):
                return None

            def poll(self, timeout=1):
                time.sleep(min(timeout, 0.01))
                return None

        create_calls: list[str] = []
        monitor = LinuxUSBMonitor.__new__(LinuxUSBMonitor)
        USBMonitorBase.__init__(monitor)
        monitor.context = object()
        monitor._create_monitor = lambda: create_calls.append("create") or _FakeMonitor()

        monitor.start()
        time.sleep(0.03)
        monitor.stop()
        first_thread = monitor.monitor_thread

        monitor.start()
        time.sleep(0.03)
        monitor.stop()

        self.assertGreaterEqual(len(create_calls), 2)
        self.assertIsNotNone(first_thread)
        self.assertFalse(first_thread.is_alive())
        self.assertIsNotNone(monitor.monitor_thread)
        self.assertFalse(monitor.monitor_thread.is_alive())

    def test_generic_monitor_detects_add_and_remove(self):
        class _FakeUsbCore:
            def __init__(self):
                self.devices = []

            def find(self, find_all=False):
                del find_all
                return list(self.devices)

        class _FakeUsbDevice:
            def __init__(self, bus, address, vendor, product):
                self.bus = bus
                self.address = address
                self.idVendor = vendor
                self.idProduct = product
                self.manufacturer = "Vendor"
                self.product = "Product"
                self.serial_number = "serial"

        generic = GenericUSBMonitor.__new__(GenericUSBMonitor)
        USBMonitorBase.__init__(generic)
        generic.usb = _FakeUsbCore()
        generic.poll_interval = 0.01
        generic.known_devices = set()

        added: list[str] = []
        removed: list[str] = []
        generic.on_connect(lambda device: added.append(device.device_id))
        generic.on_disconnect(lambda device: removed.append(device.device_id))

        generic.start()
        time.sleep(0.02)
        generic.usb.devices = [_FakeUsbDevice(1, 2, 0x1234, 0x5678)]
        time.sleep(0.03)
        generic.usb.devices = []
        time.sleep(0.03)
        generic.stop()

        self.assertEqual(len(added), 1)
        self.assertEqual(len(removed), 1)
        self.assertTrue(generic.has_usb_changed())
        self.assertFalse(generic.monitor_thread.is_alive())


if __name__ == "__main__":
    unittest.main()
