"""PostToolUse hook: format the file just edited via the tool implied by its
extension. Silently skips when the formatter is not installed or the file
extension has no configured formatter. ~/.claude/rules/formatter.md is the
source of truth for which formatter maps to which extension."""

import json
import shutil
import subprocess
import sys
from pathlib import Path

TIMEOUT_SEC = 15

PRETTIER_EXTS = {
    ".css",
    ".scss",
    ".html",
    ".htm",
    ".json",
    ".jsonc",
    ".yaml",
    ".yml",
    ".md",
    ".js",
    ".mjs",
    ".cjs",
    ".ts",
    ".tsx",
    ".jsx",
}


def build_argv(path: Path) -> list[str] | None:
    ext = path.suffix.lower()
    if ext == ".py":
        return ["ruff", "format", str(path)]
    if ext in PRETTIER_EXTS:
        return ["prettier", "--write", str(path)]
    return None


def run_hook() -> None:
    try:
        event = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        return

    file_path = (event.get("tool_input") or {}).get("file_path")
    if not file_path:
        return

    argv = build_argv(Path(file_path))
    if not argv:
        return
    if not shutil.which(argv[0]):
        return

    try:
        subprocess.run(argv, capture_output=True, timeout=TIMEOUT_SEC, check=False)
    except (subprocess.TimeoutExpired, OSError):
        return


if __name__ == "__main__":
    run_hook()
