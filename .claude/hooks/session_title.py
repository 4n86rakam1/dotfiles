"""SessionEnd hook: prefix the /resume title with the git branch and append a
compact stat suffix (duration / turns / files / commits) so past sessions are
easier to distinguish."""

import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

LOG_PATH = Path.home() / ".claude" / "hooks-session-title.log"
DEBUG_LOG_PATH = Path.home() / ".claude" / "hooks-session-title-debug.log"
MAX_TITLE_CHARS = 100
BRANCH_SKIP = {"master", "main"}
RUN_REASONS = {"prompt_input_exit", "clear", "resume", "other"}
LEADING_TAG = re.compile(r"^\[[^\]]+\]\s+")
TRAILING_STATS = re.compile(r"\s*\(\d+[hm]/\d+t/\d+f/\d+c\)\s*$")


def log_failure(reason: str) -> None:
    try:
        LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        with LOG_PATH.open("a", encoding="utf-8") as f:
            ts = time.strftime("%Y-%m-%d %H:%M:%S")
            f.write(f"{ts} {reason}\n")
    except OSError:
        pass


def log_event(event: dict) -> None:
    try:
        DEBUG_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        with DEBUG_LOG_PATH.open("a", encoding="utf-8") as f:
            ts = time.strftime("%Y-%m-%d %H:%M:%S")
            payload = {
                "reason": event.get("reason"),
                "session_id": event.get("session_id"),
                "cwd": event.get("cwd"),
            }
            f.write(f"{ts} {json.dumps(payload, ensure_ascii=False)}\n")
    except OSError:
        pass


def read_transcript(path: Path) -> list[dict]:
    entries: list[dict] = []
    try:
        with path.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    entries.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
    except OSError:
        pass
    return entries


def last_ai_title(entries: list[dict]) -> str:
    for e in reversed(entries):
        if e.get("type") == "ai-title":
            return str(e.get("aiTitle") or "").strip()
    return ""


def entry_epoch(entry: dict) -> float | None:
    ts = entry.get("timestamp")
    if not isinstance(ts, str):
        return None
    ts = ts.replace("Z", "+00:00")
    try:
        from datetime import datetime

        return datetime.fromisoformat(ts).timestamp()
    except ValueError:
        return None


def duration_str(entries: list[dict]) -> str:
    first = last = None
    for e in entries:
        t = entry_epoch(e)
        if t is None:
            continue
        if first is None:
            first = t
        last = t
    if first is None or last is None or last <= first:
        return ""
    minutes = int((last - first) // 60)
    if minutes < 60:
        return f"{max(minutes, 1)}m"
    hours = minutes // 60
    return f"{hours}h"


def count_user_turns(entries: list[dict]) -> int:
    count = 0
    for e in entries:
        if e.get("type") != "user":
            continue
        msg = e.get("message") or {}
        content = msg.get("content")
        text = ""
        if isinstance(content, str):
            text = content
        elif isinstance(content, list):
            for c in content:
                if isinstance(c, dict) and c.get("type") == "text":
                    text += str(c.get("text", ""))
        text = text.strip()
        if not text or text.startswith("<") or text.startswith("["):
            continue
        count += 1
    return count


def count_edited_files(entries: list[dict]) -> int:
    seen: set[str] = set()
    for e in entries:
        if e.get("type") != "assistant":
            continue
        content = (e.get("message") or {}).get("content") or []
        if not isinstance(content, list):
            continue
        for c in content:
            if not isinstance(c, dict) or c.get("type") != "tool_use":
                continue
            if c.get("name") not in {"Edit", "Write", "NotebookEdit"}:
                continue
            fp = (c.get("input") or {}).get("file_path")
            if fp:
                seen.add(fp)
    return len(seen)


def git_branch(cwd: str) -> str:
    try:
        result = subprocess.run(
            ["git", "-C", cwd, "branch", "--show-current"],
            capture_output=True,
            text=True,
            timeout=3,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        return ""
    if result.returncode != 0:
        return ""
    return result.stdout.strip()


def count_commits_since(cwd: str, entries: list[dict]) -> int:
    first_ts = None
    for e in entries:
        t = entry_epoch(e)
        if t is not None:
            first_ts = t
            break
    if first_ts is None:
        return 0
    try:
        result = subprocess.run(
            [
                "git",
                "-C",
                cwd,
                "log",
                f"--since={int(first_ts)}",
                "--pretty=%H",
            ],
            capture_output=True,
            text=True,
            timeout=3,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        return 0
    if result.returncode != 0:
        return 0
    return sum(1 for line in result.stdout.splitlines() if line.strip())


def build_title(
    base: str, branch: str, dur: str, turns: int, files: int, commits: int
) -> str:
    core = LEADING_TAG.sub("", TRAILING_STATS.sub("", base)).strip()
    if not core:
        return ""
    prefix = f"[{branch}] " if branch and branch not in BRANCH_SKIP else ""
    dur = dur or "0m"
    suffix = f" ({dur}/{turns}t/{files}f/{commits}c)"
    title = f"{prefix}{core}{suffix}"
    return title[:MAX_TITLE_CHARS]


def append_ai_title(transcript: Path, session_id: str, title: str) -> None:
    record = {"type": "ai-title", "aiTitle": title, "sessionId": session_id}
    with transcript.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")


def run_hook() -> None:
    try:
        event = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        return
    log_event(event)
    if event.get("reason") not in RUN_REASONS:
        return
    session_id = event.get("session_id")
    transcript_path = event.get("transcript_path")
    cwd = event.get("cwd") or os.getcwd()
    if not session_id or not transcript_path:
        return
    transcript = Path(transcript_path)
    if not transcript.exists():
        return
    entries = read_transcript(transcript)
    base = last_ai_title(entries)
    if not base:
        return
    branch = git_branch(cwd)
    dur = duration_str(entries)
    turns = count_user_turns(entries)
    files = count_edited_files(entries)
    commits = count_commits_since(cwd, entries)
    title = build_title(base, branch, dur, turns, files, commits)
    if not title or title == base:
        return
    try:
        append_ai_title(transcript, session_id, title)
    except OSError as exc:
        log_failure(f"append failed: {exc}")


if __name__ == "__main__":
    run_hook()
