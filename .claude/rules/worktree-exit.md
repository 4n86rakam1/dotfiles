# Worktree Exit

When the user signals worktree completion — in any language (e.g. "exit", "終了", "merge", "マージして") — apply this default. Only fire when in a worktree context (CWD under `.claude/worktrees/` or an active EnterWorktree session); ignore a bare "done" outside that context.

1. Record the worktree path and branch name for later cleanup.
2. If the worktree has uncommitted changes, commit them. Skip if clean. Do NOT squash the branch's own commits — the squash merge in step 6 collapses them anyway.
3. `ExitWorktree(action: "keep")` to return to the original directory.
4. Resolve the merge target — default `main`, otherwise the worktree's base ref. Confirm if it is not `main`.
5. `git checkout <target>` and verify the current branch before merging.
6. Squash merge into the target:
   - `git merge --squash <branch>` then `git commit` — one feature = one commit on the target.
   - If the merge stops on conflicts, or the branch has diverged from the target, rebase the branch onto the target first (`git rebase <target>` from the worktree/branch), resolve the conflicts there, then redo the squash merge.
   - Write the commit message for the feature as a whole, not as a list of the branch's intermediate commits.
7. `git worktree remove <path>` and `git branch -D <branch>`. `-D` is required: after a squash merge the branch is not an ancestor of the target, so `-d` refuses with "not fully merged". Use `git worktree list` if the path is not remembered.
8. Do not push. Pushing happens on the user's timing, only when they explicitly ask. Report the resulting commit on the target instead.

Exceptions:

- Skip merge and cleanup if the user says "keep", "残して", or similar. Report the retained branch name.
