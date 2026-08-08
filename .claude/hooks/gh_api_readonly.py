"""PreToolUse hook: block gh api write requests (POST/PATCH/PUT/DELETE)."""

import json
import re
import sys

# --method accepts space or = separator (--method POST / --method=POST).
# -X accepts no-space form (-XPOST), so \s* is used instead of \s+.
WRITE_METHOD_RE = re.compile(
    r"(?:--method[\s=]|-X\s*)(?P<method>POST|PATCH|PUT|DELETE)",
    re.IGNORECASE,
)


# Unquoted separators that end one command in a list/pipeline. Splitting on these
# keeps a downstream `awk -F,` or `git commit -F` from being read as gh's own flag.
SEPARATORS = "|&;\n<>"
GH_API_RE = re.compile(r"\bgh\s+api\b")


def split_unquoted(command: str) -> list[str]:
    """Split on shell separators outside quotes. Raises on unbalanced quotes."""
    segments: list[str] = []
    buf: list[str] = []
    quote: str | None = None
    escaped = False
    for char in command:
        if escaped:
            buf.append(char)
            escaped = False
        # Backslash is literal inside single quotes.
        elif char == "\\" and quote != "'":
            buf.append(char)
            escaped = True
        elif quote:
            if char == quote:
                quote = None
            buf.append(char)
        elif char in "'\"":
            quote = char
            buf.append(char)
        elif char in SEPARATORS:
            segments.append("".join(buf))
            buf = []
        else:
            buf.append(char)
    if quote:
        raise ValueError("unbalanced quote")
    segments.append("".join(buf))
    return segments


def detect_write_method(command: str) -> str | None:
    try:
        segments = split_unquoted(command)
    except ValueError:
        # Segmentation is unreliable, so fall back to scanning everything. This
        # over-denies, but never lets a write slip past.
        segments = [command]
    for segment in segments:
        if not GH_API_RE.search(segment):
            continue
        found = detect_in_segment(segment)
        if found:
            return found
    return None


def detect_in_segment(command: str) -> str | None:
    match = WRITE_METHOD_RE.search(command)
    if match:
        return match.group("method").upper()
    if re.search(r"--input\b", command, re.IGNORECASE):
        return "--input"
    # graphql subcommand always uses POST; block regardless of query vs mutation.
    if re.search(r"gh\s+api\s+graphql\b", command):
        return "graphql (POST)"
    # -f/--raw-field and -F/--field implicitly switch gh api to POST.
    # Both space-separated (-f key=val) and concatenated (-fkey=val) forms are matched.
    if re.search(r"(?:^|\s)(?:-f\S?|-F\S?|--raw-field[\s=]|--field[\s=])", command):
        return "-f/-F (implicit POST)"
    return None


def deny_response(reason: str) -> dict:
    return {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": reason,
        }
    }


def main() -> None:
    try:
        event = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        return

    if event.get("tool_name") != "Bash":
        return

    command = event.get("tool_input", {}).get("command", "")
    if "gh api" not in command:
        return

    write_method = detect_write_method(command)
    if write_method:
        print(
            json.dumps(
                deny_response(
                    f"gh api write request ({write_method}) is not allowed. "
                    "Only read-only (GET) requests are permitted."
                )
            )
        )


if __name__ == "__main__":
    main()
