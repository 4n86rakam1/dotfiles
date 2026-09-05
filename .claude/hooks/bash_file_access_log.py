"""PreToolUse(Bash) hook: record which files a Bash command touches. Never blocks.

Path-scoped rules and nested CLAUDE.md files load only when the Read tool opens a
matching file, so a Bash read leaves them silently absent. InstructionsLoaded logs
the loads that did happen; this log supplies the misses they have to be measured
against.
"""

import importlib.util
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

LOG_PATH = os.path.expanduser("~/.claude/logs/bash-file-access.jsonl")
# Resolved from this file so a worktree checkout uses its own copy of the
# classifier rather than whatever the main checkout happens to have.
CLASSIFIER_PATH = (
    Path(__file__).resolve().parent.parent / "skills" / "tool-mix-audit" / "audit.py"
)


def load_targets(command):
    spec = importlib.util.spec_from_file_location(
        "tool_mix_audit", str(CLASSIFIER_PATH)
    )
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load the classifier from {CLASSIFIER_PATH}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.bash_file_targets(command)


def main():
    event = json.load(sys.stdin)
    if event.get("tool_name") != "Bash":
        return
    command = (event.get("tool_input") or {}).get("command") or ""
    targets = load_targets(command)
    if not targets:
        return

    cwd = event.get("cwd") or os.getcwd()
    record = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "session_id": event.get("session_id"),
        "cwd": cwd,
        "permission_mode": event.get("permission_mode"),
        "agent_id": event.get("agent_id"),
        # Only resolved paths are kept: a command line can carry tokens and keys.
        "targets": [
            {"family": family, "path": resolve(path, cwd)} for family, path in targets
        ],
    }
    append(record)


def resolve(path, cwd):
    return os.path.normpath(os.path.join(cwd, os.path.expanduser(path)))


def append(record):
    """Write owner-only: the log holds every path this machine's sessions touch."""
    os.makedirs(os.path.dirname(LOG_PATH), mode=0o700, exist_ok=True)
    descriptor = os.open(LOG_PATH, os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o600)
    with os.fdopen(descriptor, "a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, ensure_ascii=False) + "\n")


if __name__ == "__main__":
    try:
        main()
    except Exception:
        # This hook runs before every Bash call; it must never block one.
        pass
