from __future__ import annotations

import json
from dataclasses import dataclass
from urllib import request, error


@dataclass
class ChatModel:
    api_base: str
    api_key: str | None
    model: str
    mock_mode: bool = False

    def complete(self, messages: list[dict[str, str]]) -> str:
        if self.mock_mode:
            last_user = next((m["content"] for m in reversed(messages) if m["role"] == "user"), "")
            return (
                "[MOCK MODE] I cannot call a remote model right now, but here is a practical plan:\n"
                f"1) Understand goal: {last_user[:120]}\n"
                "2) Break into modules\n3) Implement incremental changes\n"
                "4) Run tests and iterate."
            )

        if not self.api_key:
            raise RuntimeError("CHATBOT_API_KEY is missing. Set it or enable CHATBOT_MOCK=1.")

        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": 0.2,
        }
        body = json.dumps(payload).encode("utf-8")
        req = request.Request(
            url=f"{self.api_base.rstrip('/')}/chat/completions",
            method="POST",
            data=body,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.api_key}",
            },
        )
        try:
            with request.urlopen(req, timeout=60) as resp:
                data = json.loads(resp.read().decode("utf-8"))
        except error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="ignore")
            raise RuntimeError(f"Model API error: {exc.code} {detail}") from exc

        try:
            return data["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise RuntimeError(f"Unexpected model response: {data}") from exc
