from dataclasses import dataclass

from app.domain.enums.file_type import FileType


@dataclass
class FileInfo:
    name: str
    file_type: FileType
    type_char: str
    permissions: str
    owner: str
    group: str
    size: int
    date_str: str
    symlink_target: str = ""
    is_symlink_to_dir: bool | None = None
    raw_line: str = ""

    @property
    def is_dir(self) -> bool:
        if self.file_type == FileType.DIRECTORY:
            return True
        if self.file_type == FileType.SYMLINK:
            return self.is_symlink_to_dir is True
        return False

    @property
    def is_symlink(self) -> bool:
        return self.file_type == FileType.SYMLINK

    @property
    def is_root_owned(self) -> bool:
        return self.owner in ("root", "0")

    @property
    def type_char_display(self) -> str:
        if self.file_type == FileType.SYMLINK:
            return "l→d" if self.is_symlink_to_dir else ("l→f" if self.is_symlink_to_dir is False else "l→?")
        return self.type_char

    @property
    def type_description(self) -> str:
        mapping = {
            "d": "目录",
            "l": "符号链接",
            "-": "文件",
            "b": "块设备",
            "c": "字符设备",
            "p": "管道",
            "s": "socket",
        }
        base = mapping.get(self.type_char, "未知")
        if self.file_type == FileType.SYMLINK:
            if self.is_symlink_to_dir is True:
                return "链接→目录"
            if self.is_symlink_to_dir is False:
                return "链接→文件"
            return "链接→?"
        return base

    @property
    def size_display(self) -> str:
        if self.file_type == FileType.DIRECTORY:
            return "<DIR>"
        if self.file_type == FileType.SYMLINK and self.is_symlink_to_dir is True:
            return "<DIR>"
        s = self.size
        if s < 1024:
            return f"{s} B"
        if s < 1024 * 1024:
            return f"{s / 1024:.1f} KB"
        if s < 1024 * 1024 * 1024:
            return f"{s / (1024 * 1024):.1f} MB"
        return f"{s / (1024 * 1024 * 1024):.2f} GB"
