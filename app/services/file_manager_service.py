import os
import queue
import shutil
import subprocess
import tempfile
import threading
import time
import uuid
from typing import Callable, Optional

from PyQt6.QtCore import QObject, pyqtSignal
from app.infrastructure.config.logging_config import get_logger

logger = get_logger(__name__)

from app.domain.enums.file_type import FileType
from app.infrastructure.fileops.ls_parser import LSAllParser
from app.infrastructure.fileops.transfer_progress import TransferProgressParser


def _report_debug_event(hypothesis_id: str, location: str, msg: str, data: dict | None = None) -> None:
    del hypothesis_id, location, msg, data


class _SymlinkResolverWorker(QObject):
    progress = pyqtSignal(str, bool)
    finished = pyqtSignal()
    log_message = pyqtSignal(str, str)

    def __init__(self, cmd_manager, device_serial, symlinks, adb_lock: threading.Lock) -> None:
        super().__init__()
        self.cmd_manager = cmd_manager
        self.device_serial = device_serial
        self.symlinks = symlinks
        self._adb_lock = adb_lock
        self._running = True

    def stop(self) -> None:
        self._running = False

    def run(self) -> None:
        for name, full_path in self.symlinks:
            if not self._running:
                break
            try:
                is_dir = self._probe_type(full_path)
                self.progress.emit(name, is_dir)
            except Exception as exc:
                self.log_message.emit(f"解析符号链接失败[{name}]: {exc}", "error")
                self.progress.emit(name, False)
        self.finished.emit()

    def _probe_type(self, remote_path) -> bool:
        cmd = self.cmd_manager.get_target_cmd(
            "check_file_type_cmd",
            device_serial=self.device_serial,
            remote_path=remote_path,
        )
        res = self._run_subprocess_command(cmd)
        stdout = res.stdout.strip().lower()

        if "directory" in stdout:
            return True
        if "permission denied" in stdout or "not found" in stdout or "unknown" in stdout or "broken" in stdout or stdout == "":
            ls_cmd = self.cmd_manager.get_target_cmd(
                "list_files_detailed_cmd",
                device_serial=self.device_serial,
                remote_path=remote_path,
            )
            res_ls = self._run_subprocess_command(ls_cmd)
            if res_ls.stdout and res_ls.stdout.startswith("d"):
                return True
            return False
        return False

    def _run_subprocess_command(self, cmd: list[str]) -> subprocess.CompletedProcess:
        resolved_cwd = None
        if cmd and cmd[0]:
            executable_path = os.path.abspath(cmd[0])
            if os.path.isfile(executable_path):
                resolved_cwd = os.path.dirname(executable_path)
        with self._adb_lock:
            return subprocess.run(
                cmd,
                cwd=resolved_cwd,
                capture_output=True,
                text=True,
                timeout=5,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
                encoding="utf-8",
                errors="replace",
            )


class FileManagerService(QObject):
    files_listed = pyqtSignal(str, list, bool)
    files_listed_detailed = pyqtSignal(str, list, bool)
    symlink_resolved = pyqtSignal(str, str, bool)
    file_transfer_progress = pyqtSignal(str, str, str, str, str, int)
    log_message = pyqtSignal(str, str)

    def __init__(
        self,
        cmd_manager,
        ls_parser,
        transfer_progress_parser,
        process_registry,
        process_supervisor,
        task_runner,
        run_adb_command: Callable[[list[str], str], Optional[subprocess.CompletedProcess]],
        is_running: Callable[[], bool],
    ) -> None:
        super().__init__()
        self._cmd_manager = cmd_manager
        self._ls_parser = ls_parser or LSAllParser()
        self._transfer_progress_parser = transfer_progress_parser or TransferProgressParser()
        self._process_registry = process_registry
        self._process_supervisor = process_supervisor
        self._task_runner = task_runner
        self._run_adb_command = run_adb_command
        self._is_running = is_running
        self._symlink_workers: dict[str, _SymlinkResolverWorker] = {}
        self._symlink_request_tokens: dict[str, int] = {}
        self._adb_lock = threading.Lock()
        self._transfer_lock = threading.Lock()

    def list_device_files(self, device_serial: str, path: str) -> None:
        def _list():
            cmd = self._cmd_manager.get_target_cmd("list_files_cmd", device_serial=device_serial, remote_path=path)
            with self._adb_lock:
                res = self._run_adb_command(cmd, f"列出文件 ({device_serial})")
            if res and res.returncode == 0:
                lines = res.stdout.splitlines()
                file_list = []

                for line in lines:
                    line = line.rstrip("\r\n")
                    if not line:
                        continue

                    is_dir = False
                    name = line

                    if name.endswith("/"):
                        is_dir = True
                        name = name[:-1]
                    elif name.endswith("@") or name.endswith("*") or name.endswith("=") or name.endswith("|"):
                        name = name[:-1]

                    if len(name) >= 2:
                        if (name.startswith("'") and name.endswith("'")) or (name.startswith('"') and name.endswith('"')):
                            name = name[1:-1]

                    cleaned_name = ""
                    i = 0
                    while i < len(name):
                        if name[i] == "\\" and i + 1 < len(name):
                            next_char = name[i + 1]
                            if next_char in ("*", "@", "=", "|", " ", "'", '"', "\\"):
                                cleaned_name += next_char
                                i += 2
                                continue
                        cleaned_name += name[i]
                        i += 1
                    name = cleaned_name

                    if name:
                        file_list.append({"name": name, "is_dir": is_dir})

                self.files_listed.emit(path, file_list, True)
            else:
                self.log_message.emit("读取目录失败 (可能无权限或路径错误)", "error")
                self.files_listed.emit(path, [], False)

        self._task_runner.start(name="files-list-basic", group="files", target=_list)

    def list_device_files_detailed(self, device_serial: str, path: str) -> None:
        def _list():
            request_token = self._symlink_request_tokens.get(device_serial, 0) + 1
            self._symlink_request_tokens[device_serial] = request_token
            if device_serial in self._symlink_workers:
                try:
                    self._symlink_workers[device_serial].stop()
                except Exception:
                    pass  # best-effort: worker thread may already be dead
                del self._symlink_workers[device_serial]

            cmd = self._cmd_manager.get_target_cmd("list_files_detailed_cmd", device_serial=device_serial, remote_path=path)
            # #region debug-point C:file-list-command
            _report_debug_event(
                "C",
                "file_manager_service.list_device_files_detailed",
                "[DEBUG] file list command prepared",
                {
                    "device_serial": device_serial,
                    "path": path,
                    "request_token": request_token,
                    "cmd": cmd,
                },
            )
            # #endregion
            with self._adb_lock:
                res = self._run_adb_command(cmd, f"列出详细文件 ({device_serial})")

            if res and res.returncode == 0:
                # #region debug-point D:file-list-success
                _report_debug_event(
                    "D",
                    "file_manager_service.list_device_files_detailed",
                    "[DEBUG] file list command succeeded",
                    {
                        "device_serial": device_serial,
                        "path": path,
                        "request_token": request_token,
                        "stdout_head": "\n".join((res.stdout or "").splitlines()[:3]),
                    },
                )
                # #endregion
                lines = res.stdout.splitlines()
                file_list = []
                for line in lines:
                    fi = self._ls_parser.parse_line(line)
                    if fi:
                        file_list.append(fi)

                def sort_key(fi):
                    type_order = {
                        FileType.DIRECTORY: 0,
                        FileType.SYMLINK: 1,
                        FileType.FILE: 2,
                        FileType.BLOCK_DEVICE: 3,
                        FileType.CHAR_DEVICE: 4,
                        FileType.FIFO: 5,
                        FileType.SOCKET: 6,
                        FileType.UNKNOWN: 7,
                    }
                    return (type_order.get(fi.file_type, 99), fi.name.lower())

                file_list.sort(key=sort_key)
                self.files_listed_detailed.emit(path, file_list, True)

                symlinks = [fi for fi in file_list if fi.file_type == FileType.SYMLINK and fi.symlink_target]
                if symlinks:
                    self._resolve_symlinks_async(device_serial, path, file_list, request_token)
            else:
                # #region debug-point C:file-list-failed
                _report_debug_event(
                    "C",
                    "file_manager_service.list_device_files_detailed",
                    "[DEBUG] file list command failed",
                    {
                        "device_serial": device_serial,
                        "path": path,
                        "request_token": request_token,
                        "returncode": None if res is None else res.returncode,
                        "stdout": "" if res is None else (res.stdout or ""),
                        "stderr": "" if res is None else (res.stderr or ""),
                    },
                )
                # #endregion
                self.log_message.emit("读取目录失败 (可能无权限或路径错误)", "error")
                self.files_listed_detailed.emit(path, [], False)

        self._task_runner.start(name="files-list-detailed", group="files", target=_list)

    def _resolve_symlinks_async(self, device_serial: str, current_path: str, file_list: list, request_token: int) -> None:
        symlinks_to_resolve = []
        for fi in file_list:
            if fi.file_type == FileType.SYMLINK and fi.symlink_target and fi.is_symlink_to_dir is None:
                full_path = fi.symlink_target
                if not full_path.startswith("/"):
                    full_path = current_path + full_path if current_path.endswith("/") else current_path + "/" + full_path
                symlinks_to_resolve.append((fi.name, full_path))

        if not symlinks_to_resolve:
            return

        worker = _SymlinkResolverWorker(self._cmd_manager, device_serial, symlinks_to_resolve, self._adb_lock)
        worker.log_message.connect(self.log_message.emit)

        def on_progress(name: str, is_dir: bool):
            if self._symlink_request_tokens.get(device_serial) != request_token:
                return
            for fi in file_list:
                if fi.name == name and fi.file_type == FileType.SYMLINK:
                    fi.is_symlink_to_dir = is_dir
                    break
            self.symlink_resolved.emit(device_serial, name, is_dir)

        worker.progress.connect(on_progress)
        self._symlink_workers[device_serial] = worker

        def _run_worker():
            try:
                worker.run()
            finally:
                worker.deleteLater()
            if self._symlink_workers.get(device_serial) is worker:
                del self._symlink_workers[device_serial]

        self._task_runner.start(name="files-resolve-symlinks", group="files", target=_run_worker)

    def _wait_for_process_exit(
        self,
        proc,
        *,
        poll_interval: float = 0.2,
        shutdown_grace_seconds: float = 3.0,
        on_shutdown_timeout: Callable[[], None] | None = None,
    ) -> int | None:
        while True:
            return_code = proc.poll()
            if return_code is not None:
                return return_code
            if not self._is_running():
                break
            time.sleep(poll_interval)

        grace_checks = max(1, int(shutdown_grace_seconds / poll_interval))
        for _ in range(grace_checks):
            return_code = proc.poll()
            if return_code is not None:
                return return_code
            time.sleep(poll_interval)

        if on_shutdown_timeout is not None:
            on_shutdown_timeout()

        for _ in range(grace_checks):
            return_code = proc.poll()
            if return_code is not None:
                return return_code
            time.sleep(poll_interval)
        return proc.poll()

    @staticmethod
    def _start_transfer_output_reader(proc) -> tuple[queue.Queue[str], threading.Event]:
        output_queue: queue.Queue[str] = queue.Queue()
        output_finished = threading.Event()

        def _reader():
            try:
                if proc.stdout is None:
                    return
                while True:
                    line = proc.stdout.readline()
                    if not line:
                        break
                    output_queue.put(line)
            except Exception:
                pass  # best-effort: stream ended or pipe broken
            finally:
                output_finished.set()

        threading.Thread(target=_reader, name="sndcpypp-transfer-output", daemon=True).start()
        return output_queue, output_finished

    def _consume_transfer_output_line(
        self,
        line: str,
        *,
        device_serial: str,
        transfer_kind: str,
        remote_path: str,
        last_output_line: str,
    ) -> str:
        line = line.strip()
        if not line:
            return last_output_line
        last_output_line = line
        percent = self._transfer_progress_parser.extract_percent(line)
        if percent is not None:
            self.file_transfer_progress.emit(
                "progress",
                device_serial,
                transfer_kind,
                remote_path,
                f"传输中: {percent}%",
                percent,
            )
        return last_output_line

    def _drain_transfer_output_queue(
        self,
        output_queue: queue.Queue[str],
        output_finished: threading.Event,
        *,
        device_serial: str,
        transfer_kind: str,
        remote_path: str,
        last_output_line: str,
        wait_seconds: float = 0.5,
        poll_interval: float = 0.05,
    ) -> str:
        deadline = time.monotonic() + wait_seconds
        while True:
            drained_any = False
            while True:
                try:
                    line = output_queue.get_nowait()
                except queue.Empty:
                    break
                drained_any = True
                last_output_line = self._consume_transfer_output_line(
                    line,
                    device_serial=device_serial,
                    transfer_kind=transfer_kind,
                    remote_path=remote_path,
                    last_output_line=last_output_line,
                )
            if output_finished.is_set() or time.monotonic() >= deadline:
                return last_output_line
            if not drained_any:
                time.sleep(poll_interval)

    def _run_transfer_with_progress(
        self,
        device_serial: str,
        cmd: list,
        desc: str,
        *,
        transfer_kind: str,
        remote_path: str = "",
        emit_done: bool = True,
    ) -> bool:
        self.file_transfer_progress.emit("start", device_serial, transfer_kind, remote_path, f"正在{desc}...", 0)
        try:
            with self._transfer_lock:
                flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
                proc = subprocess.Popen(
                    cmd,
                    creationflags=flags,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                )
                self._process_registry.register(device_serial, "transfer", proc)

                last_output_line = ""
                output_queue, output_finished = self._start_transfer_output_reader(proc)
                shutdown_requested = False
                process_exit_observed_at = None
                while True:
                    if not self._is_running():
                        shutdown_requested = True
                        break
                    try:
                        line = output_queue.get(timeout=0.2)
                    except queue.Empty:
                        if proc.poll() is not None:
                            if output_finished.is_set() and output_queue.empty():
                                break
                            if process_exit_observed_at is None:
                                process_exit_observed_at = time.monotonic()
                            elif time.monotonic() - process_exit_observed_at >= 0.5:
                                break
                        else:
                            process_exit_observed_at = None
                        continue
                    last_output_line = self._consume_transfer_output_line(
                        line,
                        device_serial=device_serial,
                        transfer_kind=transfer_kind,
                        remote_path=remote_path,
                        last_output_line=last_output_line,
                    )

                return_code = self._wait_for_process_exit(
                    proc,
                    on_shutdown_timeout=lambda: self._process_supervisor.kill_group(device_serial, "transfer"),
                )
                last_output_line = self._drain_transfer_output_queue(
                    output_queue,
                    output_finished,
                    device_serial=device_serial,
                    transfer_kind=transfer_kind,
                    remote_path=remote_path,
                    last_output_line=last_output_line,
                )
                self._process_supervisor.remove_if_present(device_serial, "transfer", proc)

                if return_code == 0:
                    if emit_done:
                        self.file_transfer_progress.emit(
                            "done",
                            device_serial,
                            transfer_kind,
                            remote_path,
                            f"{desc} 完成",
                            100,
                        )
                    return True

                if shutdown_requested and not self._is_running():
                    return False
                err = last_output_line or "目标路径无效、断开或【无权限(如Android/data目录)】"
                self.file_transfer_progress.emit(
                    "error",
                    device_serial,
                    transfer_kind,
                    remote_path,
                    f"{desc} 失败: {err}",
                    0,
                )
                return False
        except Exception as exc:
            self.file_transfer_progress.emit(
                "error",
                device_serial,
                transfer_kind,
                remote_path,
                f"{desc} 发生异常: {exc}",
                0,
            )
            return False

    def pull_file(self, device_serial: str, remote_path: str, local_dir: str, rename_to: str = None) -> None:
        clean_remote = remote_path.rstrip("/")
        if not clean_remote:
            clean_remote = "/"

        target_name = rename_to if rename_to else os.path.basename(clean_remote)
        if not target_name:
            target_name = "root"

        temp_dir = os.path.join(tempfile.gettempdir(), "sndcpy_pull_cache")
        os.makedirs(temp_dir, exist_ok=True)
        temp_target_path = os.path.join(temp_dir, str(uuid.uuid4().hex))

        cmd = self._cmd_manager.get_target_cmd(
            "pull_file_cmd",
            device_serial=device_serial,
            remote_path=clean_remote,
            local_path=temp_target_path,
        )

        def _pull_task():
            success = self._run_transfer_with_progress(
                device_serial,
                cmd,
                f"下载 {target_name}",
                transfer_kind="pull",
                emit_done=False,
            )

            if success and os.path.exists(temp_target_path):
                try:
                    real_target_path = os.path.join(local_dir, target_name)
                    if os.path.exists(real_target_path):
                        if os.path.isdir(real_target_path):
                            shutil.rmtree(real_target_path)
                        else:
                            os.remove(real_target_path)

                    shutil.move(temp_target_path, real_target_path)
                    self.log_message.emit(f"文件已成功下载并保存至: {real_target_path}", "success")
                    self.file_transfer_progress.emit(
                        "done",
                        device_serial,
                        "pull",
                        "",
                        f"下载 {target_name} 完成",
                        100,
                    )
                except Exception as exc:
                    self.file_transfer_progress.emit(
                        "error",
                        device_serial,
                        "pull",
                        "",
                        f"下载 {target_name} 失败: {str(exc)}",
                        0,
                    )
                    self.log_message.emit(f"将缓存转移至目标目录时失败: {str(exc)}", "error")
                    try:
                        if os.path.isdir(temp_target_path):
                            shutil.rmtree(temp_target_path)
                        elif os.path.exists(temp_target_path):
                            os.remove(temp_target_path)
                    except Exception:
                        pass
            elif not success and os.path.exists(temp_target_path):
                try:
                    if os.path.isdir(temp_target_path):
                        shutil.rmtree(temp_target_path)
                    else:
                        os.remove(temp_target_path)
                except Exception:
                    pass  # best-effort: temp file cleanup after failed transfer

        self._task_runner.start(name="files-pull", group="files", target=_pull_task)

    def push_file(self, device_serial: str, local_path: str, remote_dir: str, rename_to: str = None) -> None:
        if not remote_dir.endswith("/"):
            remote_dir += "/"
        target_name = rename_to if rename_to else os.path.basename(local_path.rstrip("/"))
        final_remote_path = remote_dir + target_name

        cmd = self._cmd_manager.get_target_cmd(
            "push_file_cmd",
            device_serial=device_serial,
            local_path=local_path,
            remote_path=final_remote_path,
        )
        self._task_runner.start(
            name="files-push",
            group="files",
            target=self._run_transfer_with_progress,
            args=(device_serial, cmd, f"上传 {target_name}"),
            kwargs={"transfer_kind": "push", "remote_path": remote_dir},
        )

    def stop_file_transfers(self, device_serial: Optional[str] = None) -> None:
        if device_serial is None:
            for ds in list(self._process_registry.keys()):
                self._process_supervisor.kill_group(ds, "transfer")
        else:
            self._process_supervisor.kill_group(device_serial, "transfer")
