# Shared Code Style

- Comments explain WHY only. Never write WHAT or anything self-evident.
- Never write progress output via `echo` or `print`. Errors go to stderr.
- Turn magic numbers into named constants. Leave no unused imports.
- Give Bash scripts a shebang (Python does not need one). Apply `~/.claude/rules/code-style-sh.md` to any script with a shebang.
