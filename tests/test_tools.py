from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from coding_chatbot.tools import ToolRegistry


class ToolRegistryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.tools = ToolRegistry(self.root, shell_timeout_s=5)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_write_read_roundtrip(self) -> None:
        write = self.tools.write("a/b.txt", "hello")
        self.assertTrue(write.ok)
        read = self.tools.read("a/b.txt")
        self.assertTrue(read.ok)
        self.assertEqual(read.output, "hello")

    def test_path_escape_blocked(self) -> None:
        with self.assertRaises(ValueError):
            self.tools.read("../etc/passwd")

    def test_search_finds_content(self) -> None:
        self.tools.write("main.py", "print('hello world')")
        result = self.tools.search("hello")
        self.assertTrue(result.ok)
        self.assertIn("main.py:1", result.output)

    def test_run_blocked_pattern(self) -> None:
        result = self.tools.run("rm -rf /")
        self.assertFalse(result.ok)


if __name__ == "__main__":
    unittest.main()
