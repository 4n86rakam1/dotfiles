import json
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

RESET = "\033[0m"
CYAN = "\033[36m"
GREEN = "\033[32m"
YELLOW = "\033[33m"
RED = "\033[31m"
BLUE = "\033[34m"
MAGENTA = "\033[35m"
DIM = "\033[2m"

USAGE_PCT_CRITICAL = 85
USAGE_PCT_WARNING = 60
TOKENS_PER_K = 1000
SECONDS_PER_MINUTE = 60

_GIT = shutil.which("git")


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
    if n >= TOKENS_PER_K:
        return f"{n / TOKENS_PER_K:.1f}k"
    return str(n)


def fmt_countdown(epoch):
    if epoch is None:
        return None
    remaining = max(0, epoch - datetime.now(timezone.utc).timestamp())
    total_m = int(remaining // SECONDS_PER_MINUTE)
    h = total_m // SECONDS_PER_MINUTE
    m = total_m % SECONDS_PER_MINUTE
    return f"{h}h{m:02d}m" if h > 0 else f"{m}m"


def fmt_elapsed(ms):
    if not ms:
        return None
    total_s = ms // 1000
    if total_s < SECONDS_PER_MINUTE:
        return f"{total_s}s"
    minutes = total_s // SECONDS_PER_MINUTE
    seconds = total_s % SECONDS_PER_MINUTE
    if minutes < SECONDS_PER_MINUTE:
        return f"{minutes}m{seconds:02d}s"
    hours = minutes // SECONDS_PER_MINUTE
    remaining_minutes = minutes % SECONDS_PER_MINUTE
    return f"{hours}h{remaining_minutes:02d}m"


def shorten_path(path):
    if not path:
        return "?"
    p = Path(path)
    home = Path.home()
    try:
        rel = p.relative_to(home)
        return "~" if str(rel) == "." else f"~/{rel}"
    except ValueError:
        return path


def fmt_model(model_obj):
    name = model_obj.get("display_name") or model_obj.get("id") or "unknown"
    return f"{CYAN} {name.replace('Claude ', '')}{RESET}"


def fmt_context(ctx):
    used = ctx.get("used_percentage")
    if used is None:
        return f"{DIM}ctx:--{RESET}"
    color = usage_color(used)
    return f"{color}ctx:{progress_bar(used)} {used:.0f}%{RESET}"


def fmt_tokens_part(ctx):
    tok_in = ctx.get("total_input_tokens")
    tok_out = ctx.get("total_output_tokens")
    if tok_in is None and tok_out is None:
        return None
    return f"{DIM}↑{fmt_tokens(tok_in)} ↓{fmt_tokens(tok_out)}{RESET}"


def fmt_rate_window(window_data, label):
    if not window_data:
        return None
    if (raw := window_data.get("used_percentage")) is None:
        return None
    used_pct = float(raw)
    remaining_pct = 100.0 - used_pct
    countdown = fmt_countdown(window_data.get("resets_at"))
    reset_str = f" →{DIM}{countdown}{RESET}" if countdown else ""
    bar = (
        f"{usage_color(used_pct)}{progress_bar(used_pct)}"
        f" {label}: {remaining_pct:.0f}%{RESET}"
    )
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


def fmt_git(cwd):
    if _GIT is None:
        return None
    try:
        branch = (
            subprocess.check_output(
                [_GIT, "rev-parse", "--abbrev-ref", "HEAD"],
                stderr=subprocess.DEVNULL,
                cwd=cwd,
            )
            .decode()
            .strip()
        )
        if not branch or branch == "HEAD":
            return None
        dirty = bool(
            subprocess.check_output(
                [_GIT, "status", "--porcelain"],
                stderr=subprocess.DEVNULL,
                cwd=cwd,
            )
            .decode()
            .strip(),
        )
        marker = f"{YELLOW}*{GREEN}" if dirty else ""
    except (subprocess.CalledProcessError, OSError):
        return None
    else:
        return f"{GREEN} {branch}{marker}{RESET}"


def main():
    data = json.loads(sys.stdin.read())

    cwd = data.get("cwd", "")
    ctx = data.get("context_window") or {}
    rate_limits = data.get("rate_limits") or {}

    parts = [fmt_model(data.get("model") or {})]

    session_name = (data.get("session_name") or "").strip()
    if session_name:
        parts.append(f"{MAGENTA} {session_name}{RESET}")

    parts.append(fmt_context(ctx))

    tok_part = fmt_tokens_part(ctx)
    if tok_part:
        parts.append(tok_part)

    parts.extend(
        filter(
            None,
            [
                fmt_rate_window(rate_limits.get("five_hour"), "5h"),
                fmt_rate_window(rate_limits.get("seven_day"), "7d"),
            ],
        ),
    )

    meta = fmt_meta(data.get("cost") or {})
    if meta:
        parts.append(meta)

    git_part = fmt_git(cwd)
    if git_part:
        parts.append(git_part)

    parts.append(f"{BLUE} {shorten_path(cwd)}{RESET}")

    print(" | ".join(parts))


if __name__ == "__main__":
    main()
