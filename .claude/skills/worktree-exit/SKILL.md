---
name: worktree-exit
description: Finish a git worktree - commit what is in it, squash merge it into the target branch, then remove the worktree and delete its branch. Inspects the real state first and runs the irreversible steps only after the user approves the plan. Triggers include "worktree を終了", "worktree 畳んで", "マージして終了", "finish the worktree", "merge and clean up the worktree". Never pushes.
disable-model-invocation: true
---

# Worktree Exit

## Purpose

Collapse a finished worktree into one commit on the target branch and remove what is left behind. One feature becomes one commit; the branch's intermediate commits are not history worth keeping.

The reason this skill inspects before it acts is that the report of what a worktree holds and what it actually holds come apart. Twice on 2026-09-14 they did: a session that reported three items addressed had two of them uncommitted, and another that said it had skipped a measurement had in fact completed it, so tearing the worktree down would have destroyed the only copy of a sample. Both were caught by looking at the files rather than reading the claim. Deleting a worktree and its branch destroys anything not yet merged, and nothing downstream recovers it.

## When it applies

Only in a worktree context: cwd under `.claude/worktrees/`, or an `EnterWorktree` session active in this conversation. Outside that, say so and stop - a bare "done" or "終了" elsewhere means something else.

If the user says "keep", "残して", or similar, skip the merge and the cleanup entirely. Report the retained branch name and path so they can find it later.

## Phase 1 - Inspect

Read-only. Nothing here changes the repository.

Resolve the worktree path, its branch, the main checkout, and the merge target.

```bash
git worktree list
git rev-parse --abbrev-ref HEAD
git rev-parse --path-format=absolute --git-common-dir   # main checkout: this, minus the trailing /.git
git symbolic-ref --quiet --short refs/remotes/origin/HEAD | cut -d/ -f2-
```

The target is usually the repository's default branch, which is not always `main`. The `symbolic-ref` line resolves it, but with `cut` on the end of the pipe it signals failure by printing nothing rather than by exiting non-zero - so treat empty output, not the exit status, as the cue to fall back to whichever of `main` or `master` exists.

The target is not always the default branch, either. A worktree cut from some other branch belongs back on that branch, and which one it was is not mechanically recoverable afterwards. When `<default>..HEAD` holds commits that are not this branch's own work, it was cut from something else: name the target you believe is right in Phase 2 and have the user confirm it before merging.

Then establish what is actually in the worktree and how it sits against the target.

```bash
git status --short --untracked-files=all
git log --oneline <target>..HEAD
git log --oneline HEAD..<target>
```

Read all three. `git status` names what would be lost - untracked files included, which is why `--untracked-files=all` is not optional here. The first log is what the squash commit will contain. The second is whether the target has moved on since the branch started; if it is non-empty the branch has diverged and the merge will need the rebase in Phase 3.

The main checkout's own `git status --short` matters as much as the worktree's, but a harness that isolates a worktree session refuses git commands aimed at the shared checkout, so this one waits until Phase 3 step 3, after leaving the worktree. What Phase 1 can do from here is name the paths the merge will touch, which is what decides whether that later check is fatal.

```bash
git diff --name-only <target> HEAD
```

Uncommitted work in the main checkout belongs to another session. It is a stop condition when it touches any of those paths: the squash merge entangles it, and the conflict recovery below cannot run without destroying it. When the two sets do not intersect, no conflict is reachable, so report the dirty state and carry on. A staged-but-uncommitted file specifically means another session is mid-merge.

When the work was done by another session that was told not to commit, its output is entirely untracked and its own account of it is not evidence. List what is on disk and compare it against what was asked for before going further.

## Phase 2 - Present the plan

Show the inspection result and the intended actions together, in one message, and stop. State the worktree path and branch, the merge target, how many files would be committed and whether any are untracked, how many commits the squash would collapse, and what gets deleted at the end. Call out explicitly when the target is not the default branch, and when the branch has diverged.

Do not run any of Phase 3 until the user approves. After approval it runs through to the end without further prompting. Two things stop it: a merge conflict, and uncommitted work in the target checkout that touches a path this merge writes.

## Phase 3 - Execute

1. Commit the uncommitted changes in the worktree, untracked files included. Do not squash the branch's own commits - step 5 collapses them anyway. Skip this step when the worktree is clean.
2. Get out of the worktree. `ExitWorktree(action: "keep")` does it when this conversation opened the worktree with `EnterWorktree`. When cwd merely sits under `.claude/worktrees/` - a session launched with `--cwd` pointing there - `ExitWorktree` has no session to leave, reports as much, and cwd stays where it was; `cd` to the main checkout resolved in Phase 1 instead.
3. Run `git status --short` in the main checkout - the first point in the procedure where the harness allows it. Intersect what it lists with the paths from Phase 1. Anything in both stops the run; report it and never stash it, since the stash stack is shared and another session may pop it. Anything outside them is another session's unrelated work: say it is there, leave it untouched, and go on.
4. `git checkout <target>`, then confirm two things before touching anything else: that cwd is the main checkout rather than the worktree, and that the branch actually switched. Run from inside the worktree, this either fails outright (`fatal: '<target>' is already used by worktree at ...`) or, worse, succeeds and leaves every remaining step operating on a directory that step 6 is about to delete.
5. `git merge --squash <branch>` then `git commit`. Write the message for the feature as a whole, not as a list of the branch's intermediate commits.
6. `git worktree remove <path>` then `git branch -D <branch>`. Recover the path from `git worktree list` if it was not recorded.
7. Report the resulting commit on the target. Do not push.

On a conflict, or when Phase 1 found the branch diverged, rebase first: go back to the branch, run `git rebase <target>`, resolve the conflicts there, then redo the squash merge from step 4. Resolving inside the squash merge instead puts the resolution in the working tree of the target branch, where a mistake is harder to back out of.

Clear the failed squash before rebasing. `git merge --abort` does not work here - a squash merge never writes `MERGE_HEAD`, so it exits 128 with "There is no merge to abort" and leaves the conflicted files staged as `UU`. `git reset --hard HEAD` would clear it and would also discard every unrelated change in that checkout, so undo only the conflicted paths instead. Capture them before resetting: `git reset` drops the unmerged index entries, and a `--diff-filter=U` run afterwards comes back empty while the conflict markers stay in the files.

```bash
conflicted=$(git diff --name-only --diff-filter=U)
git status --short   # stop and report if anything outside $conflicted is modified
git reset -q
git checkout -- $conflicted
```

If `git worktree remove` refuses, it is reporting that the worktree still holds modifications or untracked files. Look at what they are. Do not reach for `--force` to get past it - that is the same class of loss this skill exists to avoid.

## Notes

- `-D` in step 6 is required, not a shortcut. After a squash merge the branch is not an ancestor of the target, so `-d` refuses with "not fully merged" even though the work is safely in.
- Pushing happens on the user's timing and only when they ask for it. This skill never pushes, including after a clean merge.
- `EnterWorktree` bases a new worktree on `origin/<default-branch>`, so a worktree whose local default branch was ahead started incomplete. That is a problem to catch when the worktree is created, not here - but if Phase 1 shows a large `HEAD..<target>`, mention it, because it usually means the branch was working from a stale base.
