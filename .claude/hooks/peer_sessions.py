"""SessionStart hook: list the other live Claude sessions bound to the same
repository, with what each is working on, so a starting session can coordinate
before duplicating or colliding with work already in flight.

Peers are read from `claude agents --json`; what they are doing comes from their
transcripts. The hook never blocks: SessionStart cannot veto a session, so this
is advisory context only.
"""

import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

LOG_PATH = Path.home() / ".claude" / "hooks-peer-sessions.log"
PROJECTS_ROOT = Path.home() / ".claude" / "projects"

ACTIVE_SOURCES = ("startup", "resume")
AGENTS_TIMEOUT_SEC = 5
WORKTREE_MARKER = "/.claude/worktrees/"
ANCESTRY_DEPTH = 8

# Transcripts grow to megabytes; only the tail can hold the current activity.
# The window has to be generous in bytes because single entries reach tens of
# kilobytes: across the transcripts on this machine the last human prompt sat up
# to 307 lines back, which a smaller byte window cut off well before that line.
# Parsing stays bounded regardless, since only the last lines are decoded.
TRANSCRIPT_TAIL_BYTES = 4 * 1024 * 1024
TRANSCRIPT_TAIL_LINES = 400
SUMMARY_MAX_CHARS = 100
MAX_EDITED_FILES = 3

EDIT_TOOLS = frozenset({"Edit", "Write", "NotebookEdit"})
META_PREFIXES = (
    "<task-notification>",
    "<system-reminder>",
    "<local-command-stdout>",
    "<command-stdout>",
    "<user-prompt-submit-hook>",
    # Left unclosed on purpose: this tag carries attributes, unlike the others.
    "<cross-session-message",
)
COMMAND_NAME_RE = re.compile(r"<command-name>([^<]*)</command-name>")
COMMAND_ARGS_RE = re.compile(r"<command-args>([^<]*)</command-args>")

ADVISORY = (
    "If any of these overlap with your task, ask that session via SendMessage "
    "before starting."
)


def log(msg: str) -> None:
    try:
        LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        with LOG_PATH.open("a", encoding="utf-8") as f:
            f.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')} {msg}\n")
    except OSError:
        pass


def repo_root(path: str) -> str:
    """Collapse a worktree path onto the repository that owns it, so sessions
    isolated by `worktree.bgIsolation` still group with their siblings."""
    marker = path.find(WORKTREE_MARKER)
    if marker != -1:
        path = path[:marker]
    return path.rstrip("/")


def self_ids(payload: dict) -> set[str]:
    """A resumed session can arrive with a freshly minted `session_id` while the
    registry still lists it under the id its transcript is named after, so match
    on both."""
    ids = {payload.get("session_id")}
    transcript = payload.get("transcript_path")
    if transcript:
        ids.add(Path(transcript).stem)
    return {i for i in ids if isinstance(i, str) and i}


def own_session_pid(sessions: list[dict]) -> int | None:
    """Identity that survives id re-minting: the session process that spawned
    this hook is one of its ancestors. Stop at the nearest match, because the
    daemon further up the chain is an ancestor of every background session."""
    known = {s.get("pid") for s in sessions if isinstance(s.get("pid"), int)}
    pid = os.getpid()
    for _ in range(ANCESTRY_DEPTH):
        if pid in known:
            return pid
        try:
            stat = Path(f"/proc/{pid}/stat").read_text()
        except OSError:
            return None
        try:
            ppid = int(stat[stat.rindex(")") + 2 :].split()[1])
        except (ValueError, IndexError):
            return None
        if ppid <= 1:
            return None
        pid = ppid
    return None


def list_sessions() -> list[dict]:
    proc = subprocess.run(
        ["claude", "agents", "--json"],
        capture_output=True,
        text=True,
        timeout=AGENTS_TIMEOUT_SEC,
        check=True,
    )
    sessions = json.loads(proc.stdout)
    if not isinstance(sessions, list):
        raise ValueError(f"expected a JSON array, got {type(sessions).__name__}")
    return [s for s in sessions if isinstance(s, dict)]


def find_transcript(session_id: str) -> Path | None:
    """Sessions that entered a worktree file their transcript under the worktree
    slug, so the project directory cannot be derived from the repository path."""
    return next(PROJECTS_ROOT.glob(f"*/{session_id}.jsonl"), None)


def tail_lines(path: Path) -> list[str]:
    with path.open("rb") as f:
        f.seek(0, 2)
        f.seek(max(0, f.tell() - TRANSCRIPT_TAIL_BYTES))
        raw = f.read()
    lines = raw.decode("utf-8", errors="replace").splitlines()
    return lines[-TRANSCRIPT_TAIL_LINES:]


def user_text(content: str) -> str | None:
    if content.startswith("<command-message>"):
        name = COMMAND_NAME_RE.search(content)
        if not name:
            return None
        args = COMMAND_ARGS_RE.search(content)
        return f"{name.group(1)} {args.group(1) if args else ''}".strip()
    if content.startswith(META_PREFIXES):
        return None
    return content.strip() or None


def within(path: str, root: str) -> bool:
    return path == root or path.startswith(root + "/")


def latest_edits(entries: list[dict], root: str) -> list[str]:
    """Walk backwards so a file edited repeatedly keeps its most recent position:
    that file is the likeliest to collide with the starting session's work.

    Only files under the repository count. Sessions also write scratch files to
    their job directory, and those can never collide with anything here."""
    edited: list[str] = []
    for entry in reversed(entries):
        content = (entry.get("message") or {}).get("content")
        if not isinstance(content, list):
            continue
        for block in reversed(content):
            if not isinstance(block, dict) or block.get("name") not in EDIT_TOOLS:
                continue
            file_path = (block.get("input") or {}).get("file_path")
            if not isinstance(file_path, str) or not within(file_path, root):
                continue
            if file_path not in edited:
                edited.append(file_path)
                if len(edited) == MAX_EDITED_FILES:
                    return list(reversed(edited))
    return list(reversed(edited))


def latest_prompt(entries: list[dict]) -> str | None:
    for entry in reversed(entries):
        if entry.get("type") != "user" or entry.get("isSidechain"):
            continue
        if entry.get("isMeta"):
            continue
        content = (entry.get("message") or {}).get("content")
        if not isinstance(content, str):
            continue
        text = user_text(content)
        if text:
            return text
    return None


def summarize(path: Path, root: str) -> tuple[str | None, list[str]]:
    entries = []
    for line in tail_lines(path):
        try:
            entries.append(json.loads(line))
        except ValueError:
            continue
    return latest_prompt(entries), latest_edits(entries, root)


def summarize_safely(session_id: str, root: str) -> tuple[str | None, list[str]]:
    transcript = find_transcript(session_id)
    if transcript is None:
        return None, []
    try:
        return summarize(transcript, root)
    except OSError as exc:
        log(f"transcript unreadable for {session_id}: {exc}")
        return None, []


def age(started_at_ms, now_ms: float) -> str | None:
    if not isinstance(started_at_ms, (int, float)) or started_at_ms <= 0:
        return None
    minutes = (now_ms - started_at_ms) / 60_000
    if minutes < 0:
        return None
    whole = int(minutes)
    if whole < 60:
        return f"{whole}m"
    return f"{whole // 60}h{whole % 60:02d}m"


def one_line(text: str) -> str:
    collapsed = " ".join(text.split())
    if len(collapsed) <= SUMMARY_MAX_CHARS:
        return collapsed
    return collapsed[:SUMMARY_MAX_CHARS] + "..."


def render(
    peers: list[dict],
    summaries: dict[str, tuple[str | None, list[str]]],
    now_ms: float,
) -> str:
    lines = [f"Other active sessions in this repo ({len(peers)}):"]
    for peer in peers:
        session_id = peer.get("sessionId") or ""
        short = peer.get("id") or session_id[:8]
        # Names are model-generated and unbounded; clamp them like transcript
        # text so one peer cannot break the layout for every later session.
        parts = [one_line(str(peer["name"]))] if peer.get("name") else []
        parts.append(one_line(str(peer.get("status") or "unknown")))
        elapsed = age(peer.get("startedAt"), now_ms)
        if elapsed:
            parts.append(elapsed)
        last, edited = summaries.get(session_id, (None, []))
        lines.append(f"- [{short}] " + " · ".join(parts))
        lines.append(f"  last: {one_line(last) if last else '(unknown)'}")
        names = [Path(p).name for p in edited]
        lines.append(f"  edits: {', '.join(names) if names else '(none)'}")
    lines.append(ADVISORY)
    return "\n".join(lines)


def main() -> None:
    payload = json.load(sys.stdin)
    if payload.get("source") not in ACTIVE_SOURCES:
        return

    own_repo = repo_root(payload.get("cwd") or "")
    if not own_repo:
        return

    sessions = list_sessions()
    own_ids = self_ids(payload)
    own_pid = own_session_pid(sessions)
    peers = [
        s
        for s in sessions
        if s.get("sessionId") not in own_ids
        and (own_pid is None or s.get("pid") != own_pid)
        and repo_root(s.get("cwd") or "") == own_repo
    ]
    if not peers:
        return
    peers.sort(key=lambda s: s.get("startedAt") or 0)

    summaries = {
        s.get("sessionId") or "": summarize_safely(s.get("sessionId") or "", own_repo)
        for s in peers
    }
    context = render(peers, summaries, time.time() * 1000)
    print(
        json.dumps(
            {
                "hookSpecificOutput": {
                    "hookEventName": "SessionStart",
                    "additionalContext": context,
                }
            }
        )
    )


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:  # a broken hook must never block a session start
        log(f"skipped: {type(exc).__name__}: {exc}")
