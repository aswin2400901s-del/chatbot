from __future__ import annotations

import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

from coding_chatbot.agent import CodingChatAgent
from coding_chatbot.config import ChatbotConfig


class AgentTests(unittest.TestCase):
    def test_mock_response_and_memory(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            cfg = ChatbotConfig()
            cfg = replace(
                cfg,
                workspace_root=root,
                session_file=root / "session.json",
                mock_mode=True,
            )
            agent = CodingChatAgent(cfg)
            out = agent.ask("build a parser")
            self.assertIn("[MOCK MODE]", out)
            self.assertTrue((root / "session.json").exists())


if __name__ == "__main__":
    unittest.main()
