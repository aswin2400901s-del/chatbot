# Coding AI Chatbot (System-Heavy Task Assistant)

A local-first AI chatbot focused on coding and heavyweight engineering workflows:

- Repository-aware file operations (read/write/search/list)
- Safe command execution with timeout controls
- Session memory persisted across chats
- OpenAI-compatible model endpoint support
- Built-in fallback "mock mode" for offline testing
- Extensible tool registry for adding custom actions

## Quick start

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -U pip
python -m coding_chatbot.cli --help
```

## Environment variables

- `CHATBOT_MODEL` (default: `gpt-4o-mini`)
- `CHATBOT_API_BASE` (default: `https://api.openai.com/v1`)
- `CHATBOT_API_KEY` (required for real model calls)
- `CHATBOT_SESSION_FILE` (default: `.chatbot_session.json`)
- `CHATBOT_ROOT` (default: current working directory)
- `CHATBOT_MOCK` (`1`/`true` enables mock responses)

## Run

```bash
python -m coding_chatbot.cli
```

### Useful slash commands

- `/help` show command help
- `/tools` show available tools
- `/run <cmd>` run shell command
- `/read <path>` read file
- `/write <path> <text>` write file
- `/search <pattern>` search across files
- `/ls [path]` list files
- `/clear` clear conversation memory
- `/exit` quit

## Architecture

- `coding_chatbot/agent.py` orchestrates model + tools
- `coding_chatbot/model.py` calls OpenAI-compatible chat completions
- `coding_chatbot/tools.py` contains system/file/code tooling
- `coding_chatbot/memory.py` persists multi-turn conversation state
- `coding_chatbot/cli.py` provides interactive terminal UX

## Security notes

- Commands are executed within a configurable workspace root.
- Potentially destructive shell commands are blocked by default patterns.
- File actions are path-sandboxed to the workspace root.

## Testing

```bash
python -m unittest discover -s tests -p 'test_*.py' -v
```
