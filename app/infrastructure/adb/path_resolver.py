import os
import shutil
import subprocess
from dataclasses import dataclass


@dataclass(frozen=True)
class ResolvedADBPath:
    path: str
    source: str
    requested_path: str
    bundled_path: str
    used_fallback: bool


def get_platform_vendor_subdir() -> str:
    """返回当前平台对应的 vendor 子目录名（windows/macos/linux）。"""
    import sys

    if sys.platform == "win32":
        return "windows"
    if sys.platform == "darwin":
        return "macos"
    return "linux"


def resolve_apk_path(sndcpy_dir: str, project_root: str) -> str:
    """解析 sndcpy.apk 路径：优先用户 sndcpy_dir 下的同名文件，回退到 vendor/sndcpy.apk。"""
    if sndcpy_dir:
        candidate = os.path.join(sndcpy_dir, "sndcpy.apk")
        if os.path.isfile(candidate):
            return os.path.abspath(candidate)
    return os.path.abspath(os.path.join(project_root, "vendor", "sndcpy.apk"))


def resolve_vendor_tool_path(base_dir: str, tool_name: str, *, executable_ext: str | None = None) -> str:
    ext = executable_ext if executable_ext is not None else (".exe" if os.name == "nt" else "")
    candidates = [
        os.path.join(base_dir, f"{tool_name}{ext}"),
        os.path.join(base_dir, "platform-tools", f"{tool_name}{ext}"),
    ]
    if ext:
        candidates.append(os.path.join(base_dir, tool_name))
        candidates.append(os.path.join(base_dir, "platform-tools", tool_name))
    for candidate in candidates:
        if os.path.isfile(candidate):
            return os.path.abspath(candidate)
    return os.path.abspath(candidates[0])


class ADBPathResolver:
    def __init__(self, project_root: str):
        self._project_root = os.path.abspath(project_root)
        self._ext = ".exe" if os.name == "nt" else ""
        self._viability_cache: dict[str, bool] = {}

    def resolve(self, configured_path: str, sndcpy_dir: str) -> ResolvedADBPath:
        requested_path = (configured_path or "").strip()
        bundled_path = self._get_bundled_adb_path(sndcpy_dir)
        requested_is_bundled = self._same_path(requested_path, bundled_path)

        candidates: list[tuple[str, str]] = []
        seen: set[str] = set()

        if requested_path and not requested_is_bundled:
            self._add_candidate(candidates, seen, requested_path, "用户指定")

        for candidate in self._discover_external_candidates():
            self._add_candidate(candidates, seen, candidate[0], candidate[1])

        self._add_candidate(candidates, seen, bundled_path, "内置 vendor")

        for raw_path, source in candidates:
            resolved_path = self._resolve_existing_path(raw_path)
            if resolved_path and self._is_usable_adb(resolved_path):
                used_fallback = bool(requested_path) and not self._same_path(requested_path, resolved_path)
                return ResolvedADBPath(
                    path=resolved_path,
                    source=source,
                    requested_path=requested_path,
                    bundled_path=bundled_path,
                    used_fallback=used_fallback,
                )

        fallback_path = requested_path or bundled_path or f"adb{self._ext}"
        return ResolvedADBPath(
            path=fallback_path,
            source="未解析",
            requested_path=requested_path,
            bundled_path=bundled_path,
            used_fallback=bool(requested_path and not self._same_path(requested_path, fallback_path)),
        )

    def _discover_external_candidates(self) -> list[tuple[str, str]]:
        candidates: list[tuple[str, str]] = []

        for executable_name in (f"adb{self._ext}", "adb"):
            path_from_env = shutil.which(executable_name)
            if path_from_env:
                candidates.append((path_from_env, "环境变量 PATH"))

        sdk_roots = [
            os.environ.get("ANDROID_SDK_ROOT", ""),
            os.environ.get("ANDROID_HOME", ""),
            os.path.join(os.environ.get("LOCALAPPDATA", ""), "Android", "Sdk"),
            os.path.join(os.path.expanduser("~"), "AppData", "Local", "Android", "Sdk"),
        ]
        for sdk_root in sdk_roots:
            if not sdk_root:
                continue
            candidates.append((os.path.join(sdk_root, "platform-tools", f"adb{self._ext}"), "Android SDK"))

        return candidates

    def _get_bundled_adb_path(self, sndcpy_dir: str) -> str:
        candidate_dir = (sndcpy_dir or "").strip()
        if not candidate_dir:
            candidate_dir = os.path.join(self._project_root, "vendor", get_platform_vendor_subdir())
        return resolve_vendor_tool_path(candidate_dir, "adb", executable_ext=self._ext)

    def _resolve_existing_path(self, raw_path: str) -> str:
        if not raw_path:
            return ""

        if os.path.isabs(raw_path) or os.path.dirname(raw_path):
            abs_path = os.path.abspath(raw_path)
            if os.path.isfile(abs_path):
                return abs_path
            return ""

        path_from_env = shutil.which(raw_path)
        if path_from_env and os.path.isfile(path_from_env):
            return os.path.abspath(path_from_env)
        return ""

    def _add_candidate(
        self,
        candidates: list[tuple[str, str]],
        seen: set[str],
        raw_path: str,
        source: str,
    ) -> None:
        normalized = self._normalize_path(raw_path)
        if not normalized or normalized in seen:
            return
        seen.add(normalized)
        candidates.append((raw_path, source))

    def _normalize_path(self, raw_path: str) -> str:
        if not raw_path:
            return ""
        return os.path.normcase(os.path.abspath(raw_path))

    def _same_path(self, left: str, right: str) -> bool:
        if not left or not right:
            return False
        return self._normalize_path(left) == self._normalize_path(right)

    def _is_usable_adb(self, adb_path: str) -> bool:
        normalized = self._normalize_path(adb_path)
        if self._viability_cache.get(normalized):
            return self._viability_cache[normalized]

        try:
            flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
            result = subprocess.run(
                [adb_path, "version"],
                capture_output=True,
                text=True,
                timeout=5,
                creationflags=flags,
                encoding="utf-8",
                errors="replace",
            )
            is_usable = result.returncode == 0
        except Exception:
            is_usable = False

        if is_usable:
            self._viability_cache[normalized] = True
        else:
            self._viability_cache.pop(normalized, None)
        return is_usable
