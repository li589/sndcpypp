import os
import subprocess


class ScrcpyCapabilitiesProbe:
    def __init__(self):
        self._cache: dict[str, dict] = {}

    def probe(self, scrcpy_path: str) -> dict:
        default_features = {
            "display_ori": False,
            "record_ori": False,
            "capture_ori": False,
            "lock_video_ori": False,
            "degrees": False,
            "no_playback": "--no-playback",
        }
        if not scrcpy_path or not os.path.exists(scrcpy_path):
            return default_features
        if scrcpy_path in self._cache:
            return self._cache[scrcpy_path]

        features = default_features.copy()
        try:
            flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
            res = subprocess.run(
                [scrcpy_path, "--help"], capture_output=True, text=True, creationflags=flags, timeout=10
            )
            help_text = res.stdout + res.stderr
            if "--display-orientation" in help_text:
                features["display_ori"] = True
            if "--record-orientation" in help_text:
                features["record_ori"] = True
            if "--capture-orientation" in help_text:
                features["capture_ori"] = True
            if "--lock-video-orientation" in help_text:
                features["lock_video_ori"] = True

            if "--no-playback" in help_text:
                features["no_playback"] = "--no-playback"
            elif "--no-display" in help_text:
                features["no_playback"] = "--no-display"

            for flag in ["--display-orientation", "--capture-orientation", "--lock-video-orientation"]:
                idx = help_text.find(flag)
                if idx != -1:
                    chunk = help_text[idx : idx + 300]
                    if "90" in chunk and "180" in chunk:
                        features["degrees"] = True
                    break
        except Exception:
            pass

        self._cache[scrcpy_path] = features
        return features
