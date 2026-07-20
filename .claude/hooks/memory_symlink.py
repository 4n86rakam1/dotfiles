"""SessionStart hook: ensure <cwd>/.claude/memory exists as a symlink into the
harness project directory (~/.claude/projects/<cwd-slug>/memory), so persistent
memory colocates with the project without being stored inside the repo."""

import json
import os
import sys
import time
from pathlib import Path

LOG_PATH = Path.home() / ".claude" / "hooks-memory-symlink.log"
PROJECTS_ROOT = Path.home() / ".claude" / "projects"


def log(msg: str) -> None:
    try:
        LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        with LOG_PATH.open("a", encoding="utf-8") as f:
            ts = time.strftime("%Y-%m-%d %H:%M:%S")
            f.write(f"{ts} {msg}\n")
    except OSError:
        pass


def cwd_slug(cwd: str) -> str:
    return "".join("-" if c in "/." else c for c in cwd)


def ensure_symlink(cwd: str) -> None:
    project_root = Path(cwd)
    memory_link = project_root / ".claude" / "memory"
    if memory_link.exists() or memory_link.is_symlink():
        return
    harness_memory = PROJECTS_ROOT / cwd_slug(cwd) / "memory"
    try:
        harness_memory.mkdir(parents=True, exist_ok=True)
        memory_link.parent.mkdir(parents=True, exist_ok=True)
        os.symlink(harness_memory, memory_link)
    except OSError as exc:
        log(f"failed for {cwd}: {exc}")
        return
    log(f"created {memory_link} -> {harness_memory}")


def run_hook() -> None:
    try:
        event = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        return
    if event.get("source") != "startup":
        return
    cwd = event.get("cwd") or os.getcwd()
    if not cwd:
        return
    if ".claude/worktrees/" in cwd:
        return
    ensure_symlink(cwd)


if __name__ == "__main__":
    run_hook()
