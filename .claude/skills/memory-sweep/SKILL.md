---
name: memory-sweep
description: Sweep the auto-memory of every project (~/.claude/projects/*/memory/) and report cross-project duplicates, consolidation candidates, pending tasks, and stale entries. Read-only: no deletions, merges, or index fixes.
disable-model-invocation: true
---

# Memory Sweep

Take stock of auto-memory across every project. Fixing anything inside a single project (deleting, merging, reconciling the index) is `memory-audit`'s job. This skill never modifies a file.

## Scope

Every `~/.claude/projects/*/memory/`. Each directory holds `MEMORY.md` as its index plus one `.md` file per entry.

A memory directory is sometimes a symlink to a `.claude/memory` inside the project, so the sweep uses a shell glob: `find` does not follow the symlink and would miss it. `collect.sh` accounts for this.

A file's `frontmatter.name` is kebab-case and often does not match its snake_case filename. A `[[name]]` reference resolves against `frontmatter.name`.

## Steps

1. **Mechanical pass** — run `bash ~/.claude/skills/memory-sweep/collect.sh`. It returns TSV in four line types.
   - `PROJ`: project / entry count excluding MEMORY.md / days since the newest update / whether an index exists
   - `FILE`: project / filename / days since update / name / type / description
   - `TASK`: project / filename / line number / line body
   - `WARN`: project / filename / reason

   A `WARN` means that target could not be swept. Report it in one line at the top of the report, under "not swept". Never drop it silently.

2. **Deep read** — pick duplicate-cluster candidates from the `FILE` rows and Read **only the files you picked**, comparing their bodies. Reading in full stays limited to candidates. Choosing candidates:
   - Prefer combinations that cross projects, where `type` matches and the descriptions overlap in subject
   - Treat any `type: user` or `type: feedback` sitting in an individual project as a candidate even when subjects do not overlap, since that content likely belongs to the global scope
   - Duplication contained within one project belongs to `memory-audit`, so do not pursue it here

3. **Report** — emit the three sections below, omitting any that are empty. If all are empty, print `No findings.` and stop. Give every item an `[id]`: `C1` for consolidation, `T1` for a pending task, `S1` for staleness.

   ```markdown
   - [C1] `<project>/<file>` ↔ `<project>/<file>` — <what is duplicated>. Consolidate into: <proposal>.
   ```

   The sections and what goes in them:
   - **Cross-project duplicates and consolidation candidates** — the same fact scattered across projects, plus `type: user` and `feedback` entries sitting in individual projects. State whether the home directory's project or the global `~/.claude/CLAUDE.md` is the better destination.
   - **Pending tasks** — group the `TASK` rows by project. Drop hits where the word merely appears in a description or heading. Judge in the language the memory itself is written in.
   - **Stale and abandoned** — `type: project` entries untouched for over 90 days, and projects whose newest `PROJ` update is over 90 days old. The user can change the threshold.

4. **Hand off** — close the report with one line pointing each project that needs fixing at `/memory-audit`, run from that cwd. This skill neither performs nor proposes deletions, merges, or index edits.

## Judgment

Match `memory-audit`.

- Bias toward keeping. Historical facts, learning notes, and references stay valuable when old. The mtime gate applies to `type: project` only.
- An unresolved `[[name]]` is a forward reference, not a problem.
- The per-type filename prefixes (`project_`, `feedback_`, `reference_`, `user_`) are a naming convention and never evidence of duplication.
- Duplication requires the same subject. Sharing a domain is not enough.
- For the current date, prefer `currentDate` from the system reminder, falling back to `date +%Y-%m-%d`.

## Notes

- Pending tasks are reported, never resolved. Whether the underlying task is done is a human judgment.
- In projects with dozens of entries, the deep read eats context unless it stays narrow. Do not skip picking candidates before reading.
- `collect.sh` caps task-word hits at five per file. Anything beyond that never reaches the summary, so Grep a file directly when scrutinizing it.
