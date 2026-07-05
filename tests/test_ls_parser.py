import unittest

from app.domain.enums.file_type import FileType
from app.infrastructure.fileops.ls_parser import LSAllParser


class LSAllParserTests(unittest.TestCase):
    def setUp(self):
        self.parser = LSAllParser()

    def test_parse_standard_directory_line(self):
        line = "drwxr-xr-x  2  root  root  4096  2024-01-01 12:00  dirname"

        info = self.parser.parse_line(line)

        self.assertIsNotNone(info)
        self.assertEqual(info.name, "dirname")
        self.assertEqual(info.file_type, FileType.DIRECTORY)
        self.assertEqual(info.type_char, "d")
        self.assertEqual(info.permissions, "drwxr-xr-x")
        self.assertEqual(info.owner, "root")
        self.assertEqual(info.group, "root")
        self.assertEqual(info.size, 4096)
        self.assertEqual(info.date_str, "2024-01-01 12:00")
        self.assertEqual(info.symlink_target, "")
        self.assertEqual(info.raw_line, line)
        self.assertTrue(info.is_dir)
        self.assertTrue(info.is_root_owned)

    def test_parse_standard_file_line(self):
        line = "-rw-r--r--  1  shell  shell  1024  2024-01-01 12:00  filename.txt"

        info = self.parser.parse_line(line)

        self.assertIsNotNone(info)
        self.assertEqual(info.name, "filename.txt")
        self.assertEqual(info.file_type, FileType.FILE)
        self.assertEqual(info.type_char, "-")
        self.assertEqual(info.permissions, "-rw-r--r--")
        self.assertEqual(info.owner, "shell")
        self.assertEqual(info.group, "shell")
        self.assertEqual(info.size, 1024)
        self.assertEqual(info.date_str, "2024-01-01 12:00")
        self.assertEqual(info.symlink_target, "")
        self.assertFalse(info.is_dir)
        self.assertFalse(info.is_root_owned)

    def test_parse_symlink_with_target(self):
        line = "lrwxrwxrwx  1  root  root  10  2024-01-01 12:00  link -> target"

        info = self.parser.parse_line(line)

        self.assertIsNotNone(info)
        self.assertEqual(info.name, "link")
        self.assertEqual(info.file_type, FileType.SYMLINK)
        self.assertEqual(info.type_char, "l")
        self.assertEqual(info.permissions, "lrwxrwxrwx")
        self.assertEqual(info.size, 10)
        self.assertEqual(info.symlink_target, "target")
        self.assertTrue(info.is_symlink)

    def test_parse_symlink_target_with_spaces(self):
        line = "lrwxrwxrwx  1  root  root  10  2024-01-01 12:00  link -> some target path"

        info = self.parser.parse_line(line)

        self.assertIsNotNone(info)
        self.assertEqual(info.name, "link")
        self.assertEqual(info.symlink_target, "some target path")

    def test_parse_root_owner_with_numeric_uid(self):
        line = "-rw-r--r--  1  0  0  1024  2024-01-01 12:00  filename.txt"

        info = self.parser.parse_line(line)

        self.assertIsNotNone(info)
        self.assertEqual(info.owner, "0")
        self.assertEqual(info.group, "0")
        self.assertTrue(info.is_root_owned)

    def test_parse_returns_none_for_empty_line(self):
        self.assertIsNone(self.parser.parse_line(""))
        self.assertIsNone(self.parser.parse_line("   "))
        self.assertIsNone(self.parser.parse_line("\t\t"))

    def test_parse_returns_none_for_total_header(self):
        self.assertIsNone(self.parser.parse_line("total 1234"))
        self.assertIsNone(self.parser.parse_line("total"))

    def test_parse_line_without_link_count(self):
        line = "drwxr-xr-x  root  root  4096  2024-01-01 12:00  dirname"

        info = self.parser.parse_line(line)

        self.assertIsNotNone(info)
        self.assertEqual(info.name, "dirname")
        self.assertEqual(info.owner, "root")
        self.assertEqual(info.group, "root")
        self.assertEqual(info.size, 4096)
        self.assertEqual(info.date_str, "2024-01-01 12:00")
        self.assertEqual(info.file_type, FileType.DIRECTORY)

    def test_parse_question_mark_permissions(self):
        line = "?rw-r--r--  1  root  root  4096  2024-01-01 12:00  filename.txt"

        info = self.parser.parse_line(line)

        self.assertIsNotNone(info)
        self.assertEqual(info.permissions, "?rw-r--r--")
        self.assertEqual(info.type_char, "-")
        self.assertEqual(info.file_type, FileType.FILE)
        self.assertEqual(info.name, "filename.txt")

    def test_parse_chinese_filename(self):
        line = "drwxr-xr-x  2  root  root  4096  2024-01-01 12:00  中文目录"

        info = self.parser.parse_line(line)

        self.assertIsNotNone(info)
        self.assertEqual(info.name, "中文目录")
        self.assertEqual(info.file_type, FileType.DIRECTORY)
        self.assertEqual(info.date_str, "2024-01-01 12:00")

    def test_parse_filename_with_spaces(self):
        line = "drwxr-xr-x  2  root  root  4096  2024-01-01 12:00  my folder name"

        info = self.parser.parse_line(line)

        self.assertIsNotNone(info)
        self.assertEqual(info.name, "my folder name")
        self.assertEqual(info.file_type, FileType.DIRECTORY)

    def test_parse_returns_none_for_dot_and_dotdot(self):
        self.assertIsNone(self.parser.parse_line("drwxr-xr-x  2  root  root  4096  2024-01-01 12:00  ."))
        self.assertIsNone(self.parser.parse_line("drwxr-xr-x  2  root  root  4096  2024-01-01 12:00  .."))

    def test_parse_returns_none_for_short_line(self):
        self.assertIsNone(self.parser.parse_line("drwxr-xr-x"))

    def test_parse_returns_none_for_invalid_perms_prefix(self):
        self.assertIsNone(self.parser.parse_line("xyz  1  root  root  4096  2024-01-01 12:00  filename.txt"))

    def test_parse_month_name_date_format(self):
        line = "drwxr-xr-x  2  root  root  4096  Jan  1  2024  dirname"

        info = self.parser.parse_line(line)

        self.assertIsNotNone(info)
        self.assertEqual(info.name, "dirname")
        self.assertEqual(info.date_str, "Jan 1 2024")
        self.assertEqual(info.size, 4096)

    def test_parse_strips_leading_and_trailing_whitespace(self):
        line = "  drwxr-xr-x  2  root  root  4096  2024-01-01 12:00  dirname  "

        info = self.parser.parse_line(line)

        self.assertIsNotNone(info)
        self.assertEqual(info.name, "dirname")
        self.assertEqual(info.raw_line, "drwxr-xr-x  2  root  root  4096  2024-01-01 12:00  dirname")

    def test_parse_non_numeric_size_falls_back_to_zero(self):
        line = "drwxr-xr-x  2  root  root  -  2024-01-01 12:00  dirname"

        info = self.parser.parse_line(line)

        self.assertIsNotNone(info)
        self.assertEqual(info.size, 0)


if __name__ == "__main__":
    unittest.main()
