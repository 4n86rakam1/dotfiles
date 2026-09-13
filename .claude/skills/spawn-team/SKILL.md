---
name: spawn-team
description: Use when work should be split across several independent Claude sessions that coordinate with each other, such as implementation plus review, parallel work on unrelated files, or a long job that should not sit in the current session's context
disable-model-invocation: true
---

# spawn-team

Start several sessions with `claude --bg` and let them coordinate through `SendMessage`. Do not expect arguments. Read the preceding conversation, assemble a configuration, present it, and launch only after approval.

Do not use this when one session suffices. A named `Agent` subagent already handles back-and-forth through `SendMessage`; what it cannot do is outlive the session that spawned it. That difference is the only reason to reach for this skill.

## Deciding the configuration

Three questions decide how many sessions to start. The default is "do not split".

- **Do they touch the same files?** If so, keep them in one session. Separate worktrees still conflict at merge. If a change alters the meaning of a function's return value, whatever reads that return value belongs in the same session
- **Is separating verification worth it?** An implementer measuring their own change only looks at the side that worked. When correctness is judged by classifying every changed result (detectors, parsers, formatters), give verification its own session. Skip this for straightforward work
- **Does parallelism shorten anything?** If the critical path sits in one chain, peeling off the rest does not move the finish time. Independence alone is not a reason to split

Absent a reason to split, use two sessions (worker + lead), or one worker per independent task with no aggregator. **Do not start a session whose only job is aggregation.** Collecting completion notices and artifact paths is something the calling session can do itself.

## Steps

### 1. Decide every name up front

Pass the same string to `-n` and `-w`, so the display name and the worktree share it. That name is the literal `SendMessage` address, and the worktree name becomes a branch name — `SendMessage` itself accepts spaces, but a branch name does not, so write it as a git ref: `fix-go-imports`.

Check `claude agents --json --all` for collisions; plain `--json` omits finished sessions, and those keep their names. A duplicate is not cosmetic: a bare name stops resolving and needs a `[ref]`, and an in-process agent sharing the name always wins, so messages go somewhere else without erroring.

Decide all names now. Then each prompt can name peers that have not started yet, and launch order stops mattering.

### 2. Present the configuration and get approval

Present it as one table, a row per session, so the shape reads at a glance:

| Name | Role | Worktree | Permission mode | Does what |

**Permission mode is a REQUIRED column, not a detail to settle at launch.** Pick it against the Bash the prompt implies — dependency install, `git add`/`git commit`, scripts invoked by path, whatever a test loop reruns — and against the settings allowlist, which on most machines holds read-only commands and nothing else:

| Mode                | In a session nobody is watching                                                                                                                           |
| ------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `acceptEdits`       | Edits and a few filesystem commands. Everything else prompts, and a fresh worktree's `composer install` blocks before the first turn ends                 |
| `auto`              | The usual answer: a classifier reviews each action in the user's place. Prompts come back only after it blocks 3 in a row or 20 in a session              |
| `bypassPermissions` | No checks. `--bg` refuses this mode until the user has accepted the bypass dialog once in an interactive session, so confirm that rather than assuming it |

Under the table put one line on why this split and not another, and one line on anything the user must decide — the permission mode belongs in that line whenever it is above `acceptEdits`. Nothing else — no prompt drafts, no restated background. Launch only after approval.

### 3. Write prompts to files

Always pass prompts via a file, under the handoff directory the sessions share (`~/.cache/<project>-handoff/prompt-<name>.md`). They grow long and the quoting nests badly.

Every prompt states:

- **Goal** — what counts as done
- **Background** — decisions already made. A new session inherits no conversation
- **References** — paths, commits, branches, as absolute paths
- **Its own name, every peer's name and role, and where to report** — the caller's display name if it has one, otherwise the status file to append to. A session with nobody to ask will guess
- **Completion criteria** — tests green, committed, stated concretely
- **Constraints** — files it must not touch, territory held by other running sessions, whether to push

Three role shapes cover the cases:

- **generator-verifier** — worker builds, lead verifies by measurement, failures go back. Use when correctness is only visible in a diff
- **orchestrator** — lead plans and delegates, worker executes
- **team** — coordinator hands out independent tasks

### 4. Launch

```bash
cd <repo> && claude --bg -n <name> -w <name> \
  --permission-mode <mode approved in step 2> "$(cat <prompt-file>)"
```

Pass the mode from the approved table verbatim. Approval was for that mode, so do not raise it here because a session stalled, and do not lower it to `acceptEdits` out of caution — relaunch through step 2 instead.

`--bg` prints a short id (8 hex chars) that `claude attach|logs|stop|rm` take.

Give read-only sessions (a verifier, say) a `-w` too. That keeps a session that can write out of the user's working copy.

Launch one at a time, waiting for each id. `-w` runs `git worktree add` against the shared `.git`, so simultaneous launches can hit index.lock. Start sessions that need dependency setup (`composer install`, `npm ci`) first and launch the others while they install.

### 5. Report

One table, a row per session, status and cwd measured rather than assumed — one call gives you both (`claude agents --json | jq -r '.[] | select(.id=="<id>") | "\(.status) \(.cwd)"'`):

| Name | id | cwd | Status | Role |

Read the status column before you report it: `waiting` is a session stopped at a permission prompt, not one at work, and it never fires `notify_when_idle`. Report it as stopped and say what it is waiting on.

Then two lines: `claude agents` to check them, and `SendMessage(to: "<name>", message: "...")` to add instructions. Do not repeat the prompts or the reasoning — the table and those two lines are the whole report.

## Pitfalls

Only the ones you hit without warning.

| Pitfall                                                                                                                   | What to do                                                                                                                                                                                                                                                                                                                                                                                                                                                                                              |
| ------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| A background session has nobody to answer a permission prompt and stops there the moment one appears                      | The mode table in step 2 is what prevents this; `acceptEdits` on its own does not. It surfaces as `status: "waiting"` in `claude agents --json`, so check that before reading `claude logs <id>` for the cause. A session already stopped there does not resume on a nudge, but it is not lost either: the user can `claude attach <id>` and answer that one prompt, which keeps the work the session has already done. Relaunch through step 2 only when the approved mode is too low for what remains |
| Planning to widen the settings allowlist first, then launch under `acceptEdits`                                           | That route is closed. A caller running in `auto` mode is refused by `[Self-Modification]` when it appends to `permissions.allow` in `.claude/settings.local.json`, through the `update-config` skill as well. The allowlist is the user's to edit, so either they edit it before you launch or the mode in the table carries the work                                                                                                                                                                   |
| Waiting on completion by polling `ListAgents`                                                                             | Pass `notify_when_idle: true` on `SendMessage`, from the main conversation only. Omit `message` for a pure subscription that costs the peer nothing. It fires when that session finishes a turn, so a session stalled at `waiting` never triggers it — pair the subscription with a `status` check                                                                                                                                                                                                      |
| A worktree base misses local commits                                                                                      | Where `worktree.baseRef` is not `head`, the base is `origin/<default>`. Tell the session to check `git log --oneline HEAD..<default-branch>` on startup and rebase when it is non-empty                                                                                                                                                                                                                                                                                                                 |
| `vendor/` and `node_modules/` are gitignored, so a fresh worktree has neither                                             | Make dependency install the first step in the prompt                                                                                                                                                                                                                                                                                                                                                                                                                                                    |
| Concurrent writes to a shared virtualenv or cache (`~/.cache/*/venv`) corrupt it                                          | Write "do not install here; stop and report if something is missing" into the prompt                                                                                                                                                                                                                                                                                                                                                                                                                    |
| Launching while tests are already red makes every session chase the same noise                                            | Run the suite once before launching and confirm the baseline is green                                                                                                                                                                                                                                                                                                                                                                                                                                   |
| `SendMessage` sent from a subagent to a background session returns to the parent session's conversation, not the subagent | Keep primary reporting in files (`~/.cache/<project>-handoff/status-<role>.md`) and use `SendMessage` for launch signals and nudges                                                                                                                                                                                                                                                                                                                                                                     |
| Taking a worker's "tests green" or "fixed N cases" at face value                                                          | Run the suite yourself on each branch. Implementers see the side that worked; what broke and what overreached only surface by classifying the whole diff                                                                                                                                                                                                                                                                                                                                                |

## Out of scope

- **Merging the branches and cleaning up afterwards.** `claude rm <id>` drops the session; the worktrees and branches are yours to integrate under whatever the project's merge rules are
- **Raising the permission mode on your own.** Launching a session more permissive than the one you are in routes around a decision the user made about your session. `bypassPermissions` is not off limits — it is the user's to grant, which is what the mode column in step 2 exists for. What stays out of scope is picking a mode they have not seen: at launch, on a relaunch, or when nudging a session already stalled at `waiting`

## Worked example

Four fixes in one analyzer: three touched the same file, and one of those three altered a function's return meaning, so everything reading it stayed together. The fourth was independent but sat off the critical path, so splitting it would have bought nothing. One worker, one lead, generator-verifier — and the lead sent back four items, three of which the reports alone read clean on.
