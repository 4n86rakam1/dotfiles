---
name: catchup
description: Reconstruct where the work stands, then list what is left. Reads the current project's auto-memory, reconciles it against real git state, and reports outstanding tasks in priority order with evidence. Mainly for the first message of a session. Triggers include "残タスクは？", "メモリから残タスク把握して", "メモリから状況把握して", "やり残し", "どこまで進んだ", "他にやったほうが良いことを洗い出して", "catch up on this project". Report-only — never edits files, never starts the work.
---

# Catchup

## Purpose

Answer "where did I leave off, and what is left" at the start of a session. Memory records what a past session believed; the repository records what actually happened. Most of what decides the report was never written to memory at all — what is unpushed, what CI last did, which branch a fix actually lives on — so build the listing from the repository and let memory supply the intent behind it. A memory claim that turns out contradicted gets reported rather than quietly used.

Primary target is the first message of a session, when the conversation carries no context yet. When invoked mid-session, prefer what the conversation already established and re-read only the delta — do not repeat a full sweep that this session has already done.

## Scope

The auto-memory directory for the current cwd: `~/.claude/projects/<sanitized-cwd>/memory/`, where `<sanitized-cwd>` collapses `/` and `.` in the absolute cwd to `-` (`/home/user/.foo` → `-home-user--foo`).

```bash
ls -d ~/.claude/projects/"$(pwd | tr '/.' '--')"/memory/
```

A worktree has its own memory directory, separate from the main checkout's. When cwd is under `.claude/worktrees/`, resolve the main checkout's as well and read both — project-wide state lives in the main checkout's memory, while the worktree's holds only the current branch's work.

```bash
ls -d ~/.claude/projects/"$(git rev-parse --path-format=absolute --git-common-dir | sed 's|/\.git$||' | tr '/.' '--')"/memory/
```

Build the path directly rather than grepping the project list: a substring match returns the worktree entries alongside the main checkout's, and telling those apart is the point.

## Delegation

Steps 2 and 3 are the ones that read raw material. When there is enough of it to crowd the context — more than 10 memory entries in total, more than 10 files under `docs/plan(s)/`, or entries whose combined size you would not want in full — hand both steps to parallel `Explore` subagents and keep only what they report. Instruct them to extract unfinished work only, to exclude anything already completed, and to invent no item that is not written down. Below that bar, read directly. The remaining steps are the same either way.

## Steps

1. **Locate** — Check whether cwd is a git repository (`git rev-parse --is-inside-work-tree`); step 3 depends on the answer. Resolve the memory directory, and in a worktree the main checkout's too. Count the entries in each, excluding `MEMORY.md` itself (`ls <memory dir> | grep -cv '^MEMORY\.md$'`) — counting the index as an entry crosses the delegation bar a file early. If a memory directory is missing or holds no `MEMORY.md`, say so in one line and continue with git and docs alone. Neither that nor a non-repository cwd is a reason to stop.

2. **Collect** — Gather what is unfinished: `MEMORY.md` first, then the entries it links that bear on current work, plus `docs/plan/` or `docs/plans/` if either exists. Hook lines in the index carry facts, not just titles, so open an entry only where its hook line stops short of what the report needs — it gestures at detail without stating it, or an item will need a `file:line` citation from inside the file. Opening an entry whose hook line already answers the question buys nothing — in one measured run, two of the four files opened, a quarter of its context. A memory file's `frontmatter.name` is often not its filename, and `[[name]]` references resolve against `frontmatter.name`. Do not read every file in the repository.

3. **Reconcile** — Establish the present state from the repository itself. Skip this step when step 1 found no repository, and say so in the report's opening line, since every claim then rests on memory alone.

   Run `git log --oneline -5`, `git status --short`, `git worktree list`, `git branch -vv`, and `git branch --no-merged <default-branch>` in one call. `git branch -vv` is the one that shows the gap against the remote — an unpushed default branch is often the most consequential fact in the whole report, and none of the other four reveal it. Widen the log past five commits only when the current-state lines need more.

   Resolve the default branch as a local branch name — `git symbolic-ref --quiet --short refs/remotes/origin/HEAD | cut -d/ -f2-`, falling back to whichever of `main` or `master` exists. Keep the name local: `origin/<branch>` reports the local default branch itself as unmerged work whenever it sits ahead of the remote, which is the normal state here.

   A branch `git branch --no-merged` lists while `git worktree list` does not — a worktree removed with its branch left behind — belongs in the report unless a memory entry accounts for it: a discrepancy when memory is silent, a cleanup item when memory called it disposable and it is still there.

   Check a memory's specifics only where an item you are about to report rests on them — that a path, branch or issue it names still exists, that a commit it calls pending is not already in the log, that code it calls done is actually there. Auditing every claim memory makes belongs to `/memory-audit` and mostly finds nothing once that has run; a claim you are not going to report is not worth the check. Where a discrepancy does surface, report it — memory drifts again as soon as work continues past the last audit.

   A grep that returns nothing is not proof of absence. Numbers and names get spelled out in prose — `Nineteen paths change` never matches `19` — so try a second spelling (the word form, another case, a hyphen variant) before declaring a memory's claim stale.

4. **Report** — Open with a short paragraph of current state: which branch and worktrees are live, what was most recently done. Then emit sections labelled `A.`, `B.`, `C.` and onwards, as many as the work actually has, with the items numbered continuously across all of them so that a bare number identifies one item unambiguously and never collides with a section label — the user picks what to work on by replying with one. Omit any section that would be empty and keep the letters contiguous — a report with no memory discrepancies still starts at `A.`. Cap the list at 15 items and fold the remainder into a closing "他 N 件" line. A heading reads `## A. <カテゴリ>`, and every item carries its evidence after a `根拠:` — `N. <タスク> — 根拠: <file:line / commit / memory entry>`.

   One item is one thing the user can pick up on its own. An item that disappears once another is done, or that restates a slice of one, goes inside that item as a clause rather than onto a line of its own — splitting it out raises the count without adding a decision to make. A section holding a single item is the right shape whenever the work holds one, and below four items in total the headings come off entirely: a bare numbered list carries more than three axes with one item each.

   The memory discrepancies come first when there are any, because everything below them rests on memory being accurate. Group the remaining sections by whatever axis the work actually has — risk, subproject, or phase — rather than a fixed taxonomy. Close with a single line labelled `着手順の推奨:` recommending what to pick up first and why, plus one more suggesting `/memory-audit` when the discrepancy section is present.

## Notes

- Report-only. Do not edit memory, do not write the list to a file, do not start any task in it. Repairing memory belongs to `/memory-audit`; summarising the session for whoever picks it up next is a separate job.
- If a list would be useful as a file, propose a path in one line and wait for the user to approve it. Never create it unasked.
- An item earns its place only if step 3 shows it genuinely outstanding and a memory entry, document, commit, or diff supports it. An empty list is a valid answer; a padded one is not.
- Discrepancies found here overlap `memory-audit`'s Stale detection. The split is deliberate — this skill reports what it runs into, that one goes looking and repairs — but when either definition changes, change both.
- Current date: prefer `currentDate` from the system-reminder; fall back to `date +%Y-%m-%d`.
