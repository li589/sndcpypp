from PyQt6.QtWidgets import QComboBox, QListWidget, QListWidgetItem

from app.ui.message_templates import device_count_status_text


class DevicePageController:
    def __init__(
        self,
        *,
        device_list: QListWidget,
        refresh_devices_button,
        device_combo: QComboBox,
        recording_device_combo: QComboBox,
        file_device_combo: QComboBox,
        status_setter,
        show_device_required_warning,
        core_provider,
        is_adb_valid_provider,
        auto_refresh_value_provider,
    ):
        self._device_list = device_list
        self._refresh_devices_button = refresh_devices_button
        self._device_combo = device_combo
        self._recording_device_combo = recording_device_combo
        self._file_device_combo = file_device_combo
        self._status_setter = status_setter
        self._show_device_required_warning = show_device_required_warning
        self._core_provider = core_provider
        self._is_adb_valid_provider = is_adb_valid_provider
        self._auto_refresh_value_provider = auto_refresh_value_provider

    def auto_refresh_devices(self) -> None:
        controller = self._core_provider()
        if controller is None:
            return

        if self._device_list.currentItem():
            self._refresh_devices_button.set_refresh_mode(False)
            return

        if self._is_adb_valid_provider() and self._auto_refresh_value_provider() == 1:
            controller.request_refresh_devices()

    def manual_refresh_devices(self) -> None:
        controller = self._core_provider()
        if controller is None:
            return

        if self._device_list.currentItem():
            self._refresh_devices_button.set_refresh_mode(False)
        controller.request_refresh_devices()

    def update_device_list(self, devices: list[str]) -> None:
        current_devices = [self._device_list.item(i).text() for i in range(self._device_list.count())]
        if current_devices == devices:
            self._status_setter(device_count_status_text(len(devices)))
            return

        selected_device = self.get_selected_device(show_warning=False)
        self._device_list.clear()
        for device in devices:
            item = QListWidgetItem(device)
            self._device_list.addItem(item)
            if device == selected_device:
                item.setSelected(True)

        self._sync_combo(self._device_combo, devices, ["[ADB无设备]", "[Scrcpy命令]"])
        self._sync_combo(self._recording_device_combo, devices)
        self._sync_combo(self._file_device_combo, devices)
        self._status_setter(device_count_status_text(len(devices)))

    def get_selected_device(self, show_warning: bool = True) -> str | None:
        selected_items = self._device_list.selectedItems()
        if not selected_items:
            if show_warning:
                self._show_device_required_warning()
            return None
        return selected_items[0].text()

    def _sync_combo(self, combo: QComboBox, devices: list[str], special_items: list[str] | None = None) -> None:
        special_items = special_items or []
        current_text = combo.currentText()
        combo.blockSignals(True)
        combo.clear()
        for item in special_items:
            combo.addItem(item)
        for device in devices:
            combo.addItem(device)

        idx = combo.findText(current_text)
        if idx >= 0:
            combo.setCurrentIndex(idx)
        elif combo.count() > 0:
            if devices and special_items:
                combo.setCurrentIndex(len(special_items))
            else:
                combo.setCurrentIndex(0)
        combo.blockSignals(False)
