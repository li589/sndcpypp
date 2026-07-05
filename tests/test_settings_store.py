import json
import os
import tempfile
import unittest
from unittest.mock import patch

from app.infrastructure.config.settings_store import JsonSettingsStore, get_default_settings_path


class JsonSettingsStoreTests(unittest.TestCase):
    def test_load_merges_valid_json(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            settings_path = os.path.join(temp_dir, "settings.json")
            with open(settings_path, "w", encoding="utf-8") as file:
                json.dump({"video_bitrate": 4321, "adb_path": "adb.exe"}, file)

            store = JsonSettingsStore(settings_path)
            settings = store.load()

            self.assertEqual(settings["video_bitrate"], 4321)
            self.assertEqual(settings["adb_path"], "adb.exe")
            self.assertIsNone(store.last_load_warning)

    def test_load_recovers_from_invalid_json_and_creates_backup(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            settings_path = os.path.join(temp_dir, "settings.json")
            with open(settings_path, "w", encoding="utf-8") as file:
                file.write("{invalid json")

            store = JsonSettingsStore(settings_path)
            settings = store.load()

            self.assertEqual(settings["video_bitrate"], 8000)
            self.assertFalse(os.path.exists(settings_path))
            self.assertIsNotNone(store.last_load_warning)
            self.assertIn("设置文件损坏", store.last_load_warning)

            backups = [name for name in os.listdir(temp_dir) if name.startswith("settings.json.broken-")]
            self.assertEqual(len(backups), 1)

    def test_save_creates_parent_directory(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            settings_path = os.path.join(temp_dir, "nested", "settings.json")
            store = JsonSettingsStore(settings_path)

            store.save({"video_bitrate": 1234})

            self.assertTrue(os.path.exists(settings_path))

    def test_get_default_settings_path_prefers_user_profile_directory(self):
        with (
            patch("app.infrastructure.config.settings_store.os.name", "nt"),
            patch.dict(
                "app.infrastructure.config.settings_store.os.environ",
                {"APPDATA": "C:/Users/test/AppData/Roaming"},
                clear=False,
            ),
        ):
            settings_path = get_default_settings_path()

        self.assertEqual(
            os.path.normpath(settings_path),
            os.path.normpath("C:/Users/test/AppData/Roaming/sndcpypp/settings.json"),
        )


if __name__ == "__main__":
    unittest.main()
