"""Count file operations done through dedicated tools vs their Bash equivalents."""

import argparse
import json
import os
import re
import shlex
import sys
from collections import Counter, defaultdict
from pathlib import PurePosixPath

TRANSCRIPT_ROOT = os.path.expanduser("~/.claude/projects")
LOG_DIR = os.path.expanduser("~/.claude/logs")
INSTRUCTIONS_LOG = os.path.join(LOG_DIR, "instructions-loaded.jsonl")
BASH_ACCESS_LOG = os.path.join(LOG_DIR, "bash-file-access.jsonl")
USER_RULES_DIR = "~/.claude/rules"
DEFAULT_RULE_DIRS = (USER_RULES_DIR, ".claude/rules")
FRONTMATTER_DELIMITER = "---"

READ = "read"
SEARCH = "search"
EDIT = "edit"
FAMILIES = (READ, SEARCH, EDIT)

NATIVE_TOOLS = {
    "Read": READ,
    "NotebookRead": READ,
    "Grep": SEARCH,
    "Glob": SEARCH,
    "Edit": EDIT,
    "Write": EDIT,
    "MultiEdit": EDIT,
    "NotebookEdit": EDIT,
}

BASH_READ = {"cat", "head", "tail", "nl", "less", "more", "bat", "zcat"}
BASH_SEARCH = {"grep", "egrep", "fgrep", "rg", "ag", "ack"}
# These default to the working directory, so they touch the filesystem even
# without an operand.
BASH_LIST = {"ls", "find", "fd", "tree"}
BASH_EDIT = {"tee", "truncate"}
# The first operand is a pattern or script, not a path.
BASH_PATTERN_FIRST = {"grep", "egrep", "fgrep", "rg", "ag", "ack", "sed", "awk"}
# Interpreters can do any of the three; the command line alone does not say
# which, so they are reported separately instead of folded into a family.
BASH_SCRIPT = {"python", "python3", "node", "perl", "ruby", "deno", "bun"}
# Everything after these runs on another machine, so it is not this session's
# file access.
BASH_REMOTE = {"ssh", "scp", "rsync", "docker", "kubectl"}

# Wrappers that delegate to the command after them, with the flags that take a
# value and the count of positional arguments to step over first. `timeout 30 cat`
# would otherwise be read as a command named "30".
BASH_PREFIXES = {
    "sudo": ({"-u", "-g", "-p", "-C", "-D", "-h", "-r", "-t", "-U"}, 0),
    "doas": ({"-u", "-C"}, 0),
    "env": (set(), 0),
    "command": (set(), 0),
    "builtin": (set(), 0),
    "exec": (set(), 0),
    "nohup": (set(), 0),
    "nice": ({"-n", "--adjustment"}, 0),
    "ionice": ({"-c", "-n", "-p"}, 0),
    "time": (set(), 0),
    "timeout": ({"-s", "-k", "--signal", "--kill-after"}, 1),
    "stdbuf": ({"-i", "-o", "-e"}, 0),
    "xargs": ({"-n", "-P", "-I", "-d", "-s", "-a", "-E", "-L"}, 0),
}
# Short flags that consume the token after them as their value.
# Which short flags consume the next token differs per command: -n is a count
# for head but a boolean for sed, and -f is a file for grep but a boolean for tail.
GREP_VALUE_FLAGS = {"-e", "-f", "-m", "-A", "-B", "-C", "--regexp", "--file"}
VALUE_FLAGS_BY_COMMAND = {
    "head": {"-n", "-c"},
    "tail": {"-n", "-c"},
    "grep": GREP_VALUE_FLAGS,
    "egrep": GREP_VALUE_FLAGS,
    "fgrep": GREP_VALUE_FLAGS,
    "rg": GREP_VALUE_FLAGS | {"-g", "--glob"},
    "ag": GREP_VALUE_FLAGS,
    "ack": GREP_VALUE_FLAGS,
    "sed": {"-e", "-f"},
    "awk": {"-f", "-v"},
    "perl": {"-e"},
}
PATTERN_FLAGS = {"-e", "-f", "--regexp", "--file"}
RECURSIVE_FLAGS = {"-r", "-R", "--recursive", "-rn", "-rl", "-ri", "-nr"}
# `find [path...] [expression]`: only the operands before the first flag are
# paths. Everything after belongs to -name, -exec and friends.
PATHS_BEFORE_FLAGS = {"find", "fd"}

SEPARATORS = {";", "&&", "||", "&", ";;"}
PIPES = {"|", "|&"}
WRITE_REDIRECTS = {">", ">>", ">|", "&>", "&>>"}
# These consume the token after them without it naming a file to write: `2>&1`
# duplicates a descriptor and `< in` is an input.
OTHER_REDIRECTS = {"<", "<<<", ">&", "<&", "&>&"}

HEREDOC_START = re.compile(r"<<-?\s*(['\"]?)([A-Za-z_][A-Za-z0-9_]*)\1")
ENV_ASSIGNMENT = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=")
FILE_DESCRIPTOR = re.compile(r"^[0-9]$")
# A redirect into scratch space is not an edit to the user's files.
SCRATCH_PATH = re.compile(r"^/dev/|(^|/)tmp/|^/proc/|^/sys/")
# Operands that cannot be a concrete path: glob patterns, `find -exec` syntax,
# and anything still holding a shell expansion.
NON_PATH_OPERAND = re.compile(r"[*?\[\]{}$`!]|^[-+;]$")
PATH_EXTENSION = re.compile(r"\.[A-Za-z0-9]{1,10}$")

STEER_LABELS = {True: "steer", False: "auto-no-steer", None: "no-auto"}


def strip_heredocs(command):
    """Drop heredoc bodies, and the `<<DELIM` that introduces them.

    The introducer has to go too: left in place it tokenizes into operands, so
    `cat > out.md <<'EOF'` would otherwise read as a read of a file named EOF.
    """
    lines = command.split("\n")
    kept = []
    index = 0
    while index < len(lines):
        line = lines[index]
        delimiters = [match.group(2) for match in HEREDOC_START.finditer(line)]
        kept.append(HEREDOC_START.sub(" ", line))
        index += 1
        for delimiter in delimiters:
            while index < len(lines) and lines[index].strip() != delimiter:
                index += 1
            index += 1
    return "\n".join(kept)


def mark_line_breaks(command):
    """Turn unquoted newlines into `;` so each line is its own command.

    shlex treats a newline as plain whitespace, which fuses every line of a
    multi-line command into one segment. Quoted newlines are left alone: they
    belong to a single argument, such as a remote script passed to ssh.
    """
    out = []
    quote = None
    escaped = False
    for char in command:
        if escaped:
            # A backslash before a newline continues the line rather than ending it.
            out.append(" " if char == "\n" else char)
            escaped = False
            continue
        if char == "\\" and quote != "'":
            out.append(char)
            escaped = True
        elif quote:
            out.append(char)
            if char == quote:
                quote = None
        elif char in "'\"":
            quote = char
            out.append(char)
        elif char == "\n":
            out.append(";")
        else:
            out.append(char)
    return "".join(out)


def tokenize(command):
    """Split into shell tokens, keeping operators as tokens of their own."""
    lexer = shlex.shlex(mark_line_breaks(command), posix=True, punctuation_chars=True)
    lexer.whitespace_split = True
    # A shell only starts a comment at a word boundary, so `foo#1.md` is a path.
    lexer.commenters = ""
    try:
        return list(lexer), True
    except ValueError:
        return [], False


def split_pipelines(tokens):
    """Group tokens into pipelines of segments, collecting written-to paths."""
    pipelines = [[[]]]
    targets = []
    expect = None
    for token in tokens:
        if expect is not None:
            if expect == "write":
                targets.append(token)
            expect = None
            continue
        if token in WRITE_REDIRECTS or token in OTHER_REDIRECTS:
            # `2>file` lexes as `2` then `>`; the descriptor is not an operand.
            segment = pipelines[-1][-1]
            if segment and FILE_DESCRIPTOR.match(segment[-1]):
                segment.pop()
            expect = "write" if token in WRITE_REDIRECTS else "skip"
        elif token in SEPARATORS:
            pipelines.append([[]])
        elif token in PIPES:
            pipelines[-1].append([])
        else:
            pipelines[-1][-1].append(token)
    return pipelines, targets


def head_command(tokens):
    """Return the command name and its arguments, skipping env vars and wrappers."""
    position = 0
    while position < len(tokens):
        token = tokens[position]
        if ENV_ASSIGNMENT.match(token):
            position += 1
            continue
        name = os.path.basename(token)
        wrapper = BASH_PREFIXES.get(name)
        if wrapper is not None:
            value_flags, positional = wrapper
            position += 1
            while position < len(tokens) and tokens[position].startswith("-"):
                takes_value = tokens[position] in value_flags
                position += 1
                if takes_value:
                    position += 1
            position += positional
            continue
        return name, tokens[position + 1 :]
    return None, []


def split_arguments(name, args):
    """Return (flags, operands) with flag values and the leading pattern removed."""
    flags = []
    operands = []
    pattern_given = False
    value_flags = VALUE_FLAGS_BY_COMMAND.get(name, frozenset())
    index = 0
    while index < len(args):
        token = args[index]
        if token.startswith("-") and token != "-":
            flags.append(token)
            if token in value_flags and index + 1 < len(args):
                if token in PATTERN_FLAGS:
                    pattern_given = True
                index += 1
            index += 1
            continue
        operands.append(token)
        index += 1
    if name in BASH_PATTERN_FIRST and not pattern_given and operands:
        operands = operands[1:]
    if name in PATHS_BEFORE_FLAGS:
        operands = operands[: leading_operand_count(args)]
    return flags, operands


def leading_operand_count(args):
    """Count the operands before the first flag, which is where find's paths end."""
    count = 0
    for token in args:
        if token.startswith("-") and token != "-":
            break
        count += 1
    return count


def classify_segment(tokens, is_downstream):
    """Return (families, kind, operands) for one segment of a pipeline."""
    if not tokens:
        return set(), "empty", []
    name, args = head_command(tokens)
    if name is None:
        return set(), "empty", []
    if name in BASH_REMOTE:
        return set(), "remote", []
    if name in BASH_SCRIPT:
        return set(), "script", []

    flags, operands = split_arguments(name, args)
    # A stage fed by a pipe with no path of its own is filtering the previous
    # command's output, not touching a file.
    touches_file = bool(operands) or (not is_downstream and name in BASH_LIST)
    settled = "classified" if touches_file else "filter"

    if name in ("sed", "awk", "perl"):
        if not touches_file:
            return set(), "filter", []
        inplace = any(flag.startswith("-i") for flag in flags)
        return {EDIT} if inplace else {READ}, "classified", operands
    if name in BASH_READ:
        return ({READ} if touches_file else set()), settled, operands
    if name in BASH_SEARCH:
        recursive = any(flag in RECURSIVE_FLAGS for flag in flags)
        if touches_file or (recursive and not is_downstream):
            return {SEARCH}, "classified", operands
        return set(), "filter", []
    if name in BASH_LIST:
        return ({SEARCH} if touches_file else set()), settled, operands
    if name in BASH_EDIT:
        return ({EDIT} if touches_file else set()), settled, operands
    return set(), "other", []


def analyze_bash(command):
    """Return (operations, kinds). One operation is (family, paths) for a segment."""
    operations = []
    kinds = Counter()
    tokens, parsed = tokenize(strip_heredocs(command))
    if not parsed:
        kinds["unparsed"] += 1
        return operations, kinds

    pipelines, redirects = split_pipelines(tokens)
    for pipeline in pipelines:
        for position, segment in enumerate(pipeline):
            families, kind, operands = classify_segment(segment, position > 0)
            kinds[kind] += 1
            for family in families:
                operations.append((family, operands))
    for target in redirects:
        if not SCRATCH_PATH.search(target):
            operations.append((EDIT, [target]))
            kinds["classified"] += 1
    return operations, kinds


def classify_bash(command):
    """Count one operation per family per segment, matching the report's units."""
    operations, kinds = analyze_bash(command)
    return Counter(family for family, _ in operations), kinds


def looks_like_path(operand):
    """Screen out operands that are not concrete paths.

    Flag tables cover the commands this tool models, but not every command, so an
    operand can be a pattern, a nested command, or a secret passed as an argument.
    Anything logged is written to disk, so the doubtful cases are dropped.
    """
    if not operand or NON_PATH_OPERAND.search(operand):
        return False
    return "/" in operand or PATH_EXTENSION.search(operand) is not None


def bash_file_targets(command):
    """Return (family, path) pairs for the files a command reads, searches or writes."""
    operations, _ = analyze_bash(command)
    return [
        (family, path)
        for family, paths in operations
        for path in paths
        if looks_like_path(path)
    ]


def session_records(path):
    with open(path, encoding="utf-8", errors="replace") as handle:
        for line in handle:
            if '"type"' not in line:
                continue
            try:
                yield json.loads(line)
            except ValueError:
                continue


def scan_session(path, include_subagent):
    start_model = None
    bash_first = None
    first_timestamp = None
    native = Counter()
    bash = Counter()
    kinds = Counter()

    for record in session_records(path):
        if first_timestamp is None and record.get("timestamp"):
            first_timestamp = record["timestamp"][:10]

        attachment = record.get("attachment") or {}
        if attachment.get("type") == "auto_mode":
            bash_first = bool(attachment.get("bashFirst")) or bool(bash_first)

        if record.get("type") != "assistant":
            continue
        sidechain = bool(record.get("isSidechain"))
        if sidechain and not include_subagent:
            continue

        message = record.get("message") or {}
        model = message.get("model")
        if start_model is None and model and model != "<synthetic>" and not sidechain:
            start_model = model

        content = message.get("content")
        if not isinstance(content, list):
            continue
        for block in content:
            if not isinstance(block, dict) or block.get("type") != "tool_use":
                continue
            tool = block.get("name")
            if tool in NATIVE_TOOLS:
                native[NATIVE_TOOLS[tool]] += 1
            elif tool == "Bash":
                command = (block.get("input") or {}).get("command") or ""
                found, seen = classify_bash(command)
                bash.update(found)
                kinds.update(seen)

    return {
        "path": path,
        "date": first_timestamp,
        "model": start_model or "(unknown)",
        "steer": STEER_LABELS[bash_first],
        "native": native,
        "bash": bash,
        "kinds": kinds,
    }


def collect(args):
    sessions = []
    for directory, _, files in os.walk(TRANSCRIPT_ROOT):
        for name in files:
            if not name.endswith(".jsonl"):
                continue
            if name[: -len(".jsonl")] in args.exclude_session:
                continue
            if args.project and args.project not in directory:
                continue
            path = os.path.join(directory, name)
            try:
                session = scan_session(path, args.include_subagent)
            except OSError as error:
                print(f"skipped {path}: {error}", file=sys.stderr)
                continue
            if args.since and (session["date"] or "") < args.since:
                continue
            if args.model and args.model not in session["model"]:
                continue
            if sum(session["native"].values()) + sum(session["bash"].values()) == 0:
                continue
            sessions.append(session)
    return sessions


def rate(bash_count, native_count):
    total = bash_count + native_count
    return f"{100 * bash_count / total:5.1f}%" if total else "    - "


def report(sessions):
    groups = defaultdict(lambda: {"native": Counter(), "bash": Counter(), "n": 0})
    kinds = Counter()
    native_totals = Counter()
    for session in sessions:
        key = (session["model"], session["steer"])
        groups[key]["native"].update(session["native"])
        groups[key]["bash"].update(session["bash"])
        groups[key]["n"] += 1
        kinds.update(session["kinds"])
        native_totals.update(session["native"])

    header = f"{'model':26}{'steer':16}{'sess':>5}"
    for family in FAMILIES:
        header += f"{family:>10}{'native':>8}{'bash':>7}{'bash率':>9}"
    print(header)
    for key in sorted(groups):
        model, steer = key
        data = groups[key]
        row = f"{model:26}{steer:16}{data['n']:>5}"
        for family in FAMILIES:
            native_count = data["native"][family]
            bash_count = data["bash"][family]
            row += f"{'':>10}{native_count:>8}{bash_count:>7}{rate(bash_count, native_count):>9}"
        print(row)

    for family in FAMILIES:
        if native_totals[family] == 0:
            print(
                f"\n注意: {family} 系統の専用ツールは 0 件。この環境に未提供なら bash率は無意味。"
            )

    total = sum(kinds.values())
    print("\nBash セグメントの分類カバレッジ:")
    for kind, count in kinds.most_common():
        share = f"{100 * count / total:.1f}%" if total else "-"
        print(f"  {kind:12}{count:>8}  {share:>7}")


def rule_globs(path):
    """Read the `paths:` frontmatter list from a rule file, if it has one."""
    globs = []
    with open(path, encoding="utf-8", errors="replace") as handle:
        if handle.readline().strip() != FRONTMATTER_DELIMITER:
            return globs
        in_paths = False
        for line in handle:
            stripped = line.strip()
            if stripped == FRONTMATTER_DELIMITER:
                break
            if stripped.startswith("paths:"):
                in_paths = True
            elif in_paths and stripped.startswith("- "):
                globs.append(stripped[2:].strip().strip("\"'"))
            elif in_paths and stripped:
                in_paths = False
    return globs


def discover_rules(directories):
    """Map each path-scoped rule to (globs, project root), keyed by real path.

    The root is None for a user-level rule, which applies in every project. A
    project rule only applies to sessions run inside its own tree, so its misses
    must not be counted from unrelated sessions.
    """
    rules = {}
    user_root = os.path.realpath(os.path.expanduser(USER_RULES_DIR))
    seen_dirs = set()
    for directory in directories:
        base = os.path.realpath(os.path.expanduser(directory))
        # A symlinked ~/.claude/rules and the checkout it points at are one place.
        if base in seen_dirs:
            continue
        seen_dirs.add(base)
        root = None if base == user_root else os.path.dirname(os.path.dirname(base))
        for dirpath, _, files in os.walk(base):
            for name in sorted(files):
                if not name.endswith(".md"):
                    continue
                path = os.path.join(dirpath, name)
                globs = rule_globs(path)
                if globs:
                    rules[os.path.realpath(path)] = (globs, root)
    return rules


def read_jsonl(path):
    try:
        handle = open(path, encoding="utf-8", errors="replace")
    except OSError:
        return
    with handle:
        for line in handle:
            try:
                yield json.loads(line)
            except ValueError:
                continue


def within(path, root):
    if not path:
        return False
    relative = os.path.relpath(os.path.realpath(path), root)
    return relative == "." or not relative.startswith("..")


def glob_matches(globs, path, cwd):
    """Match the way Claude Code does: against the path relative to the project."""
    if not cwd:
        return False
    try:
        relative = os.path.relpath(path, cwd)
    except ValueError:
        return False
    if relative.startswith(".."):
        return False
    candidate = PurePosixPath(relative)
    return any(candidate.full_match(glob.lstrip("/")) for glob in globs)


def shorten_path(path, width):
    """Keep the tail, which is what distinguishes two rules with the same name."""
    home = os.path.expanduser("~")
    display = "~/" + os.path.relpath(path, home) if path.startswith(home) else path
    return display if len(display) <= width else "…" + display[-(width - 1) :]


def report_rules(directories, since=None):
    rules = discover_rules(directories)
    if not rules:
        print("paths: frontmatter を持つ rule が見つからない", file=sys.stderr)
        return 1

    def in_window(record):
        return not since or (record.get("ts") or "")[:10] >= since

    loaded = defaultdict(set)
    for record in read_jsonl(INSTRUCTIONS_LOG):
        if record.get("load_reason") != "path_glob_match" or not in_window(record):
            continue
        key = os.path.realpath(os.path.expanduser(record.get("file_path") or ""))
        loaded[key].add(record.get("session_id"))

    touches = [
        (record.get("session_id"), record.get("cwd") or "", target.get("path") or "")
        for record in read_jsonl(BASH_ACCESS_LOG)
        if in_window(record)
        for target in record.get("targets") or []
    ]

    print(f"{'rule':44}{'globs':22}{'loaded':>8}{'bash-only':>11}{'coverage':>10}")
    for path in sorted(rules):
        globs, root = rules[path]
        hit = loaded.get(path, set())
        missed = {
            session
            for session, cwd, target in touches
            if session not in hit
            and (root is None or within(cwd, root))
            and glob_matches(globs, target, cwd)
        }
        total = len(hit) + len(missed)
        coverage = f"{100 * len(hit) / total:.1f}%" if total else "-"
        print(
            f"{shorten_path(path, 42):44}{','.join(globs)[:20]:22}"
            f"{len(hit):>8}{len(missed):>11}{coverage:>10}"
        )

    print(
        "\n単位はセッション数。InstructionsLoaded はセッションごと rule ごとに 1 回だけ発火する。"
    )
    if not os.path.exists(INSTRUCTIONS_LOG):
        print(
            f"注意: {INSTRUCTIONS_LOG} がまだない。hook が未登録か、まだ発火していない。"
        )
    if not os.path.exists(BASH_ACCESS_LOG):
        print(
            f"注意: {BASH_ACCESS_LOG} がまだない。hook が未登録か、まだ発火していない。"
        )
    return 0


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", help="モデル名の部分一致で絞る")
    parser.add_argument("--project", help="プロジェクトディレクトリ名の部分一致で絞る")
    parser.add_argument("--since", help="YYYY-MM-DD 以降のセッションのみ")
    parser.add_argument(
        "--exclude-session",
        action="append",
        default=[],
        help="セッション ID を除外する (複数指定可)",
    )
    parser.add_argument(
        "--include-subagent",
        action="store_true",
        help="subagent (isSidechain) の tool_use も集計する",
    )
    parser.add_argument(
        "--sessions", action="store_true", help="セッション単位の内訳も出す"
    )
    parser.add_argument(
        "--rules",
        action="store_true",
        help="transcript ではなく hook のログから path スコープ付き rule の発火率を出す",
    )
    parser.add_argument(
        "--rule-dir",
        action="append",
        default=[],
        help="rule を探すディレクトリを追加する (既定は ~/.claude/rules と ./.claude/rules)",
    )
    args = parser.parse_args()

    if args.rules:
        return report_rules([*DEFAULT_RULE_DIRS, *args.rule_dir], args.since)

    sessions = collect(args)
    if not sessions:
        print("該当するセッションがない", file=sys.stderr)
        return 1
    report(sessions)

    if args.sessions:
        print(
            f"\n{'date':12}{'model':26}{'steer':16}{'read n/b':>12}{'edit n/b':>12}  path"
        )
        for session in sorted(sessions, key=lambda item: item["date"] or ""):
            native, bash = session["native"], session["bash"]
            print(
                f"{session['date'] or '?':12}{session['model']:26}{session['steer']:16}"
                f"{f'{native[READ]}/{bash[READ]}':>12}"
                f"{f'{native[EDIT]}/{bash[EDIT]}':>12}  "
                f"{os.path.relpath(session['path'], TRANSCRIPT_ROOT)}"
            )
    return 0


if __name__ == "__main__":
    sys.exit(main())
