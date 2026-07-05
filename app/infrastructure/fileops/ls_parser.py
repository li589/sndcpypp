import re

from app.domain.enums.file_type import FileType
from app.domain.models.file_info import FileInfo


class LSAllParser:
    def parse_line(self, line: str) -> FileInfo | None:
        line = line.strip()
        if not line or line.startswith("total"):
            return None

        parts = line.split()
        if len(parts) < 4:
            return None

        perms = parts[0]
        if len(perms) < 10 or (perms[0] not in ("-", "b", "c", "d", "l", "p", "s") and perms[0] != "?"):
            return None

        idx = 1
        if parts[idx].isdigit() or parts[idx] == "?":
            idx += 1

        if idx >= len(parts):
            return None
        owner = parts[idx]
        idx += 1

        if idx >= len(parts):
            return None
        group = parts[idx]
        idx += 1

        if idx >= len(parts):
            return None
        size_str = parts[idx]
        idx += 1

        try:
            size = int(size_str)
        except ValueError:
            size = 0

        date_parts = []
        while idx < len(parts) - 1 and len(date_parts) < 3:
            part = parts[idx]
            is_date = False

            if (
                re.match(r"^\d{4}-\d{2}-\d{2}$", part)
                or re.match(r"^\d{2}:\d{2}(:\d{2})?(\.\d+)?$", part)
                or re.match(r"^\.\d+$", part)
                or re.match(r"^[+-]\d{4}$", part)
                or re.match(r"^(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)$", part, re.IGNORECASE)
                or part == "?"
            ):
                is_date = True
            elif re.match(r"^\d{1,2}$", part) or re.match(r"^\d{4}$", part):
                if len(date_parts) > 0 and re.match(r"^[A-Za-z]+$", date_parts[0]):
                    is_date = True

            if is_date:
                date_parts.append(part)
                idx += 1
            else:
                break

        date_str = " ".join(date_parts)
        remaining = parts[idx:]

        if "->" in remaining and perms.startswith("l"):
            arrow_idx = remaining.index("->")
            filename = " ".join(remaining[:arrow_idx])
            symlink_target = " ".join(remaining[arrow_idx + 1 :])
        else:
            filename = " ".join(remaining)
            symlink_target = ""

        if not filename or filename in (".", ".."):
            return None

        file_type_map = {
            "d": FileType.DIRECTORY,
            "l": FileType.SYMLINK,
            "-": FileType.FILE,
            "b": FileType.BLOCK_DEVICE,
            "c": FileType.CHAR_DEVICE,
            "p": FileType.FIFO,
            "s": FileType.SOCKET,
        }

        type_char = perms[0]
        if type_char == "?" and "->" in line:
            type_char = "l"
        elif type_char == "?":
            type_char = "-"

        file_type = file_type_map.get(type_char, FileType.UNKNOWN)

        return FileInfo(
            name=filename,
            file_type=file_type,
            type_char=type_char,
            permissions=perms,
            owner=owner,
            group=group,
            size=size,
            date_str=date_str,
            symlink_target=symlink_target,
            raw_line=line,
        )
