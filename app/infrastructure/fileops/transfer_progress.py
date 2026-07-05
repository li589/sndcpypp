import re


class TransferProgressParser:
    _progress_pattern = re.compile(r"\[\s*(\d+)%\]")

    def extract_percent(self, line: str) -> int | None:
        match = self._progress_pattern.search(line)
        if not match:
            return None
        return int(match.group(1))
