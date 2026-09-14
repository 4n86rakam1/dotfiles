"""PostToolUse hook: format the file just edited via the tool implied by its
extension, and lint it when the language has a linter instead of a formatter.
Markdown gets both, because prettier settles none of the style rules the
findings and reports in these repositories are held to. Silently skips when the
tool is not installed or the file has no configured tool. This module is the
source of truth for which tool maps to which file type.

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


MARKDOWNLINT_CONFIG = Path.home() / ".markdownlint.yaml"
FENCE_RE = re.compile(r"^\s*(?:`{3,}|~{3,})")
INLINE_CODE_RE = re.compile(r"`[^`]*`")
FULLWIDTH_PAREN_RE = re.compile(r"[（）]")
# Punctuation is deliberately out of the class: `、A` is correct, `のA` is not.
JAPANESE = r"ぁ-んァ-ヶー一-龥々〆"
JA_ASCII_RE = re.compile(rf"[{JAPANESE}][0-9A-Za-z]|[0-9A-Za-z][{JAPANESE}]")
PUNCT_SPACE_RE = re.compile(r"[、。・][ 　]")
BOLD_RE = re.compile(r"\*\*[^*\n]+\*\*")
# The style rule keeps emphasis for the rare line a reader must not miss, so a
# couple per file is fine and a fourth means it has become decoration.
BOLD_LIMIT = 3


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


def report(message: str) -> None:
    """Hand findings back as context rather than rewriting the file, for the
    checks that report instead of fixing."""
    print(
        json.dumps(
            {
                "hookSpecificOutput": {
                    "hookEventName": "PostToolUse",
                    "additionalContext": message,
                }
            }
        )
    )


def prose_lines(text: str) -> list[tuple[int, str]]:
    """Lines that carry prose: fenced blocks and code spans are markup the
    style rules do not govern."""
    lines: list[tuple[int, str]] = []
    in_fence = False
    for lineno, line in enumerate(text.splitlines(), start=1):
        if FENCE_RE.match(line):
            in_fence = not in_fence
            continue
        if not in_fence:
            # A code span stands in as one ASCII letter rather than vanishing:
            # deleting it would fabricate adjacencies that are not in the text,
            # and the spacing rule treats a code span as ASCII anyway.
            lines.append((lineno, INLINE_CODE_RE.sub("X", line)))
    return lines


def check_markdown_style(path: Path) -> list[str]:
    """The parts of the markdown rule that markdownlint cannot express."""
    try:
        text = path.read_text()
    except OSError:
        return []

    findings: list[str] = []
    bold = 0
    for lineno, line in prose_lines(text):
        bold += len(BOLD_RE.findall(line))
        if FULLWIDTH_PAREN_RE.search(line):
            findings.append(f"{path}:{lineno}: full-width parentheses; use ()")
        if JA_ASCII_RE.search(line):
            findings.append(
                f"{path}:{lineno}: missing space between Japanese and ASCII"
            )
        if PUNCT_SPACE_RE.search(line):
            findings.append(f"{path}:{lineno}: space after 、。・; remove it")
    if bold >= BOLD_LIMIT:
        findings.append(
            f"{path}: {bold} bold spans; emphasis is for the rare line a reader "
            f"must not miss, so keep at most {BOLD_LIMIT - 1}"
        )
    return findings


def lint_markdown(path: Path) -> None:
    findings = check_markdown_style(path)

    if shutil.which("markdownlint"):
        argv = ["markdownlint", str(path)]
        if MARKDOWNLINT_CONFIG.exists():
            argv[1:1] = ["--config", str(MARKDOWNLINT_CONFIG)]
        try:
            result = subprocess.run(
                argv,
                capture_output=True,
                text=True,
                timeout=TIMEOUT_SEC,
                check=False,
            )
        except (subprocess.TimeoutExpired, OSError):
            result = None
        # markdownlint writes findings to stderr and exits non-zero; an empty
        # stderr with a non-zero exit means it failed to run at all.
        if result is not None and result.returncode != 0 and result.stderr.strip():
            findings.extend(result.stderr.strip().splitlines())

    if findings:
        report("markdown style issues:\n" + "\n".join(findings))


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
    report(f"shellcheck reported issues in {path}:\n{result.stdout}")


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

    # Formatting a .md file settles none of the style rules, so lint it after
    # prettier has had its pass.
    if path.suffix.lower() == ".md":
        lint_markdown(path)


if __name__ == "__main__":
    run_hook()
