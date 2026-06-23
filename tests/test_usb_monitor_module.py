import unittest

from app.infrastructure.adb.UsbMonitor import CrossPlatformUSBMonitor, USBDevice


class UsbMonitorModuleTests(unittest.TestCase):
    def test_new_module_exports_expected_symbols(self):
        device = USBDevice("dev-1", vendor_id="1234", product_id="5678")

        self.assertEqual(device.device_id, "dev-1")
        self.assertEqual(device.vendor_id, "1234")
        self.assertTrue(issubclass(CrossPlatformUSBMonitor, object))


if __name__ == "__main__":
    unittest.main()
