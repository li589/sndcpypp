import os
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from app.infrastructure.process.registry import ProcessRegistry
from app.infrastructure.process.supervisor import ProcessSupervisor
from app.services.file_manager_service import FileManagerService
from app.ui.file_actions import submit_upload_requests


class _ImmediateTaskRunner:
    def start(self, name, group=None, target=None, args=()):
        del name, group
        if target is not None:
            target(*args)
        return SimpleNamespace()


class _FakeCommandManager:
    def get_target_cmd(self, target_key: str, **kwargs):
        del kwargs
        return [target_key]


class FileTransferBehaviorTests(unittest.TestCase):
    def test_submit_upload_requests_detects_same_name_in_single_batch(self):
        uploads: list[tuple[str, str | None]] = []
        conflict_calls: list[str] = []

        def _resolve_file_conflict(target_name, is_upload, exists):
            del is_upload, exists
            conflict_calls.append(target_name)
            return "rename", "same (1).txt"

        submit_upload_requests(
            ["C:/from-a/same.txt", "D:/from-b/same.txt"],
            existing_names=set(),
            popups=SimpleNamespace(resolve_file_conflict=_resolve_file_conflict),
            log_to_console=lambda message, level: None,
            request_push=lambda path, rename_to: uploads.append((path, rename_to)),
        )

        self.assertEqual(conflict_calls, ["same.txt"])
        self.assertEqual(
            uploads,
            [
                ("C:/from-a/same.txt", None),
                ("D:/from-b/same.txt", "same (1).txt"),
            ],
        )

    def test_pull_file_reports_error_when_final_move_fails(self):
        registry = ProcessRegistry()
        service = FileManagerService(
            cmd_manager=_FakeCommandManager(),
            ls_parser=None,
            transfer_progress_parser=None,
            process_registry=registry,
            process_supervisor=ProcessSupervisor(registry),
            task_runner=_ImmediateTaskRunner(),
            run_adb_command=lambda cmd, desc: None,
            is_running=lambda: True,
        )
        progress_events: list[tuple[str, str, int]] = []
        service.file_transfer_progress.connect(
            lambda status, message, percent: progress_events.append((status, message, percent))
        )

        with tempfile.TemporaryDirectory() as temp_dir:
            fake_uuid = SimpleNamespace(hex="fixed-cache")

            def _fake_transfer(device_serial, cmd, desc, *, emit_done=True):
                del device_serial, cmd, desc, emit_done
                cache_path = os.path.join(temp_dir, "sndcpy_pull_cache", fake_uuid.hex)
                os.makedirs(os.path.dirname(cache_path), exist_ok=True)
                with open(cache_path, "w", encoding="utf-8") as file_obj:
                    file_obj.write("payload")
                return True

            service._run_transfer_with_progress = _fake_transfer

            with patch("app.services.file_manager_service.tempfile.gettempdir", return_value=temp_dir), patch(
                "app.services.file_manager_service.uuid.uuid4",
                return_value=fake_uuid,
            ), patch(
                "app.services.file_manager_service.shutil.move",
                side_effect=PermissionError("denied"),
            ):
                service.pull_file("device-1", "/sdcard/demo.txt", temp_dir)

        self.assertEqual(progress_events[-1][0], "error")
        self.assertIn("denied", progress_events[-1][1])


if __name__ == "__main__":
    unittest.main()
