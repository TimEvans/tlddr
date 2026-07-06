---
name: review
description: Use when a Reviewer works the open question queue after a draft/verify run — an interactive, one-question-at-a-time session that ingests signed-off answers and drives the scoped re-passes.
---

# review

## Overview

The interactive review session for the answer loop. The Reviewer works the open
question queue one question at a time; each signed-off decision is committed via
`tlddr answer-commit`, which routes it to a re-pass. Generation never blocked on
the Reviewer — this session runs whenever they are ready, and is resumable.

## Deterministic/Agent Boundary

- **Agent (this session) supplies:** for each signed-off question, an answer record
  `{id, disposition, answer}` where `disposition` is `revise` (re-draft/re-understand
  with this answer as guidance) or `accept` (acknowledge as a disclosed caveat).
- **CLI validates and acts:** `answer-commit` validates each id against the question
  store and the disposition against `{revise, accept}`, sets the answer and the
  question's `status` (`accepted` for `accept`, `revise_pending` for `revise`), and
  writes the deduped re-pass worklist. Unknown ids, and records with an invalid
  disposition, are reported and dropped.
- **Grounding guardrail:** an answer is guidance, never evidence. A re-draft still
  cites real `(node_id, page)` sources; the answer cannot become a citation.

## Output location

All paths are relative to the run's output base, `$TLDDR_OUTPUT` (default the current directory).

    export TLDDR_OUTPUT=<your-output-dir>

## Prerequisites

- `$TLDDR_OUTPUT/.tlddr/questions.json` exists with open (unresolved) questions.
- `$TLDDR_OUTPUT/.tlddr/sections.json`, `nodes/`, and `extracted/` exist (a completed
  draft/verify run).

## Procedure

### 1. Load the open queue

Read `$TLDDR_OUTPUT/.tlddr/questions.json`. Work only the questions whose `status` is
`open`. Order them blocking-first, then by section. Tell the Reviewer how many
open questions there are.

### 2. Present ONE question at a time

Do not batch. For each open question:

1. **State the question** clearly and plainly.
2. **Link the pertinent documents** for retrieval: the `[[node_id]]` of the source(s)
   and, for a `verify` question, the cited pages of the claim under review (look them
   up in `.tlddr/claims.json`). The Reviewer may need to open these before deciding.
3. **Offer a probable answer.** Say what you think the answer most likely is and why,
   grounded in the cited pages. Where the question genuinely admits more than one
   reading, present the **ranked interpretations** as options (best first), the way
   the brainstorming skill presents solution options.
4. **Discuss.** The Reviewer may push back, ask for more context, or check the docs.
   This conversation is NOT persisted — only the final decision is.

### 3. Sign-off (one deliberate decision)

When the Reviewer agrees, present the decision back as a single quoted, italicised
line and its disposition, for explicit approval, e.g.:

> _revise: the causal link to the Hess acquisition is correct — keep the sentence but
> re-cite it to p.47, which states it directly._

Only on the Reviewer's explicit nod does this become an answer record. Never commit an
answer that was not signed off.

### 4. Commit the batch

Accumulate the signed-off records into an answers file and commit them:

```
tlddr answer-commit --answers <answers.json> --output "$TLDDR_OUTPUT"
```

(Or, if the Reviewer filled `> answer:` slots in `_triage.md` directly with leading
`[revise]`/`[accept]` tags, commit those instead:
`tlddr answer-commit --triage "$TLDDR_OUTPUT/vault/_triage.md" --output "$TLDDR_OUTPUT"`.)

Read the printed RE-PASS WORKLIST.

### 5. Walk the worklist

For each **section** entry (re-pass): treat the entry's `guidance` as Reviewer
instruction for the specific claims the question named — **do not regenerate the whole
section**; a full re-draft churns claims the Reviewer never questioned and reopens
findings already accepted. Look up those claims' `id`s in `$TLDDR_OUTPUT/.tlddr/claims.json`,
author an `amendments.json` record per claim (`{claim_id, set_text?, add_pages?,
set_support?, set_evidence?}`), and apply it:

```
.venv/bin/tlddr draft-amend --amendments <amendments.json> --output "$TLDDR_OUTPUT"
```

Amend only the claims the guidance names, then re-run `draft-verify` for that section.
Already-resolved questions will be suppressed on re-ingest; only genuinely new problems
surface.

For each **node** entry (re-understand): re-run the `understand` skill for that node
with the guidance in context, then `understand-commit`. If the node's section tags
change, the affected sections are candidates for a follow-up re-draft — surface them to
the Reviewer; do not re-draft them automatically.

### 6. Re-assemble and check convergence

```
tlddr assemble --output "$TLDDR_OUTPUT"
```

The loop has converged for a section when its re-verify raises zero new questions. If
`assemble` warns that a target has cycled 3+ times, stop and raise it with the
Reviewer rather than looping again.
