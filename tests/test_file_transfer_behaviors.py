import os
import sys
import tempfile
import threading
import types
import unittest
from types import SimpleNamespace
from unittest.mock import patch


class _DummyMeta(type):
    def __getattr__(cls, name):
        del name
        return cls


class _Dummy(metaclass=_DummyMeta):
    def __init__(self, *args, **kwargs):
        del args, kwargs

    def __getattr__(self, name):
        del name
        return self

    def __call__(self, *args, **kwargs):
        del args, kwargs
        return self

    def __or__(self, other):
        del other
        return self

    def __and__(self, other):
        del other
        return self

    def __bool__(self):
        return False

    def __int__(self):
        return 0


class QObject:
    def __init__(self, *args, **kwargs):
        del args, kwargs

    def deleteLater(self):
        return None


class _Signal:
    def __init__(self, *args, **kwargs):
        self._slots = []

    def connect(self, slot):
        self._slots.append(slot)

    def emit(self, *args, **kwargs):
        for slot in list(self._slots):
            slot(*args, **kwargs)


def pyqtSignal(*args, **kwargs):
    del args, kwargs
    return _Signal()


def pyqtSlot(*args, **kwargs):
    del args, kwargs

    def _decorator(func):
        return func

    return _decorator


def _ensure_pyqt6_stubs():
    pyqt6 = sys.modules.setdefault("PyQt6", types.ModuleType("PyQt6"))
    qtcore = sys.modules.setdefault("PyQt6.QtCore", types.ModuleType("PyQt6.QtCore"))
    qtgui = sys.modules.setdefault("PyQt6.QtGui", types.ModuleType("PyQt6.QtGui"))
    qtwidgets = sys.modules.setdefault("PyQt6.QtWidgets", types.ModuleType("PyQt6.QtWidgets"))

    qtcore.QObject = getattr(qtcore, "QObject", QObject)
    qtcore.pyqtSignal = getattr(qtcore, "pyqtSignal", pyqtSignal)
    qtcore.pyqtSlot = getattr(qtcore, "pyqtSlot", pyqtSlot)
    qtcore.QTimer = getattr(qtcore, "QTimer", _Dummy)
    qtcore.Qt = getattr(qtcore, "Qt", _Dummy)
    qtcore.__getattr__ = getattr(qtcore, "__getattr__", lambda name: _Dummy)

    qtgui.QTextCursor = getattr(qtgui, "QTextCursor", _Dummy)
    qtgui.__getattr__ = getattr(qtgui, "__getattr__", lambda name: _Dummy)

    for attr_name in (
        "QApplication",
        "QMainWindow",
        "QLabel",
        "QLineEdit",
        "QPushButton",
        "QSystemTrayIcon",
        "QTableWidgetItem",
        "QCheckBox",
        "QComboBox",
        "QDialog",
        "QListWidget",
        "QSpinBox",
        "QTableWidget",
        "QWidget",
        "QMenu",
        "QAction",
        "QMessageBox",
        "QFileDialog",
    ):
        setattr(qtwidgets, attr_name, getattr(qtwidgets, attr_name, _Dummy))
    qtwidgets.__getattr__ = getattr(qtwidgets, "__getattr__", lambda name: _Dummy)

    pyqt6.QtCore = qtcore
    pyqt6.QtGui = qtgui
    pyqt6.QtWidgets = qtwidgets


_ensure_pyqt6_stubs()

from app.domain.enums.file_type import FileType
from app.domain.models.file_info import FileInfo
from app.ui.main_window import SndcpyGUI
from app.infrastructure.process.registry import ProcessRegistry
from app.infrastructure.process.supervisor import ProcessSupervisor
from app.services.file_manager_service import FileManagerService
from app.ui.file_actions import submit_upload_requests


class _ImmediateTaskRunner:
    def start(self, name, group=None, target=None, args=(), kwargs=None):
        del name, group
        if target is not None:
            target(*args, **(kwargs or {}))
        return SimpleNamespace()


class _DeferredSymlinkTaskRunner:
    def __init__(self):
        self._deferred: list[tuple[object, tuple]] = []

    def start(self, name, group=None, target=None, args=(), kwargs=None):
        del group
        if target is None:
            return SimpleNamespace()
        if name == "files-resolve-symlinks":
            self._deferred.append((target, args, kwargs or {}))
        else:
            target(*args, **(kwargs or {}))
        return SimpleNamespace()

    def run_deferred(self):
        queued = list(self._deferred)
        self._deferred.clear()
        for target, args, kwargs in queued:
            target(*args, **kwargs)


class _FakeCommandManager:
    def get_target_cmd(self, target_key: str, **kwargs):
        del kwargs
        return [target_key]


class _StdoutStub:
    def __init__(self, lines: list[str], trailing_text: str = ""):
        self._lines = list(lines)
        self._trailing_text = trailing_text

    def readline(self):
        if self._lines:
            return self._lines.pop(0)
        if self._trailing_text:
            trailing = self._trailing_text
            self._trailing_text = ""
            return trailing
        return ""

    def read(self):
        trailing = self._trailing_text
        self._trailing_text = ""
        return trailing


class _TransferProc:
    def __init__(self, returncode: int, lines: list[str], trailing_text: str = ""):
        self.pid = 6789
        self.returncode = None
        self._final_returncode = returncode
        self.stdout = _StdoutStub(lines, trailing_text)

    def poll(self):
        # 模拟进程已退出：新版本 _run_transfer_with_progress 依赖 poll() 检测退出
        return self._final_returncode

    def wait(self):
        self.returncode = self._final_returncode
        return self.returncode


class _StopAwareSupervisor:
    def __init__(self, registry: ProcessRegistry):
        self._registry = registry

    def kill_group(self, device_serial: str, group: str):
        reg = self._registry.ensure(device_serial)
        for proc in reg.get(group, []):
            proc.returncode = 1
        reg[group].clear()

    def remove_if_present(self, device_serial: str, group: str, proc):
        reg = self._registry.ensure(device_serial)
        if proc in reg.get(group, []):
            reg[group].remove(proc)


class _BlockingStdout:
    def __init__(self):
        self.read_calls = 0

    def readline(self):
        threading.Event().wait(2)
        return ""

    def read(self):
        self.read_calls += 1
        raise AssertionError("shutdown cleanup should not call read()")


class _BlockingTransferProc:
    def __init__(self):
        self.pid = 9876
        self.returncode = None
        self.stdout = _BlockingStdout()
        self.wait_calls = 0

    def poll(self):
        return self.returncode

    def wait(self):
        self.wait_calls += 1
        raise AssertionError("shutdown cleanup should not call wait()")


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

    def test_transfer_locks_are_scoped_by_device(self):
        service = FileManagerService(
            cmd_manager=_FakeCommandManager(),
            ls_parser=None,
            transfer_progress_parser=None,
            process_registry=ProcessRegistry(),
            process_supervisor=ProcessSupervisor(ProcessRegistry()),
            task_runner=_ImmediateTaskRunner(),
            run_adb_command=lambda cmd, desc: None,
            is_running=lambda: True,
        )

        self.assertIs(service._get_transfer_lock("device-1"), service._get_transfer_lock("device-1"))
        self.assertIsNot(service._get_transfer_lock("device-1"), service._get_transfer_lock("device-2"))

    def test_transfer_start_event_waits_until_device_lock_is_acquired(self):
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
        statuses: list[str] = []
        start_seen = threading.Event()

        def _emit(status, device_serial, transfer_kind, remote_path, message, percent):
            del device_serial, transfer_kind, remote_path, message, percent
            statuses.append(status)
            if status == "start":
                start_seen.set()

        service.file_transfer_progress = SimpleNamespace(emit=_emit)
        lock = service._get_transfer_lock("device-1")
        lock.acquire()

        def _run_locked_transfer():
            with patch("app.services.file_manager_service.subprocess.Popen", return_value=_TransferProc(0, [])):
                service._run_transfer_with_progress(
                    "device-1",
                    ["push_file_cmd"],
                    "上传 demo.txt",
                    transfer_kind="push",
                    remote_path="/sdcard/",
                )

        worker = threading.Thread(target=_run_locked_transfer)
        worker.start()
        try:
            self.assertFalse(start_seen.wait(0.1))
        finally:
            lock.release()
        worker.join(timeout=1)

        self.assertFalse(worker.is_alive())
        self.assertIn("start", statuses)
        self.assertIn("done", statuses)

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
        progress_events: list[tuple[str, str, str, str, int]] = []
        service.file_transfer_progress.connect(
            lambda status, device_serial, transfer_kind, remote_path, message, percent: progress_events.append(
                (status, device_serial, transfer_kind, remote_path, message, percent)
            )
        )

        with tempfile.TemporaryDirectory() as temp_dir:
            fake_uuid = SimpleNamespace(hex="fixed-cache")

            def _fake_transfer(device_serial, cmd, desc, *, transfer_kind="", remote_path="", emit_done=True):
                del device_serial, cmd, desc, transfer_kind, remote_path, emit_done
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
        self.assertEqual(progress_events[-1][1], "device-1")
        self.assertEqual(progress_events[-1][2], "pull")
        self.assertIn("denied", progress_events[-1][4])

    def test_transfer_failure_uses_trailing_output_as_error_message(self):
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
        progress_events: list[tuple[str, str, str, str, str, int]] = []
        service.file_transfer_progress.connect(
            lambda status, device_serial, transfer_kind, remote_path, message, percent: progress_events.append(
                (status, device_serial, transfer_kind, remote_path, message, percent)
            )
        )

        with patch(
            "app.services.file_manager_service.subprocess.Popen",
            return_value=_TransferProc(1, ["50%\n"], "Permission denied\n"),
        ):
            success = service._run_transfer_with_progress(
                "device-1",
                ["push_file_cmd"],
                "上传 demo.txt",
                transfer_kind="push",
                remote_path="/sdcard/",
            )

        self.assertFalse(success)
        self.assertEqual(progress_events[-1][0], "error")
        self.assertIn("Permission denied", progress_events[-1][4])

    def test_transfer_shutdown_cleanup_does_not_block_on_stdout_or_wait(self):
        registry = ProcessRegistry()
        service = FileManagerService(
            cmd_manager=_FakeCommandManager(),
            ls_parser=None,
            transfer_progress_parser=None,
            process_registry=registry,
            process_supervisor=_StopAwareSupervisor(registry),
            task_runner=_ImmediateTaskRunner(),
            run_adb_command=lambda cmd, desc: None,
            is_running=lambda: False,
        )
        progress_events: list[tuple[str, str, str, str, str, int]] = []
        service.file_transfer_progress.connect(
            lambda status, device_serial, transfer_kind, remote_path, message, percent: progress_events.append(
                (status, device_serial, transfer_kind, remote_path, message, percent)
            )
        )
        proc = _BlockingTransferProc()

        with patch("app.services.file_manager_service.subprocess.Popen", return_value=proc), patch(
            "app.services.file_manager_service.time.sleep",
            lambda _: None,
        ):
            success = service._run_transfer_with_progress(
                "device-1",
                ["push_file_cmd"],
                "上传 demo.txt",
                transfer_kind="push",
                remote_path="/sdcard/",
            )

        self.assertFalse(success)
        self.assertEqual(registry.ensure("device-1")["transfer"], [])
        self.assertEqual(proc.wait_calls, 0)
        self.assertEqual(proc.stdout.read_calls, 0)
        self.assertEqual([event[0] for event in progress_events], ["start"])

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

    def test_refresh_after_transfer_only_targets_matching_push_view(self):
        gui = SndcpyGUI.__new__(SndcpyGUI)
        gui.file_device_combo = SimpleNamespace(currentText=lambda: "device-1")
        gui.remote_path_edit = SimpleNamespace(text=lambda: "/sdcard/Download")

        self.assertTrue(
            SndcpyGUI._should_refresh_file_view_after_transfer(
                gui,
                "device-1",
                "push",
                "/sdcard/Download/",
            )
        )
        self.assertFalse(
            SndcpyGUI._should_refresh_file_view_after_transfer(
                gui,
                "device-2",
                "push",
                "/sdcard/Download/",
            )
        )
        self.assertFalse(
            SndcpyGUI._should_refresh_file_view_after_transfer(
                gui,
                "device-1",
                "pull",
                "/sdcard/Download/",
            )
        )
        self.assertFalse(
            SndcpyGUI._should_refresh_file_view_after_transfer(
                gui,
                "device-1",
                "push",
                "/sdcard/Documents/",
            )
        )


if __name__ == "__main__":
    unittest.main()
