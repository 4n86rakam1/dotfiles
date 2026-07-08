---
name: memory-audit
description: Read-only audit of the current project's auto-memory (~/.claude/projects/<sanitized-cwd>/memory/). Surfaces stale entries, broken links, duplicates, and pending tasks. Reports findings only — never edits, deletes, or proposes cleanup follow-ups.
disable-model-invocation: true
---

# Memory Audit

## Scope

`~/.claude/projects/<sanitized-cwd>/memory/` for the current cwd. `<sanitized-cwd>` collapses `/` and `.` in the absolute cwd to `-` (`/home/user/.foo` → `-home-user--foo`). Confirm the exact directory before reading: `ls ~/.claude/projects/ | grep -F -- "$(pwd | tr '/.' '--')"`. The directory holds `MEMORY.md` (index) plus per-entry `.md` files.

Note: a memory file's `frontmatter.name` (kebab-case) is often not equal to its filename (snake_case). Example: `reference_vscode_layout.md` has `name: dotfiles-vscode-layout`. `[[name]]` references resolve against `frontmatter.name`, not the filename.

## Steps

1. **Collect** — Read `MEMORY.md`. For each linked entry, Read the target `.md`. Extract frontmatter (`name`, `description`, `metadata.type`), body text, and file mtime. If the memory dir or `MEMORY.md` is missing, report that and stop. If an individual memory file has malformed frontmatter or fails to parse, record it as a finding and continue with the rest.

2. **Detect** — Gather findings under 4 categories:
   - Stale (any of): `metadata.type: project` AND mtime older than the staleness threshold (default 90 days, override on user request); OR a past-due DEADLINE written as a scheduled event ("freeze on YYYY-MM-DD", "ship by X") — but NOT a past date describing an ongoing STATE ("freeze started YYYY-MM-DD" with no end); OR a referenced path, function, branch, or issue no longer exists (verify with grep / Read / `gh`).
   - Broken links: `MEMORY.md` index entries pointing at missing files. Do NOT flag `[[name]]` mentions in body text that resolve to nothing — user-memory convention treats them as forward references to memories worth writing later.
   - Duplicates: two or more files that share `metadata.type` AND have overlapping descriptions or body topics (same subject, not merely same domain). Cross-references via `[[name]]` are not overlap. Ignore shared `type_` filename prefixes (`project_`, `feedback_`, `reference_`, `user_`) — they are naming convention, not duplication signal.
   - Pending tasks: body mentions any of "TODO", "pending", "later", "next time", "保留", "後で", "未完了", "要検討", "宿題", or a dated commitment still open. Match language of the memory file itself.

3. **Report** — Emit up to 4 Markdown sections, one per non-empty category. Omit empty sections. When all sections are empty, output exactly `No findings.` Report language follows the user's global preference (Japanese). Format each finding as:

   ```markdown
   - `<file>` — <reason>. Suggested: <action>.
   ```

4. **Stop** — The skill's job ends at the report. Do NOT prompt the user to clean anything up, and do NOT perform deletions or edits. If the user later requests a specific cleanup in a follow-up turn, treat that as a separate task.

## Notes

- Current date: prefer `currentDate` from the system-reminder; fall back to `date +%Y-%m-%d`.
- Bias toward keeping. Historical facts, learning notes, and reference material stay valuable even when old — `type: project` is the only mtime-based stale gate.
- Cross-repo checks: use `git -C <path>` when a referenced repo differs from the current cwd.
- Large memory dirs: Grep the whole dir first to shortlist candidates, then Read per file.
