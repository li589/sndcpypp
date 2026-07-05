import unittest

from app.infrastructure.fileops.transfer_progress import TransferProgressParser


class TransferProgressParserTests(unittest.TestCase):
    def setUp(self):
        self.parser = TransferProgressParser()

    def test_extract_percent_from_normal_progress(self):
        self.assertEqual(self.parser.extract_percent("[ 45%] /sdcard/file.txt"), 45)

    def test_extract_percent_100_complete(self):
        self.assertEqual(self.parser.extract_percent("[100%] /sdcard/Download/demo.txt: 1 file pushed."), 100)

    def test_extract_percent_with_leading_spaces(self):
        self.assertEqual(self.parser.extract_percent("[  5%]"), 5)
        self.assertEqual(self.parser.extract_percent("[   5%]"), 5)

    def test_extract_percent_zero(self):
        self.assertEqual(self.parser.extract_percent("[0%]"), 0)
        self.assertEqual(self.parser.extract_percent("[ 0%]"), 0)

    def test_extract_percent_returns_none_for_no_match(self):
        self.assertIsNone(self.parser.extract_percent("some random text without percent"))
        self.assertIsNone(self.parser.extract_percent("45% without brackets"))
        self.assertIsNone(self.parser.extract_percent("[]"))

    def test_extract_percent_returns_none_for_empty_string(self):
        self.assertIsNone(self.parser.extract_percent(""))

    def test_extract_percent_returns_first_match_for_multiple(self):
        self.assertEqual(self.parser.extract_percent("[30%] [60%]"), 30)

    def test_extract_percent_from_realistic_adb_push_line(self):
        line = "[ 75%] /sdcard/Download/demo.txt: 1 file pushed, 0 skipped. 2.5 MB/s (1500000 bytes in 0.600s)"

        self.assertEqual(self.parser.extract_percent(line), 75)

    def test_extract_percent_from_realistic_adb_pull_line(self):
        line = "[ 80%] /sdcard/Download/demo.txt: 1 file pulled. 0 skipped. 1.2 MB/s"

        self.assertEqual(self.parser.extract_percent(line), 80)

    def test_extract_percent_handles_full_width_brackets_not_matched(self):
        self.assertIsNone(self.parser.extract_percent("【 50%】"))

    def test_extract_percent_preserves_value_for_max_progress(self):
        self.assertEqual(self.parser.extract_percent("[100%]"), 100)


if __name__ == "__main__":
    unittest.main()
