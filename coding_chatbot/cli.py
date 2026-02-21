from __future__ import annotations

import argparse
import shlex
from dataclasses import replace

from .agent import CodingChatAgent
from .config import ChatbotConfig


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Coding AI chatbot for heavy system tasks")
    p.add_argument("--mock", action="store_true", help="Enable offline mock mode")
    return p


def main() -> None:
    args = build_parser().parse_args()
    base = ChatbotConfig()
    config = replace(base, mock_mode=(args.mock or base.mock_mode))
    agent = CodingChatAgent(config)

    print("Coding Chatbot ready. Type /help for commands.")

    while True:
        try:
            user = input("\nYou> ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nBye.")
            break

        if not user:
            continue

        if user == "/exit":
            print("Bye.")
            break
        if user == "/help":
            print(
                "Commands: /help /tools /clear /exit /run <cmd> /read <file> /write <file> <text> /search <pattern> /ls [path]"
            )
            continue
        if user == "/tools":
            print(agent.available_tools())
            continue
        if user == "/clear":
            agent.clear()
            print("Session cleared.")
            continue

        if user.startswith("/run "):
            cmd = user[len("/run ") :]
            r = agent.tools.run(cmd)
            print(r.output)
            continue
        if user.startswith("/read "):
            path = user[len("/read ") :]
            r = agent.tools.read(path)
            print(r.output)
            continue
        if user.startswith("/write "):
            parts = shlex.split(user)
            if len(parts) < 3:
                print("Usage: /write <path> <text>")
                continue
            path = parts[1]
            text = " ".join(parts[2:])
            r = agent.tools.write(path, text)
            print(r.output)
            continue
        if user.startswith("/search "):
            pattern = user[len("/search ") :]
            r = agent.tools.search(pattern)
            print(r.output)
            continue
        if user.startswith("/ls"):
            path = user[len("/ls") :].strip() or "."
            r = agent.tools.ls(path)
            print(r.output)
            continue

        try:
            response = agent.ask(user)
        except Exception as exc:  # runtime surface for API/network/config errors
            print(f"Error: {exc}")
            continue
        print(f"\nAssistant> {response}")


if __name__ == "__main__":
    main()
