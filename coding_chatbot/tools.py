from __future__ import annotations

import platform
import subprocess
from dataclasses import dataclass
from pathlib import Path


BLOCKED_PATTERNS = ["rm -rf /", ":(){:|:&};:", "mkfs", "dd if="]


@dataclass
class ToolResult:
    ok: bool
    output: str


class ToolRegistry:
    def __init__(self, root: Path, shell_timeout_s: int = 120):
        self.root = root.resolve()
        self.shell_timeout_s = shell_timeout_s

    def help(self) -> str:
        return (
            "Tools: read(path), write(path,text), ls(path='.'), search(pattern), "
            "run(command), sysinfo()"
        )

    def _resolve(self, rel_path: str) -> Path:
        target = (self.root / rel_path).resolve()
        if not str(target).startswith(str(self.root)):
            raise ValueError("Path escapes workspace root")
        return target

    def read(self, rel_path: str) -> ToolResult:
        p = self._resolve(rel_path)
        if not p.exists() or not p.is_file():
            return ToolResult(False, f"File not found: {rel_path}")
        return ToolResult(True, p.read_text(encoding="utf-8", errors="replace"))

    def write(self, rel_path: str, text: str) -> ToolResult:
        p = self._resolve(rel_path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8")
        return ToolResult(True, f"Wrote {len(text)} bytes to {rel_path}")

    def ls(self, rel_path: str = ".") -> ToolResult:
        p = self._resolve(rel_path)
        if not p.exists():
            return ToolResult(False, f"Path not found: {rel_path}")
        entries = sorted(p.iterdir(), key=lambda x: (x.is_file(), x.name.lower()))
        return ToolResult(True, "\n".join(str(e.relative_to(self.root)) for e in entries))

    def search(self, pattern: str) -> ToolResult:
        matches: list[str] = []
        for f in self.root.rglob("*"):
            if not f.is_file() or ".git" in f.parts:
                continue
            try:
                lines = f.read_text(encoding="utf-8", errors="ignore").splitlines()
            except OSError:
                continue
            for i, line in enumerate(lines, start=1):
                if pattern.lower() in line.lower():
                    matches.append(f"{f.relative_to(self.root)}:{i}:{line[:200]}")
        if not matches:
            return ToolResult(True, "No matches")
        return ToolResult(True, "\n".join(matches[:500]))

    def run(self, command: str) -> ToolResult:
        lowered = command.lower()
        if any(pat in lowered for pat in BLOCKED_PATTERNS):
            return ToolResult(False, "Command blocked by safety policy")
        proc = subprocess.run(
            command,
            shell=True,
            cwd=self.root,
            text=True,
            capture_output=True,
            timeout=self.shell_timeout_s,
        )
        out = (proc.stdout or "") + ("\n" + proc.stderr if proc.stderr else "")
        prefix = f"exit_code={proc.returncode}\n"
        return ToolResult(proc.returncode == 0, prefix + out.strip())

    def sysinfo(self) -> ToolResult:
        return ToolResult(
            True,
            f"platform={platform.platform()}\npython={platform.python_version()}\nroot={self.root}",
        )
