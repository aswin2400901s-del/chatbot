from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


def _env_bool(key: str, default: bool = False) -> bool:
    value = os.getenv(key)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class ChatbotConfig:
    model: str = os.getenv("CHATBOT_MODEL", "gpt-4o-mini")
    api_base: str = os.getenv("CHATBOT_API_BASE", "https://api.openai.com/v1")
    api_key: str | None = os.getenv("CHATBOT_API_KEY")
    session_file: Path = Path(os.getenv("CHATBOT_SESSION_FILE", ".chatbot_session.json"))
    workspace_root: Path = Path(os.getenv("CHATBOT_ROOT", os.getcwd())).resolve()
    mock_mode: bool = _env_bool("CHATBOT_MOCK", False)
    max_context_messages: int = int(os.getenv("CHATBOT_MAX_CONTEXT_MESSAGES", "30"))
    shell_timeout_s: int = int(os.getenv("CHATBOT_SHELL_TIMEOUT", "120"))
