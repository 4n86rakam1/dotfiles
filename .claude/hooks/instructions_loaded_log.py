"""InstructionsLoaded hook: append each instruction-file load to a JSONL log.

Transcripts are swept after cleanupPeriodDays, so this log is the durable record
of which CLAUDE.md files and .claude/rules/*.md entries actually reached context.
"""

import json
import os
import sys
from datetime import datetime, timezone

LOG_PATH = os.path.expanduser("~/.claude/logs/instructions-loaded.jsonl")
KEPT_FIELDS = (
    "session_id",
    "cwd",
    "permission_mode",
    "agent_id",
    "file_path",
    "memory_type",
    "load_reason",
    "globs",
    "trigger_file_path",
    "parent_file_path",
)


def main():
    event = json.load(sys.stdin)
    record = {"ts": datetime.now(timezone.utc).isoformat()}
    record.update({name: event[name] for name in KEPT_FIELDS if name in event})
    # Write owner-only: the log holds absolute paths from every project.
    os.makedirs(os.path.dirname(LOG_PATH), mode=0o700, exist_ok=True)
    descriptor = os.open(LOG_PATH, os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o600)
    with os.fdopen(descriptor, "a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, ensure_ascii=False) + "\n")


if __name__ == "__main__":
    try:
        main()
    except Exception:
        # A logging hook must never disturb the session it observes.
        pass
