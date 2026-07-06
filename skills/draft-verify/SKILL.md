---
name: draft-verify
description: Use when running the independent verification pass (C-lite judge) over committed draft claims to surface contradictions and support downgrades before report assembly.
---

# draft-verify

## Overview

An independent judge pass that re-reads the source evidence and assesses each committed claim without reusing the drafting agent's reasoning. Disagreements (support downgrades and contradictions) are raised as `verify` questions for human review. Run this after all sections are drafted and committed, and before assembling the final report.

## Deterministic/Agent Boundary

- **Agent supplies:** verdicts — `{claim_id, support_level, contradiction, note}` for each claim, referencing the claim's `id` from `claims.json`.
- **CLI ingests and raises questions:** only disagreements produce questions. Agreements are silent. All questions are tagged `raised_by=verify` and surface in `report_comments.md` after assembly.
- **Fresh context required:** do not carry over any reasoning, notes, or intermediate conclusions from the drafting pass. The value of this pass is independence.

## Output location

All paths below are relative to the run's output base, `$TLDDR_OUTPUT` (default
the current directory when unset). Set it once at the start of the run so every `tlddr`
command and file reference resolves under the same directory:

    export TLDDR_OUTPUT=<your-output-dir>   # e.g. output/Chevron-10K

Work artifacts live under `$TLDDR_OUTPUT/.tlddr/`, the rendered vault under
`$TLDDR_OUTPUT/vault/`, and the report under `$TLDDR_OUTPUT/report/`.

## Prerequisites

Before starting:

1. **Committed claims store** — `$TLDDR_OUTPUT/.tlddr/claims.json` must exist and be non-empty. If missing, run the `draft` skill first.
2. **Extracted store** — `$TLDDR_OUTPUT/.tlddr/extracted/*.json` must exist.

## Procedure

### 1. Load the committed claims

Read `$TLDDR_OUTPUT/.tlddr/claims.json`. The array is the authoritative list of committed claims. Note each claim's `id` — your verdict array must reference every claim by its `id`; order does not matter.

Each claim record contains: `id`, `section_id`, `text`, `support_level` (the drafter's assessment), `evidence_relation`, and `sources` (a list of `{node_id, page}` pairs).

### 2. Verify each claim

For each claim:

#### 2a. Read the cited page(s)

```
tlddr draft-read --output "$TLDDR_OUTPUT" --id <node_id> --pages <p>
```

Request only the pages cited by the claim (the `sources` array). If a claim cites multiple nodes or multiple pages on the same node, read each page separately. Do not read pages that are not cited — the judge's scope is the cited evidence only.

#### 2b. Judge independently

Read the page text and ask: does this page, taken alone, support the claim's `text`?

- Assign `support_level`: `fully_supported`, `partially_supported`, or `unsupported`.
- Set `contradiction: true` if the cited page directly contradicts the claim — the source states the opposite of what the claim asserts.
- Write a `note` (one clear sentence) for any downgrade or contradiction, explaining what the source actually says. Leave `note` empty for agreements.
- If a page is unclear, ambiguous, or unreadable, record `partially_supported` and note why.

Do not reference any information beyond the pages you have read for that specific claim.

### 3. Emit verdicts JSON

Write the complete verdicts array to a temporary file (e.g. `$TLDDR_OUTPUT/.tlddr/verdicts.json`). The array must contain one entry per claim, each keyed on that claim's `id`:

```json
[
  {"claim_id": "claim-3f2a91bc", "support_level": "fully_supported", "contradiction": false, "note": ""},
  {"claim_id": "claim-8ad4102e", "support_level": "partially_supported", "contradiction": false, "note": "Source mentions the figure only in passing; the claim overstates certainty."},
  {"claim_id": "claim-01c7f5da", "support_level": "unsupported", "contradiction": true, "note": "Source states the value is 12%, not 8% as claimed."}
]
```

Every claim's `id` from `claims.json` must appear. An omitted id leaves that claim unreviewed — the CLI will not catch the gap. A verdict whose `claim_id` does not match any committed claim, or whose `support_level` is not a valid value, is silently skipped — double-check ids against `claims.json`.

### 4. Commit the verdicts

```
tlddr draft-verify-commit \
  --verdicts "$TLDDR_OUTPUT/.tlddr/verdicts.json" \
  --output "$TLDDR_OUTPUT"
```

The CLI looks up each verdict's claim by `claim_id` and compares the judged `support_level` against the drafter's recorded level. A downgrade (judge's level is lower than the drafter's) or a `contradiction: true` raises a question whose id is `verify-{claim_id}-{reason}` (`reason` is `downgrade` or `contradiction`); that id is the dedup key, so re-verifying after a re-pass does not re-raise a question already answered. Agreements produce no output. The command prints how many questions were raised.

### 5. Review the outcome

Check how many questions were raised. If the count is high relative to the total number of claims, consider looping back to the `draft` skill to re-read evidence and re-draft the contested sections before assembling.

Run the groundedness readout to see the current overall picture:

```
tlddr draft-eval --output "$TLDDR_OUTPUT"
```

## Proving Gate

Honor the run's **interaction style** (read it via `tlddr status` or `tlddr.toml`). This gate
is **blocking** if the judge raised any contradiction (as opposed to a mere support
downgrade).

- **`guided`, or a blocking gate under any style:** stop and present the raised question
  count to the Reviewer, who decides:
  - Accept the raised questions as acknowledged findings (they appear in `report_comments.md`).
  - Return to the `draft` skill and re-draft specific sections where the judge disagreed.

  Do not proceed to assembly (`tlddr assemble`) until the Reviewer has made that call.

- **`autonomous`, non-blocking:** do not stop. The verify questions are recorded and will
  surface in the end-of-run review queue; continue to assembly.
