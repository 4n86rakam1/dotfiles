---
name: proofread-en
description: 英語文章を公開前に校正する。文法・語法の誤りと、非ネイティブ特有の不自然な表現を指摘する。「英語を校正して」「proofread this」「この英文をチェック」「英文レビュー」で起動。
---

# Proofread English

## Principles

- Never fix silently. Every correction carries its reason. The point is to stop the writer repeating the mistake, not to tidy the surface.
- Preserve the voice. Keep to light edits and never swap in vocabulary or syntax that is "better" than the writer's own.
- The reader is a B2-level engineer. Rare words, idioms, and elaborate syntax count against the text.
- Where you cannot be certain, offer two candidates and state the difference in nuance.

## 1. Mechanical check

```bash
proofread <path>
```

Runs Vale (Microsoft style / proselint / write-good) and LanguageTool. English is detected from the content, so this works in any repository or directory. Pass `--en` when the detection gets it wrong.

Caught by the tools: spelling, wordiness, passive voice, weasel words, heading capitalization, subject-verb disagreement, a/an, plurals of uncountable nouns.

Missed by the tools: whether an article is needed in context, preposition choice, tense consistency, sentences that do not parse as meaning, and translated-sounding phrasing.

That second list is exactly where non-native errors concentrate, so run every pass below even when the mechanical check reports nothing.

## 2. Grammar pass

Fix errors only, without changing meaning. Cover:

- Subject-verb agreement and tense consistency
- Articles (a / the / zero) and countability (`equipment`, `software`, `research`)
- Preposition choice
- Restrictive vs non-restrictive relative clauses, where the comma changes the meaning
- Number, and pronoun reference

## 3. Copyedit pass

Keep this separate from the grammar pass. Handle what is hard to read rather than wrong.

- Passive to active, except where the agent is not obvious
- Split long sentences
- Weak verbs (`make`, `do`, `get`, `perform`) into specific ones
- Delete filler words (`basically`, `actually`, `just`, `very`)
- Undo nominalizations (`utilization` into `use`)

## 4. Unnaturalness

Point out what is grammatical but does not read as English. This is the highest-value output.

- Translated phrasing, where Japanese word order or framing survives
- Collocation errors (`do a mistake` into `make a mistake`)
- Register mismatch: colloquial in a technical document, or needlessly stiff

## Output format

Separate the passes, and give four things per finding: line number, original text, correction, reason. Close with two or three lines on the error patterns that recurred. Recognizing the pattern helps more next time than any single fix.

## Reference

A non-native writer's account of proofreading with an LLM: <https://vincent.bernat.ch/en/blog/2026-blogging-llm>
