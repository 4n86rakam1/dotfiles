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


def detect_write_method(command: str) -> str | None:
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
