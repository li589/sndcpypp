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

        self._add_candidate(candidates, seen, bundled_path, "内置 Sndcpy")

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
            candidate_dir = os.path.join(self._project_root, "Sndcpy")
        return os.path.abspath(os.path.join(candidate_dir, f"adb{self._ext}"))

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
        if normalized in self._viability_cache:
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

        self._viability_cache[normalized] = is_usable
        return is_usable
