from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class ConversationMemory:
    session_file: Path
    messages: list[dict[str, str]] = field(default_factory=list)

    def load(self) -> None:
        if not self.session_file.exists():
            return
        data = json.loads(self.session_file.read_text(encoding="utf-8"))
        self.messages = data.get("messages", [])

    def save(self) -> None:
        payload = {"messages": self.messages}
        self.session_file.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    def clear(self) -> None:
        self.messages.clear()
        if self.session_file.exists():
            self.session_file.unlink()

    def append(self, role: str, content: str) -> None:
        self.messages.append({"role": role, "content": content})
