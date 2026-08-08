"""PreToolUse hook: block gh api write requests (POST/PATCH/PUT/DELETE)."""

import json
import re
import shlex
import sys

# Unquoted separators that end one command in a list/pipeline. Splitting on these
# keeps a downstream `awk -F,` or `git commit -F` from being read as gh's own flag.
# The command-substitution delimiters are here too: a gh call nested inside one is
# its own command, and the flags of the command wrapping it are not gh's.
SEPARATORS = "|&;\n<>()`"

WRITE_METHODS = frozenset({"POST", "PATCH", "PUT", "DELETE"})
METHOD_FLAGS = ("-X", "--method")
FIELD_FLAGS = frozenset({"-f", "-F", "--raw-field", "--field"})
FIELD_PREFIXES = ("--raw-field=", "--field=")

# Fallback patterns, used only when the segment cannot be tokenized. They match
# the raw text, so they have to tolerate the quotes a shell would have removed.
# A shell line continuation can also sit between words, where a backslash
# separates them just as whitespace does.
WORD_GAP = r"(?:\s|\\\r?\n)+"
GH_API_RE = re.compile(rf"\bgh{WORD_GAP}api\b")
GRAPHQL_RE = re.compile(rf"\bgh{WORD_GAP}api{WORD_GAP}graphql\b")
WRITE_METHOD_RE = re.compile(
    r"""(?:--method|-X)[\s=]*["']?(?P<method>POST|PATCH|PUT|DELETE)""",
    re.IGNORECASE,
)
FIELD_RE = re.compile(r"(?:^|\s)(?:-f\S?|-F\S?|--raw-field[\s=]|--field[\s=])")
INPUT_RE = re.compile(r"--input\b", re.IGNORECASE)


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


def invokes_gh_api(tokens: list[str]) -> bool:
    """True when the tokens run gh's api subcommand, rather than merely name it.

    Adjacency is what distinguishes the two: a quoted "gh api" mentioned inside
    a commit message survives tokenization as a single token, so it never lines
    up as two.
    """
    return any(
        token == "gh" and tokens[index + 1] == "api"
        for index, token in enumerate(tokens[:-1])
    )


def flag_value(tokens: list[str], index: int, flag: str) -> str | None:
    """Value of a flag spelled `--flag value`, `--flag=value`, or `-Xvalue`."""
    token = tokens[index]
    if token == flag:
        return tokens[index + 1] if index + 1 < len(tokens) else None
    if token.startswith(f"{flag}="):
        return token[len(flag) + 1 :]
    if not flag.startswith("--") and token.startswith(flag):
        return token[len(flag) :]
    return None


def is_write_method(value: str) -> bool:
    # shlex strips the quotes of $'POST' but leaves the dollar sign, which the
    # shell itself would have consumed. A value that is a variable reference
    # lands here too, and denying one is the safe direction.
    return value.lstrip("$").upper() in WRITE_METHODS


def is_field_flag(token: str) -> bool:
    if token in FIELD_FLAGS or token.startswith(FIELD_PREFIXES):
        return True
    # -fkey=val and -Fkey=val, but never a long flag that merely starts with -f.
    return token.startswith(("-f", "-F")) and not token.startswith("--")


def detect_in_tokens(tokens: list[str]) -> str | None:
    for index, token in enumerate(tokens):
        for flag in METHOD_FLAGS:
            value = flag_value(tokens, index, flag)
            if value and is_write_method(value):
                return value.lstrip("$").upper()
        if token == "--input" or token.startswith("--input="):
            return "--input"

    # graphql always POSTs; block it whether the document queries or mutates.
    if any(
        tokens[index : index + 3] == ["gh", "api", "graphql"]
        for index in range(len(tokens))
    ):
        return "graphql (POST)"

    # -f/--raw-field and -F/--field implicitly switch gh api to POST.
    if any(is_field_flag(token) for token in tokens):
        return "-f/-F (implicit POST)"
    return None


def detect_in_text(text: str) -> str | None:
    """Pattern fallback for text the tokenizer rejected."""
    if not GH_API_RE.search(text):
        return None
    match = WRITE_METHOD_RE.search(text)
    if match:
        return match.group("method").upper()
    if INPUT_RE.search(text):
        return "--input"
    if GRAPHQL_RE.search(text):
        return "graphql (POST)"
    if FIELD_RE.search(text):
        return "-f/-F (implicit POST)"
    return None


def tokenize(segment: str) -> list[str]:
    """Tokens of one segment.

    A line continuation survives shlex as a token holding only the newline, so
    whitespace-only tokens are dropped: they would otherwise break the adjacency
    of `gh` and `api` and the pairing of a flag with its value.
    """
    return [token for token in shlex.split(segment, comments=True) if token.strip()]


def detect_write_method(command: str) -> str | None:
    try:
        segments = split_unquoted(command)
        tokenized = [tokenize(segment) for segment in segments]
    except ValueError:
        # Splitting is unreliable, so fall back to scanning everything. This
        # over-denies, but never lets a write slip past.
        return detect_in_text(command)

    for tokens in tokenized:
        if not invokes_gh_api(tokens):
            continue
        found = detect_in_tokens(tokens)
        if found:
            return found
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

    if not isinstance(event, dict) or event.get("tool_name") != "Bash":
        return

    command = (event.get("tool_input") or {}).get("command")
    if not isinstance(command, str):
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
