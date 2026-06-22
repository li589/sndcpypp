from enum import Enum


class FileType(Enum):
    DIRECTORY = "dir"
    SYMLINK = "link"
    FILE = "file"
    BLOCK_DEVICE = "block"
    CHAR_DEVICE = "char"
    FIFO = "fifo"
    SOCKET = "socket"
    UNKNOWN = "unknown"
