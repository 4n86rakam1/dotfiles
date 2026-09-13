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
- **Is separating verification worth it?** An implementer measuring their own change only looks at the side that worked. Ask this of the evidence, not of the subject matter: when confirming the change means classifying every result it produced — each page, each row, each match — and the one who produced them would also be deriving what the right answer was, verification belongs in its own session. Detectors and parsers are the obvious shape, but a generator emitting a set of files from a list it derived itself is the same shape, and so is anything whose expected output nobody wrote down beforehand. Skip this only when one command's exit code settles the question
- **Does parallelism shorten anything?** If the critical path sits in one chain, peeling off the rest does not move the finish time. Independence alone is not a reason to split

Absent a reason to split, use two sessions (worker + lead), or one worker per independent task with no aggregator. **Do not start a session whose only job is aggregation.** Collecting completion notices and artifact paths is something the calling session can do itself.

That prohibition does not reach a verifier. A verifier produces a measurement nobody else has; an aggregator only forwards what the others already reported. So "one worker per independent task with no aggregator" says nothing about whether to add one — the verification question above decides that by itself, and it decides it after the workers are counted, not instead of counting them.

## Steps

### 1. Decide every name up front

Pass the same string to `-n` and `-w`, so the display name and the worktree share it. That name is the literal `SendMessage` address, and the worktree name becomes a branch name — `SendMessage` itself accepts spaces and brackets, but a branch name takes neither, so write it as a git ref.

Spell it `<role>-<task>`, the role drawn from `worker`, `verifier`, `lead`: `worker-fix-go-imports`, `verifier-fix-go-imports`. One string then serves as display name, worktree, and branch, so which session holds which branch reads off the name instead of being measured later. The caller is the exception — a running session cannot rename itself — so its role lives in the Role column of the table below.

Check `claude agents --json --all` for collisions; plain `--json` omits finished sessions, and those keep their names. A duplicate is not cosmetic: a bare name stops resolving and needs a `[ref]`, and an in-process agent sharing the name always wins, so messages go somewhere else without erroring.

Decide all names now. Then each prompt can name peers that have not started yet, and launch order stops mattering.

### 2. Present the configuration and get approval

Present it as one table, a row per session, so the shape reads at a glance:

| Name | Role | Worktree | Permission mode | Does what |

**The caller is the first row.** Its Name is its own display name, or `(this session)` when it has none; its Worktree is normally none, meaning the user's working copy; its Permission mode is the mode it is running in, read rather than assumed. Leave the row out and the launch gets approved while the caller's own conduct does not, which is how one team ends up supervised and the next one abandoned.

The caller's Role is one of three words:

- **`supervisor`** — on each completion notice, check out that branch, run the suite, classify the diff, send shortfalls back through `SendMessage`
- **`relay`** — carry the verifier's measurement to the user, measuring nothing itself
- **`hands-off`** — report the launch and stop. Only when the user asks for it

A configuration with a verifier in it makes the caller a `relay`; one without makes it a `supervisor`. Same logic as the aggregator prohibition: the caller does what no session needs to exist for, and it measures only when no session was given the measurement.

Three things stay the caller's whichever word applies — noticing a session stopped at `waiting`, arranging its recovery, and relaying to the user. In a team nobody is watching, there is no one else to do them.

**Permission mode is a REQUIRED column, not a detail to settle at launch.** Pick it against the Bash the prompt implies — dependency install, `git add`/`git commit`, scripts invoked by path, whatever a test loop reruns — and against the settings allowlist, which on most machines holds read-only commands and nothing else:

| Mode                | In a session nobody is watching                                                                                                                           |
| ------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `acceptEdits`       | Edits and a few filesystem commands. Everything else prompts, and a fresh worktree's `composer install` blocks before the first turn ends                 |
| `auto`              | The usual answer: a classifier reviews each action in the user's place. Prompts come back only after it blocks 3 in a row or 20 in a session              |
| `bypassPermissions` | No checks. `--bg` refuses this mode until the user has accepted the bypass dialog once in an interactive session, so confirm that rather than assuming it |

Under the table put one line on why this split and not another, one line on verification — which session measures the result, or why no session needs to — and one line on anything the user must decide; the permission mode belongs in that line whenever it is above `acceptEdits`. **The verification line is required even when the answer is no**, because a table of workers looks complete whether the question was asked or skipped, and that is the one omission the user cannot see. Nothing else — no prompt drafts, no restated background. Launch only after approval.

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

- **generator-verifier** — worker builds, verifier measures, failures go back. Use when correctness is only visible in a diff. Tell the verifier to commit nothing and to write its measurement to its status file: a verifier that adds tests writes into the same files the worker touched, and that is the one collision the file-overlap question cannot screen out
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

Carry the caller's row into this table too, with the Role word from step 2, so the report says who is watching.

Then two lines: `claude agents` to check them, and `SendMessage(to: "<name>", message: "...")` to add instructions. Do not repeat the prompts or the reasoning — the table and those two lines are the whole report.

The report closes the launch, not the caller's turn. Unless the caller is `hands-off`, subscribe with `notify_when_idle: true` before reporting and then hold the role step 2 approved. `hands-off` is the only word that ends here.

### 6. Wind the team down

Only on the user's word. Completion notices from every session are not the signal — integrating into a target branch is the user's call, the same as the permission mode is.

Run it from the repo root, in this order:

1. Record each session's branch and worktree path from `claude agents --json`. Measure them: a name gives the spelling, not whether the worktree is still there
2. Settle uncommitted changes. A session still running commits its own — `SendMessage` it, since it knows its worktree better than the caller does. For one already stopped, the caller commits in that worktree
3. `claude stop`, then `claude rm`, each session — **before any worktree is removed.** Deleting the cwd under a live session breaks it, and a live session sharing the `.git` fights the merge over `index.lock`
4. Confirm the working copy is clean, resolve the target (`main` by default, confirm anything else), check it out, and verify the current branch before merging
5. `git merge --squash <branch>`, one branch at a time, taking branches whose changes others read first. **Run the suite after each one and stop on red.** Every branch was cut from the same base, so the second knows nothing of the first: same file gives a conflict, different files give a semantic conflict that only the suite catches. On a conflict or a diverged branch, rebase that branch onto the target and redo its squash merge. A branch carrying no commits of its own — a read-only verifier's — has nothing to merge; take it to removal as it is
6. `git worktree remove --force <path>` and `git branch -D <branch>`. `--force` because gitignored `vendor/` and `node_modules/` leave the worktree permanently untracked-dirty, and it is safe only because step 2 settled the tracked changes first. `-D` because a squash-merged branch is not an ancestor of the target, so `-d` refuses it
7. Do not push. Report the commits left on the target

Where `git commit` falls in that loop is the one thing the role shape decides:

- **generator-verifier and orchestrator** — one feature, one commit. Let the squashes accumulate in the index and commit once at the end, after the last suite run
- **team** — one commit per branch, right after each squash. Those tasks were independent by construction, and collapsing them together destroys the unit anyone would revert

Leave `~/.cache/<project>-handoff/` in place. The prompts and status files are what this report rests on; clear them when the user asks.

When the caller is itself inside a worktree, `ExitWorktree(action: "keep")` first, then treat its branch as one more in step 5's order.

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
| Taking a worker's "tests green" or "fixed N cases" at face value                                                          | This is what `supervisor` in step 2 buys: run the suite yourself on each branch. Implementers see the side that worked; what broke and what overreached only surface by classifying the whole diff. A `relay` caller does not repeat the verifier's measurement — it checks that one was actually made                                                                                                                                                                                                  |

## Out of scope

- **Winding the team down unasked.** Step 6 is the caller's to run, and only on the user's word. A full set of completion notices is not that word
- **Pushing the target branch.** Step 6 stops at the commits it leaves locally. Pushing happens on the user's timing, when they ask for it
- **Raising the permission mode on your own.** Launching a session more permissive than the one you are in routes around a decision the user made about your session. `bypassPermissions` is not off limits — it is the user's to grant, which is what the mode column in step 2 exists for. What stays out of scope is picking a mode they have not seen: at launch, on a relaunch, or when nudging a session already stalled at `waiting`

## Worked example

Four fixes in one analyzer: three touched the same file, and one of those three altered a function's return meaning, so everything reading it stayed together. The fourth was independent but sat off the critical path, so splitting it would have bought nothing. `worker-analyzer-fixes` and `verifier-analyzer-fixes`, generator-verifier, the caller a `relay` — and the verifier sent back four items, three of which the reports alone read clean on. Teardown collapsed the worker's branch into one commit; the verifier's had none to collapse.
