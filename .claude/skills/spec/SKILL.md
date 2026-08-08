---
name: spec
description: Create a design spec for a feature or change. Measure the repository to gather context, run the grilling skill to pin down requirements, then write a spec file that matches the project's existing design-doc pattern. Trigger phrases include "/spec", "仕様書作って", "設計まとめて", "write a design spec".
disable-model-invocation: true
---

# /spec

## Purpose

Combine "grilling → spec write" into one command. Enforce the spec structure used in the user's existing `plans/*_design.md`. PLAN.md generation and implementer subagent dispatch are out of scope — delegate those to `superpowers:writing-plans` or manual subagent dispatch.

## Arguments

`/spec [one-line feature description]`

- With an argument: use it as the target feature and proceed to Step 2.
- Without an argument: ask the user "What should I spec, in one line?" and use the response as the target feature.

## Steps

### Step 1: Detect repo and output path

- Run `git rev-parse --show-toplevel 2>/dev/null` to get the repo root.
- If no repo root, use `pwd` as the working directory and fall back to `docs/spec/<slug>.md` here (create the directory if needed).
- Directory selection (first match wins):
  - Under `~/Documents/logbook` → `plans/`
  - `SPEC.md` exists at the repo root → target `SPEC.md` directly (skip filename derivation, Step 4 handles collision)
  - `docs/specs/` (plural) exists → `docs/specs/`
  - `docs/spec/` (singular) exists → `docs/spec/`
  - Otherwise → `docs/spec/` (create)
- Filename convention: sample the newest `.md` file in the chosen directory (`ls -t <dir>/*.md 2>/dev/null | head -1`) and match its stem against these patterns in order:
  - `^\d{4}-\d{2}-\d{2}-.*-design$` → `<today>-<slug>-design.md` where `<today>` is `date +%Y-%m-%d`
  - `^\d{4}-\d{2}-\d{2}-.*$` → `<today>-<slug>.md`
  - `.*_design$` → `<slug>_design.md` (the logbook convention)
  - No sample or unrecognized → `<slug>.md`
- Derive `<slug>` as kebab-case from the target feature. Translate Japanese to concise English. Heuristic when multiple phrasings are viable: prefer the outcome/artifact noun over the action verb. Example: 「verify.sh drift 検出昇格」→ `drift-recovery` (the outcome) over `verify-drift-detection-promotion` (the action). Cap at 4 words. If uncertain, show 2-3 candidates to the user and pick.

### Step 2: Measure the repo

Run these in parallel Bash and feed the results to grilling as evidence.

- `git ls-files | wc -l` — file count
- `git ls-files | grep -oE '\.[^./]+$' | sort | uniq -c | sort -rn | head -5` — top extensions (files without extensions are excluded)
- Read the repo root's `README*`, `CONTRIBUTING*`, `CLAUDE.md`, `CLAUDE.local.md`.
- Run `git grep -F -l -i -- "<noun>"` for each noun in the target feature to list related files (cap at 20). `-F` prevents regex interpretation of user-supplied strings.

Assemble the results as a "measurement summary". If it grows too long, list file names only and Read contents on demand.

### Step 3: Invoke grilling

Invoke `Skill(skill: "grilling")`. The user's global CLAUDE.md rule allows this: `/spec`-invoked grilling counts as an explicit request.

Pass to grilling:

- The target feature from Step 1
- The measurement summary from Step 2
- The intended output path (as context that a spec file will be written)

From grilling's output, separate "decisions" from "open questions".

### Step 4: Overwrite check

If the target file already exists, present to the user before writing:

- The existing file path
- The existing heading list
- Choices: (a) overwrite, (b) new slug, (c) abort. If the target is an existing `SPEC.md`, also offer (a') append as a new section.

If the file does not exist, proceed to Step 5.

### Step 5: Write the spec file

Fill the required sections below. Follow the user's existing `plans/*_design.md` for tone and format.

```text
# <feature name>

## 目的
<1-2 paragraphs. What this is for. Success condition.>

## 背景
<Current state, constraints, related existing assets. Quote the measurement summary as needed.>

## 決定事項
<Bulleted decisions from grilling. Add a 1-2 sentence reason for each.>

## 構成
<Module split, file layout, responsibility. No diagrams — bullets only.>

## 未決事項
<Open questions from grilling. Judgment calls left for implementation.>
```

Follow `~/.claude/rules/code-style-md.md`:

- No tables (use bullets)
- 常体 (だ・である) — no です・ます
- Half-width parens `()` only, never full-width `（）`
- Fenced code blocks require a language tag
- Half-width space around Latin words inside Japanese sentences

### Step 6: Report placement

After writing, report to the user only:

- The output path
- Generated heading list (`grep '^##' <path>`)
- Count of open questions

Do not reprint the body — the user will Read the file directly.

## Edge cases

- **cwd not under git**: Step 1 already falls back to `docs/spec/<slug>.md`. Derive `<slug>` from cwd basename.
- **Feature overlaps an existing spec**: If Step 2's grep surfaces an existing spec, raise the Step 4 overwrite check up-front instead of waiting.
- **Empty repo (`git ls-files` returns 0)**: Skip Step 2's measurement. Grilling proceeds with user-supplied context only.
- **Grilling already active in the session**: `/spec` is designed as a fresh entry point. Do not stack a second grilling on top; ask the user whether to abort `/spec` or wait for the current grilling to finish.

## Out of scope (yagni)

- Generating PLAN.md — hand off to `superpowers:writing-plans`
- Dispatching implementer subagents — hand off to `superpowers:subagent-driven-development` or do it manually
- git commit — leave to `pr-creation.md` and the user's manual flow
- Spec self-review — do not enforce inside this skill. Run `crit` or `/code-review` separately if needed.

## Boundary with existing skills

- `superpowers:brainstorming`: A broad design skill including decomposition and approach selection for greenfield projects. `/spec` is narrower — grilling-centric, tailored to the user's measurement + spec-file workflow. Use `/spec` when conventions and existing assets are clear; use `brainstorming` when starting from a blank slate. The two coexist.
- `grilling`: Called from inside `/spec`. Still usable standalone.
- `superpowers:writing-plans`: Called after `/spec` when converting the spec into a PLAN.md.
