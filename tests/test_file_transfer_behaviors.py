import os
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from app.domain.enums.file_type import FileType
from app.domain.models.file_info import FileInfo
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


class _DeferredSymlinkTaskRunner:
    def __init__(self):
        self._deferred: list[tuple[object, tuple]] = []

    def start(self, name, group=None, target=None, args=()):
        del group
        if target is None:
            return SimpleNamespace()
        if name == "files-resolve-symlinks":
            self._deferred.append((target, args))
        else:
            target(*args)
        return SimpleNamespace()

    def run_deferred(self):
        queued = list(self._deferred)
        self._deferred.clear()
        for target, args in queued:
            target(*args)


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

    def test_stale_symlink_resolution_is_ignored_after_directory_switch(self):
        registry = ProcessRegistry()
        task_runner = _DeferredSymlinkTaskRunner()
        parser_map = {
            "old-link": FileInfo(
                name="shared-link",
                file_type=FileType.SYMLINK,
                type_char="l",
                permissions="lrwxrwxrwx",
                owner="shell",
                group="shell",
                size=0,
                date_str="2026-01-01",
                symlink_target="old-target-file",
            ),
            "new-link": FileInfo(
                name="shared-link",
                file_type=FileType.SYMLINK,
                type_char="l",
                permissions="lrwxrwxrwx",
                owner="shell",
                group="shell",
                size=0,
                date_str="2026-01-01",
                symlink_target="new-target-dir",
            ),
        }
        current_listing = {"stdout": "old-link\n"}

        service = FileManagerService(
            cmd_manager=_FakeCommandManager(),
            ls_parser=SimpleNamespace(parse_line=lambda line: parser_map.get(line)),
            transfer_progress_parser=None,
            process_registry=registry,
            process_supervisor=ProcessSupervisor(registry),
            task_runner=task_runner,
            run_adb_command=lambda cmd, desc: SimpleNamespace(
                returncode=0,
                stdout=current_listing["stdout"],
                stderr="",
            ),
            is_running=lambda: True,
        )
        resolved_events: list[tuple[str, str, bool]] = []
        service.symlink_resolved.connect(
            lambda device_serial, name, is_dir: resolved_events.append((device_serial, name, is_dir))
        )

        with patch(
            "app.services.file_manager_service._SymlinkResolverWorker._probe_type",
            lambda self, remote_path: remote_path.endswith("-dir"),
        ):
            service.list_device_files_detailed("device-1", "/old/")
            current_listing["stdout"] = "new-link\n"
            service.list_device_files_detailed("device-1", "/new/")
            task_runner.run_deferred()

        self.assertEqual(resolved_events, [("device-1", "shared-link", True)])


if __name__ == "__main__":
    unittest.main()
