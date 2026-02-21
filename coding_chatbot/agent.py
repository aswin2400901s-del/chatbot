from __future__ import annotations

from dataclasses import dataclass

from .config import ChatbotConfig
from .memory import ConversationMemory
from .model import ChatModel
from .tools import ToolRegistry


SYSTEM_PROMPT = """You are a senior software engineering assistant for system-heavy coding tasks.
Always:
- Propose a short plan before large changes.
- Suggest tests/verification commands.
- Prefer incremental, reversible edits.
- Explain tradeoffs and performance implications.
"""


@dataclass
class CodingChatAgent:
    config: ChatbotConfig

    def __post_init__(self) -> None:
        self.memory = ConversationMemory(self.config.session_file)
        self.memory.load()
        self.tools = ToolRegistry(self.config.workspace_root, self.config.shell_timeout_s)
        self.model = ChatModel(
            api_base=self.config.api_base,
            api_key=self.config.api_key,
            model=self.config.model,
            mock_mode=self.config.mock_mode,
        )

    def available_tools(self) -> str:
        return self.tools.help()

    def ask(self, text: str) -> str:
        self.memory.append("user", text)
        messages = [{"role": "system", "content": SYSTEM_PROMPT}] + self.memory.messages[-self.config.max_context_messages :]
        response = self.model.complete(messages)
        self.memory.append("assistant", response)
        self.memory.save()
        return response

    def clear(self) -> None:
        self.memory.clear()
