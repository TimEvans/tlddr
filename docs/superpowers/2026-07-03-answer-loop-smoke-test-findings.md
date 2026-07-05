# Answer Loop (D6) — Smoke-Test Findings

**Date:** 2026-07-03
**Branch:** `feat/answer-loop`
**Method:** Ran the interactive `skills/review` session over the Chevron 10-K run's 19 open
verify questions end-to-end — sign-off, `answer-commit`, worklist, re-pass, re-verify,
re-assemble — plus a throwaway blind-regeneration experiment on the glossary section
(isolated scratch, committed report untouched). This is the authoritative consolidation of
what that run surfaced; supersedes the scratch notes in `.superpowers/sdd/`.

**Hardening validated (2026-07-05):** the five fixes below (spec
`2026-07-03-answer-loop-hardening-design.md`, merged) were re-smoke-tested on **Sonnet at
medium effort** (the honest end-user floor — see F8) over two Chevron sections in an
isolated `chevron-retest/` base. Both changed model-facing contracts held, verified against
disk: (1) claim_id-keyed verdicts — 35/35 claims covered, 0 botched/dropped ids, 5
downgrades → 5 correctly-formed new-shape questions; (2) the `draft-amend` re-pass —
full lifecycle `open → revise_pending → revise_applied`, `answers.json`/`amendments.json`
key-spaces not crossed, all 5 edits re-validated through grounding, re-verify converged
(0 new), committed report isolated. On the hardest claim Sonnet reasoned *better* than the
original Opus run (caught the $10B-includes-finance-leases table artifact). Net: the
hardening is sound and the quality is not a big-model artifact. One new ergonomic finding —
see F11 below.

## F11 — Decisions encoded twice in the hardened re-pass (ergonomic)
The hardened flow makes the reviewer express each decision twice: once as `answers.json`
(`{id, disposition, answer}` — audit trail + lifecycle transition) and once as
`amendments.json` (`{claim_id, set_text/add_pages/...}` — the mechanical edit). Functionally
correct and each has a distinct job, but redundant to author. Pre-hardening, the
`answers.json` guidance *was* the re-pass instruction (fed a full re-draft); now the precise
`amendments.json` carries the edit and the guidance is only recorded. *Fix (with the
entry-point-friction item in next-steps.md):* let the review wrapper derive the `answers.json`
disposition/lifecycle record from the same signed-off edit that produces the amendment, so
the reviewer specifies the fix once. Non-blocking.

---

## Top-line result

**The answer loop's plumbing is sound and proven on real data. Its re-pass *execution
model* is wrong.** The loop converged end-to-end (19/19 resolved, 0 open, independent
re-verify cleared all 15 edited claims, 547→547 claims, all commits through the validated
`draft-commit` seam, 4 accepts rendered as disclosed caveats, no cycle warning). But that
clean result depended on the agent executing the re-pass **surgically** (patch only the
changed claims). The **designed** re-pass — full-section regeneration via `skills/draft`,
which the spec and skill prescribe — was shown by experiment to be actively harmful. So
"the loop works" is contingent on doing the re-pass a way the current design does *not*
prescribe.

### What was proven to work (do not lose these)
- Ingestion/validation (`answer-commit`): unknown ids + invalid dispositions reported and
  dropped; machine-trust held at the seam.
- Routing + deduped worklist: 15 revises across 9 sections, two-question sections collapsed
  correctly.
- Grounding guardrail through a surgical re-pass: every new citation validated to resolve
  to a real page via `draft-commit`; `source_confidence` re-derived (model's value ignored).
- Assemble: corrected prose in `report.md`, accepted findings as disclosed caveats in
  `report_comments.md`.
- The review *method* the session converged on is genuinely good and caught real defects:
  three C-lite judge false-positives, a fabricated "$10 billion", and two directional
  inversions — none of which a rubber-stamp review would have caught.

---

## Findings

### Must-fix before this ships (the re-pass model)

**F9 / F3 — Re-pass mechanism: surgical patch is correct; full-section regeneration is harmful.**
The skill's re-pass mode implies re-running `skills/draft` (full regeneration). The blind-
regen experiment on the glossary (to change 2 of 53 claims) churned 53→58 claims — only
7/53 byte-identical, 46/53 reworded/split/merged/reordered. No factual mangling in the
sampled claims, but the audit trail is destroyed: you cannot diff a "fix" that rewrote 46
of 53 lines. The agent's improvised surgical patch (edit only the changed claims, commit
through `draft-commit`) changed exactly the 2 intended claims, 0 churn, and preserved
grounding.
*Fix:* make surgical claim-level editing the sanctioned re-pass mechanism. Add a validated
CLI command (e.g. `draft-amend --claim <id> --add-page N` / `--set-text ...`) that routes
through the same validation, so the model isn't hand-writing throwaway Python to mutate the
store. Rewrite the skill's re-pass mode to prescribe surgical, not full re-draft.

**F10 — `verify-{index}` question ids collide across re-passes (data-integrity bug).**
`ingest_verdicts` mints `id=f"verify-{index}"` from claim position, but `draft-commit`
reorders claims on section re-commit (append semantics), so indices shift. The experiment
produced two different questions sharing id `verify-527`. Since `answer-commit` resolves BY
id, duplicate ids make resolution ambiguous — silent store corruption on a second round.
*Fix:* stable/unique ids independent of claim ordering (hash of raised_by + section +
durable claim id, or a persisted monotonic counter).

**F5 — Resolved-question dedup is brittle to the point of near-non-functional.**
`question_identity` = `(raised_by, target, normalize(question_text))`, and the question
text embeds both `claim.text[:80]` and the judge's free-text `note`. The experiment
reopened both blind-regenerated accepts: 523 because its claim was reworded (text differs),
and — the clean proof — 527 despite a **byte-identical claim**, purely because the judge's
note differed. Either axis drifting defeats suppression, and the note essentially never
reproduces, so in practice suppression almost never fires across a real re-verify.
*Testing gap:* the Task-5 dedup tests used identical question text, so suppression "worked"
in test and masked that it cannot work in the field.
*Fix:* key identity on a stable concern id (not claim snippet + free-text note); add a test
that varies the note/claim wording as reality does.

**F6 — No "revise-pending" vs "revise-done" state; an unexecuted revise silently drops.**
`answer-commit` marks every answered question `resolved=true` and fire-and-forgets the
worklist. A committed revise whose section is never re-passed shows under `_triage.md`
Resolved but appears in neither the report's open-questions nor its caveats — the prose
stays uncorrected while tracking says "resolved."
*Fix:* track revise lifecycle (clear when the section's re-pass commits); `assemble` warns
on resolved-revise questions with no post-answer re-pass.

### Should-fix (skill / review quality)

**F2 — The C-lite judge is a good smoke detector but a poor diagnostician.**
It flagged the right claims for wrong/shallow reasons — 3 false positives where the source
supported the claim verbatim on an *uncited adjacent page* (the judge never looked past the
cited page's row labels).
*Fix:* the review skill must instruct the reviewer to *verify the flagged claim against its
cited source before proposing* — treat the judge's note as a pointer, not a verdict.

**F8 — The skill under-specifies the reviewer's real job.**
`review/SKILL.md` only says "link the docs and propose your best answer." All the run's
best behaviour (source verification, arithmetic decomposition, sign-checking, distrusting
the judge) was emergent from a diligent agent, not guaranteed by the skill text. A weaker
model would relay the judge's question and get rubber-stamped.
*Fix:* encode the expected review depth explicitly (see F2, F4). *Caveat on this run's
signal:* the "smoke test" frame leaked to the agent at Q18 (eval-awareness); the observed
depth may partly reflect a strong model. Re-run the skill cold on a weaker model for the
true floor.

**F4 — Encode the disposition axis the review actually converged on.**
Not "nit vs error" and not "is it locatable" — the operative test is **"does leaving it in
mislead a reader?"** Reader-harm (falsehood / fabrication / contradicted causation) →
revise now. Citation-fidelity only, statement true → accept + disclose, or re-cite if the
source is trivially locatable.
*Fix:* put this axis in the skill's guidance; consider noting it in the spec's D-decisions.

**F7 — CLI invocation friction.**
The agent burned several tool calls on `tlddr: command not found` before finding
`.venv/bin/tlddr`. The skill's examples use a bare `tlddr ...`.
*Fix:* show the working invocation (`.venv/bin/tlddr` or `.venv/bin/python -m tlddr.cli`) or
a "activate the venv first" prerequisite in every SKILL.md that shows a `tlddr` command.

### Broader (beyond this branch)

**F1 — Drafter under-citation / compound claims (draft stage).**
~5–6 of the 19 questions were not errors — the drafter cited one page of a fact spanning
two, or bundled several facts (living on different pages) into one compound claim with a
single citation. This is *upstream* noise that inflated the reviewer's load.
*Fix (draft stage):* hold the drafter to atomic claims (design D3 already intends this)
and/or "cite every page a claim leans on." Reduces review load at the source.

**F8b — Strengthen the verify stage.**
The review had to re-verify against source because the judge was unreliable (F2). In a
cleaner design, review is *adjudication of trustworthy flags*, not *re-verification of
untrustworthy ones*. This is the case for the deferred C-full NLI-ensemble verifier.

---

## Recommended sequence before merge
1. F10 (stable ids) and F5 (dedup key + test) — correctness; small, self-contained.
2. F9/F3 (surgical `draft-amend` command + skill re-pass rewrite) — the design correction.
3. F6 (revise lifecycle + assemble warning).
4. F2 + F4 + F8 + F7 (skill guidance + docs).
5. F1, F8b — separate follow-up work, out of this branch's scope.

Items 1–4 are branch-scoped and should land before `feat/answer-loop` merges; the loop's
plumbing is proven, but shipping the prescribed full-regen re-pass would be shipping the
harmful path.
