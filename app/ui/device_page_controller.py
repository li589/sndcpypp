from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QComboBox, QListWidget, QListWidgetItem

from app.ui.message_templates import device_count_status_text
from app.ui.widgets import DeviceListItemWidget


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
            self._attach_device_item_widget(item, device)
            if device == selected_device:
                item.setSelected(True)

        self._sync_combo(self._device_combo, devices, ["[ADB无设备]", "[Scrcpy命令]"])
        self._sync_combo(self._recording_device_combo, devices)
        self._sync_combo(self._file_device_combo, devices)
        self._status_setter(device_count_status_text(len(devices)))
        self.refresh_device_status_indicators()

    def _attach_device_item_widget(self, item: QListWidgetItem, device: str) -> None:
        """为设备列表项绑定状态指示 widget；测试环境（mock）下静默跳过。"""
        try:
            widget = DeviceListItemWidget(device, self._device_list)
            self._device_list.setItemWidget(item, widget)
        except Exception:
            pass

    def refresh_device_status_indicators(self) -> None:
        """遍历设备列表，查询每台设备的音频/视频/录制状态并更新指示 widget。"""
        controller = self._core_provider()
        if controller is None:
            return
        for i in range(self._device_list.count()):
            item = self._device_list.item(i)
            if item is None:
                continue
            widget = self._device_list.itemWidget(item)
            if widget is None:
                continue
            try:
                status = controller.get_device_route_status(item.text())
            except Exception:
                continue
            widget.update_status(
                audio=bool(status.get("audio", False)),
                video=bool(status.get("video", False)),
                recording=bool(status.get("recording", False)),
            )

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
            combo.setItemData(combo.count() - 1, item, Qt.ItemDataRole.ToolTipRole)
        for device in devices:
            combo.addItem(device)
            combo.setItemData(combo.count() - 1, device, Qt.ItemDataRole.ToolTipRole)

        idx = combo.findText(current_text)
        if idx >= 0:
            combo.setCurrentIndex(idx)
        elif combo.count() > 0:
            if devices and special_items:
                combo.setCurrentIndex(len(special_items))
            else:
                combo.setCurrentIndex(0)
        combo.setToolTip(combo.currentText())
        combo.blockSignals(False)
