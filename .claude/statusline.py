import json
import os
import re
import shutil
import subprocess
import sys
import unicodedata
from datetime import datetime, timezone
from pathlib import Path

RESET = "\033[0m"
CYAN = "\033[36m"
GREEN = "\033[32m"
YELLOW = "\033[33m"
RED = "\033[31m"
BLUE = "\033[34m"
DIM = "\033[2m"

USAGE_PCT_CRITICAL = 85
USAGE_PCT_WARNING = 60
TOKENS_PER_K = 1000
TOKENS_PER_M = 1_000_000
TOKENS_DROP_FRACTION_ABOVE = 100_000
SECONDS_PER_MINUTE = 60
MINUTES_PER_HOUR = 60
HOURS_PER_DAY = 24
MS_PER_SECOND = 1000

SEPARATOR = " | "
PATH_MAX_WIDTH = 32
WORKTREE_BRANCH_PREFIX = "worktree-"
PATH_TAIL_DEPTH = 2
FALLBACK_COLUMNS = 120
RIGHT_MARGIN = 2
WIDE_EAST_ASIAN = ("W", "F")

_GIT = shutil.which("git")
_ANSI_RE = re.compile(r"\033\[[0-9;]*m")
_CONTEXT_SIZE_RE = re.compile(r"\((\d+[KM]) context\)")
_MODEL_FAMILY_RE = re.compile(r"^([A-Z])[a-z]+ ")


def display_width(text):
    plain = _ANSI_RE.sub("", text)
    return sum(
        2 if unicodedata.east_asian_width(c) in WIDE_EAST_ASIAN else 1 for c in plain
    )


def terminal_width():
    # stdout が Claude Code に捕捉されるため ioctl や tput では幅を取れない
    try:
        return int(os.environ["COLUMNS"]) - RIGHT_MARGIN
    except (KeyError, ValueError):
        return FALLBACK_COLUMNS


def line_width(segments):
    texts = [text for _, text in segments]
    return sum(map(display_width, texts)) + len(SEPARATOR) * (len(texts) - 1)


def fit(segments, width):
    """(優先度, 文字列) の並びを幅に収める。数値の大きい優先度から捨てる。"""
    kept = [seg for seg in segments if seg[1]]
    while len(kept) > 1 and line_width(kept) > width:
        kept.remove(max(kept, key=lambda seg: seg[0]))
    return SEPARATOR.join(text for _, text in kept)


def usage_color(used_pct):
    if used_pct >= USAGE_PCT_CRITICAL:
        return RED
    if used_pct >= USAGE_PCT_WARNING:
        return YELLOW
    return GREEN


def progress_bar(used_pct, width=8):
    filled = round(used_pct / 100 * width)
    return "█" * filled + "░" * (width - filled)


def fmt_tokens(n):
    if n is None:
        return "--"
    if n >= TOKENS_DROP_FRACTION_ABOVE:
        return f"{n // TOKENS_PER_K}k"
    if n >= TOKENS_PER_K:
        return f"{n / TOKENS_PER_K:.1f}k"
    return str(n)


def fmt_countdown(epoch):
    if epoch is None:
        return None
    remaining = max(0, epoch - datetime.now(timezone.utc).timestamp())
    total_m = int(remaining // SECONDS_PER_MINUTE)
    h, m = divmod(total_m, MINUTES_PER_HOUR)
    if h >= HOURS_PER_DAY:
        d, h = divmod(h, HOURS_PER_DAY)
        return f"{d}d{h}h"
    return f"{h}h{m:02d}m" if h > 0 else f"{m}m"


def fmt_elapsed(ms):
    if not ms:
        return None
    total_s = ms // MS_PER_SECOND
    if total_s < SECONDS_PER_MINUTE:
        return f"{total_s}s"
    minutes = total_s // SECONDS_PER_MINUTE
    seconds = total_s % SECONDS_PER_MINUTE
    if minutes < MINUTES_PER_HOUR:
        return f"{minutes}m{seconds:02d}s"
    hours = minutes // MINUTES_PER_HOUR
    remaining_minutes = minutes % MINUTES_PER_HOUR
    return f"{hours}h{remaining_minutes:02d}m"


def elide_path(text):
    if display_width(text) <= PATH_MAX_WIDTH:
        return text
    parts = text.split("/")
    if len(parts) <= PATH_TAIL_DEPTH + 1:
        return text
    return "/".join([parts[0], "…", *parts[-PATH_TAIL_DEPTH:]])


def shorten_path(path):
    if not path:
        return "?"
    p = Path(path)
    home = Path.home()
    try:
        rel = p.relative_to(home)
    except ValueError:
        return elide_path(path)
    return "~" if str(rel) == "." else elide_path(f"~/{rel}")


def fmt_model(data):
    model = data.get("model") or {}
    name = model.get("display_name") or model.get("id") or "unknown"
    name = _CONTEXT_SIZE_RE.sub(r"\1", name.replace("Claude ", ""))
    name = _MODEL_FAMILY_RE.sub(r"\1", name)
    text = f"{DIM} {name}"
    level = ((data.get("effort") or {}).get("level") or "").strip()
    if level:
        text += f"·{level}"
    if data.get("fast_mode"):
        text += " ⚡"
    return text + RESET


def fmt_agent(data):
    name = ((data.get("agent") or {}).get("name") or "").strip()
    if not name:
        return None
    return f"{YELLOW}▸ {name}{RESET}"


def fmt_window_size(n):
    if n >= TOKENS_PER_M:
        return f"{n / TOKENS_PER_M:g}M"
    return f"{n // TOKENS_PER_K}k"


def fmt_context(ctx):
    used = ctx.get("used_percentage")
    if used is None:
        return f"{DIM}ctx:--{RESET}"
    text = f"{usage_color(used)}ctx:{progress_bar(used)} {used:.0f}%"
    # 同じ % でも 1M と 200K では絶対量が 5 倍違う
    if (tokens := ctx.get("total_input_tokens")) is not None:
        size = ctx.get("context_window_size")
        limit = f"/{fmt_window_size(size)}" if size else ""
        text += f"{DIM} {fmt_tokens(tokens)}{limit}"
    return text + RESET


def fmt_rate_window(window_data, label):
    if not window_data:
        return None
    if (raw := window_data.get("used_percentage")) is None:
        return None
    used_pct = float(raw)
    countdown = fmt_countdown(window_data.get("resets_at"))
    reset_str = f" →{DIM}{countdown}{RESET}" if countdown else ""
    bar = f"{usage_color(used_pct)}{progress_bar(used_pct)} {label}:{used_pct:.0f}%{RESET}"
    return bar + reset_str


def fmt_meta(cost):
    items = []
    cost_usd = cost.get("total_cost_usd")
    if cost_usd is not None:
        items.append(f"${cost_usd:.3f}")
    added = cost.get("total_lines_added", 0) or 0
    removed = cost.get("total_lines_removed", 0) or 0
    if added or removed:
        items.append(f"+{added}/−{removed}")  # noqa: RUF001
    elapsed = fmt_elapsed(cost.get("total_duration_ms"))
    if elapsed:
        items.append(f"⏱ {elapsed}")
    if not items:
        return None
    return f"{DIM}{'  '.join(items)}{RESET}"


def git_output(cwd, args):
    if _GIT is None or not cwd:
        return None
    try:
        return (
            subprocess.check_output(
                [_GIT, "--no-optional-locks", *args],
                stderr=subprocess.DEVNULL,
                cwd=cwd,
            )
            .decode()
            .strip()
        )
    except (subprocess.CalledProcessError, OSError):
        return None


def fmt_vcs(data):
    cwd = data.get("cwd") or ""
    worktree_name = ((data.get("worktree") or {}).get("name") or "").strip()
    marker = f"{YELLOW}*{GREEN}" if git_output(cwd, ["status", "--porcelain"]) else ""
    if worktree_name:
        branch = ((data.get("worktree") or {}).get("branch") or "").strip()
        # EnterWorktree は worktree-<name> を切るので、その分だけ併記しても情報が増えない
        derived = (worktree_name, f"{WORKTREE_BRANCH_PREFIX}{worktree_name}")
        suffix = f" {branch}" if branch and branch not in derived else ""
        return f"{GREEN}⎇ {worktree_name}{marker}{suffix}{RESET}"
    branch = git_output(cwd, ["rev-parse", "--abbrev-ref", "HEAD"])
    if not branch or branch == "HEAD":
        return None
    return f"{GREEN} {branch}{marker}{RESET}"


def fmt_location(data):
    # worktree 配下の実パスより、元リポジトリの位置のほうが手掛かりになる
    base = (data.get("worktree") or {}).get("original_cwd") or data.get("cwd") or ""
    return f"{BLUE} {shorten_path(base)}{RESET}"


def main():
    try:
        data = json.loads(sys.stdin.read())
    except (json.JSONDecodeError, OSError, UnicodeDecodeError):
        data = {}

    ctx = data.get("context_window") or {}
    rate_limits = data.get("rate_limits") or {}
    width = terminal_width()

    # 表示順はこの並び、幅が足りないときは第 1 要素の大きいものから捨てる
    segments = [
        (5, fmt_model(data)),
        (2, fmt_agent(data)),
        (1, fmt_vcs(data)),
        (3, fmt_location(data)),
        (0, fmt_context(ctx)),
        (4, fmt_rate_window(rate_limits.get("five_hour"), "5h")),
        (7, fmt_rate_window(rate_limits.get("seven_day"), "7d")),
        (6, fmt_meta(data.get("cost") or {})),
    ]

    if line := fit(segments, width):
        print(line)


if __name__ == "__main__":
    main()
