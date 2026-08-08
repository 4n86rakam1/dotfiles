# Review Hygiene

Apply the rules below before starting a code review, plan review, or meta-review. Apply them actively in recursive meta-reviews especially: novelty drops with every added layer, which invites padding the count, adding unverified phantom problems, and performative self-criticism.

- Verifiability gate: before writing a finding, confirm you can show evidence it occurs, via grep, Read, or real data. If you cannot, label it an unverified concern or leave it out. Never turn a guess about a tool's internals or spec into a finding.
- Severity threshold: define the minimum real cost up front, for example "30 minutes of rework after implementation". Drop anything below it in plan reviews and meta-reviews. Keep it in code reviews, tagged with severity and confidence and moved to the end, because losing a real bug costs more. Resist pressure to inflate the count either way.
- Recursion stop condition: stop a meta-review once novelty falls below the previous layer. Posturing as a harsher self-critic is performative humility and does not serve the user's goal.
- State the purpose: write one line on what decision this review informs before starting. If you cannot write it, do not start the review.
- Verify the actions: a meta-review covers not only the previous layer's findings but whether the actions taken on them, such as fix commits, were sound. Skipping this breaks the feedback loop between review and execution.
