"""PostToolUse hook: format the file just edited via the tool implied by its
extension, and lint it when the language has a linter instead of a formatter.
Silently skips when the tool is not installed or the file has no configured
tool. This module is the source of truth for which tool maps to which file
type.

Its matcher covers Write, Edit, and MultiEdit only, so a file produced by a
shell redirect or a heredoc is neither formatted nor linted. That gap is
accepted: routing every Bash call through a formatter would cost more than
the occasional unformatted file."""

import json
import re
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


SHELL_EXTS = {".sh", ".bash"}
# Repository scripts often carry no extension, so the shebang decides.
# \b keeps zsh and fish out while matching sh, bash, and env-style shebangs.
SHEBANG_RE = re.compile(r"^#!.*\b(?:ba)?sh\b")
SHEBANG_READ_BYTES = 128


def build_argv(path: Path) -> list[str] | None:
    ext = path.suffix.lower()
    if ext == ".py":
        return ["ruff", "format", str(path)]
    if ext in PRETTIER_EXTS:
        return ["prettier", "--write", str(path)]
    return None


def is_shell_script(path: Path) -> bool:
    if path.suffix.lower() in SHELL_EXTS:
        return True
    try:
        with path.open("rb") as handle:
            head = handle.read(SHEBANG_READ_BYTES)
    except OSError:
        return False
    return bool(SHEBANG_RE.match(head.decode("utf-8", "replace")))


def lint_shell(path: Path) -> None:
    if not shutil.which("shellcheck"):
        return
    try:
        result = subprocess.run(
            ["shellcheck", str(path)],
            capture_output=True,
            text=True,
            timeout=TIMEOUT_SEC,
            check=False,
        )
    except (subprocess.TimeoutExpired, OSError):
        return
    # A non-zero exit with nothing on stdout means shellcheck failed to run at
    # all, and an empty finding list is worse than silence.
    if result.returncode == 0 or not result.stdout.strip():
        return
    # shellcheck reports rather than rewrites, so the findings go back as
    # context instead of being applied to the file.
    print(
        json.dumps(
            {
                "hookSpecificOutput": {
                    "hookEventName": "PostToolUse",
                    "additionalContext": (
                        f"shellcheck reported issues in {path}:\n{result.stdout}"
                    ),
                }
            }
        )
    )


def run_hook() -> None:
    try:
        event = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        return

    file_path = (event.get("tool_input") or {}).get("file_path")
    if not file_path:
        return

    path = Path(file_path)
    # The extension decides first: a .md or .py file opening with a shell
    # shebang is still a .md or .py file.
    argv = build_argv(path)
    if not argv:
        if is_shell_script(path):
            lint_shell(path)
        return
    if not shutil.which(argv[0]):
        return

    try:
        subprocess.run(argv, capture_output=True, timeout=TIMEOUT_SEC, check=False)
    except (subprocess.TimeoutExpired, OSError):
        return


if __name__ == "__main__":
    run_hook()
