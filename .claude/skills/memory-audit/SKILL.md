---
name: memory-audit
description: Audit and update the current project's auto-memory (~/.claude/projects/<sanitized-cwd>/memory/). Surfaces stale entries, broken links, duplicates, and pending tasks, then applies user-approved cleanups. Pending tasks are report-only.
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

3. **Report and propose** — Emit up to 4 Markdown sections, one per non-empty category. Omit empty sections. When all sections are empty, output exactly `No findings.` and stop. Report language follows the user's global preference (Japanese). Format each actionable finding as:

   ```markdown
   - [id] `<file>` — <reason>. Action: <proposed change>.
   ```

   `id` is a stable per-run identifier (e.g. `S1`, `S2` for stale; `B1` for broken links; `D1` for duplicates). Pending tasks are report-only — omit the `Action:` field and mark them `(report-only)`.

   Proposed actions per category:
   - Stale → `delete file + remove index entry`
   - Broken links → `remove index entry`
   - Duplicates → `merge <source> into <target>, delete source, update index` (identify the target as the older, more informative, or better-linked file; state the choice)

4. **Confirm** — After the report, ask exactly one question: `apply all / apply [ids] / none`. Wait for the user's reply. Interpret:
   - `apply all` or `all` — apply every actionable finding
   - `apply S1 D2 …` or a bare list of ids — apply only the listed ids
   - `none`, `skip`, `no`, or an empty reply — apply nothing and stop

5. **Apply** — For each approved finding, execute the proposed action:
   - Delete file: `rm <file>` via Bash
   - Remove index entry: Edit `MEMORY.md`, delete the matching `- [Title](file.md) — ...` line
   - Merge: Read both files, append or splice source's unique content into target's body (preserve target's frontmatter, update `description` only if the merged content demands it), then delete source and remove source's index entry
     Apply in this order to keep `MEMORY.md` consistent: merges → deletes → index removals.

6. **Report result** — After applying, emit a one-line summary per category: `applied: <n> / skipped: <n>`. If any action failed, list the failure with its `id` and the error.

## Notes

- Current date: prefer `currentDate` from the system-reminder; fall back to `date +%Y-%m-%d`.
- Bias toward keeping. Historical facts, learning notes, and reference material stay valuable even when old — `type: project` is the only mtime-based stale gate.
- Cross-repo checks: use `git -C <path>` when a referenced repo differs from the current cwd.
- Large memory dirs: Grep the whole dir first to shortlist candidates, then Read per file.
- Pending tasks never become actions — resolving a `保留` / `TODO` requires human judgment on whether the underlying task is done. Report and leave.
- Never delete `MEMORY.md` itself. Never modify entries the user has not approved for the current run.
