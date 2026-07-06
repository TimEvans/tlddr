---
name: understand
description: Use when driving the tlddr Understand stage over an extracted corpus to produce a linked, triaged vault — section tags, agent-proposed edges, and a coverage triage layer.
---

# understand

## Overview

Per-run procedure for the Understand stage of tl-ddr. The host agent supplies comprehension (description, section tags, confidence, questions, edges); the deterministic `tlddr` CLI validates and renders. The vault produced is a linked, triaged Obsidian-style collection keyed to the user's curated section structure.

## Deterministic/Agent Boundary

The CLI is the only thing that writes authoritative output:

- **Agent supplies:** `description`, `report_sections`, `confidence_interpretation`, `questions`, and (in Phase 2) `related` edges.
- **CLI validates and drops:** section tags whose id is not in `sections.json`, edge targets that are not known node ids, and self-links. Triage is machine-derived — never hand-set.
- **Corollary:** if a section tag or edge target is silently absent from the rendered vault, the CLI dropped it. Check ids.

## Output location

All paths below are relative to the run's output base, `$TLDDR_OUTPUT` (default
the current directory when unset). Set it once at the start of the run so every `tlddr`
command and file reference resolves under the same directory:

    export TLDDR_OUTPUT=<your-output-dir>   # e.g. output/Chevron-10K

Work artifacts live under `$TLDDR_OUTPUT/.tlddr/`, the rendered vault under
`$TLDDR_OUTPUT/vault/`, and the report under `$TLDDR_OUTPUT/report/`.

## Prerequisites

Before starting any phase:

1. **Extracted store** — `$TLDDR_OUTPUT/.tlddr/extracted/*.json` must exist. If missing, run:
   ```
   tlddr extract --source <source-dir> --output "$TLDDR_OUTPUT"
   ```

2. **Curated sections** — `$TLDDR_OUTPUT/.tlddr/sections.json` must exist. If missing, run the `generate-sections` skill to build it.

3. **Load and verify the section structure** — run once to confirm ids and hierarchy are clean:
   ```
   tlddr sections --sections "$TLDDR_OUTPUT/.tlddr/sections.json"
   ```
   The command prints each section and exits 0. Fix any reported errors before proceeding.

## Phase 1 — Comprehend (per document)

For each document id in `$TLDDR_OUTPUT/.tlddr/extracted/`:

### 1. Read the slice

```
tlddr understand-slice --output "$TLDDR_OUTPUT" --id <id>
```

This prints a bounded slice of the extracted document (title, structure markers, capped content sample). Read it fully.

### 2. Write the enrichment file

Write `$TLDDR_OUTPUT/.tlddr/enrichment/<id>.json` with exactly these fields:

```json
{
  "extracted_id": "<id>",
  "doc_type": "<signal type, e.g. born_digital_report>",
  "description": "<readable paragraph summarising content, purpose, and key claims>",
  "report_sections": ["<section-id>", "<section-id>"],
  "confidence_interpretation": "high|medium|low",
  "questions": [
    {"id": "q-0001", "question": "<question text>", "blocking": true}
  ],
  "related": []
}
```

Field rules:
- `report_sections` — best-fit section ids from the loaded sections. Multiple allowed. Use `[]` if no section fits.
- `confidence_interpretation` — self-report: `high` if the document is coherent and fully legible; `medium` if partial; `low` if large gaps or unreadable sections.
- `questions` — quarantine items. `blocking: true` for anything that invalidates interpretation; `blocking: false` for clarifications. Ids in `q-NNNN` format. Omit the list (`[]`) if nothing is unclear.
- `related` — leave as `[]` for now. Edges are added in Phase 2.

Do not propose edges in this phase. Process all documents before moving to Phase 2.

## Phase 2 — Relate (holistic, once)

Read every `$TLDDR_OUTPUT/.tlddr/enrichment/*.json` to build a complete picture of the corpus — all ids, all descriptions.

Propose typed edges across the whole corpus. For each enrichment file, add or update the `related` list:

```json
"related": [
  {"target": "<other-id>", "relation": "corroborates", "rationale": "<one sentence>"},
  {"target": "<other-id>", "relation": "supersedes", "rationale": "<one sentence>"}
]
```

Allowed `relation` values: `contradicts`, `supersedes`, `corroborates`, `references`, `same_subject`, `input_to`.

Constraints:
- Only link to ids that exist in the corpus (the CLI will drop unknown targets).
- No self-links.
- Rationale must be a single, specific sentence.

## Phase 3 — Commit and Render

### Commit each enrichment file

For each `$TLDDR_OUTPUT/.tlddr/enrichment/<id>.json`:

```
tlddr understand-commit \
  --enrichment "$TLDDR_OUTPUT/.tlddr/enrichment/<id>.json" \
  --output "$TLDDR_OUTPUT"
```

This validates the enrichment, validates edges, computes extraction confidence, derives triage, and writes the node record. The command is idempotent — re-running overwrites the previous node cleanly.

### Render the vault

Once all commits are done, render once:

```
tlddr understand-render \
  --output "$TLDDR_OUTPUT"
```

This writes `$TLDDR_OUTPUT/vault/<id>.md` (one per node), `$TLDDR_OUTPUT/vault/_index.md` (summary table), and `$TLDDR_OUTPUT/vault/_triage.md` (nodes grouped Red/Amber/Green with open questions).

## Phase 4 — Coverage

Add the vault to TurboVault (MCP) so it can be explored as a linked graph:

1. Register `$TLDDR_OUTPUT/vault/` as a TurboVault vault.
2. Run graph-level explorations: isolated nodes, thin clusters, hub notes.
3. Write findings into `$TLDDR_OUTPUT/vault/_triage.md` as a coverage layer **appended beneath the deterministic backbone** — do not overwrite or reorder the rendered sections.

Coverage observations to include:
- Documents the automated triage missed or under-scored (isolated but substantive).
- Clusters that appear disconnected but share subject matter.
- Hubs that may need manual splitting.
- Any gaps in section coverage (sections with no assigned documents).

## Proving Gate

Honor the run's **interaction style** (read it via `tlddr status` or `tlddr.toml`). This gate
is **blocking** if any node is RED in triage (a blocking open question, or LOW confidence).

- **`guided`, or a blocking gate under any style:** stop and get the Reviewer's explicit
  sign-off before proceeding. Ask them to open `$TLDDR_OUTPUT/vault/` and
  `$TLDDR_OUTPUT/vault/_triage.md` and confirm:
  - The section index looks like a trustworthy map of the corpus.
  - Triage colours match their reading of the documents.
  - Open questions are actionable.
  - Coverage observations are useful.

  Do not proceed to any downstream stage until the Reviewer approves.

- **`autonomous`, non-blocking:** do not stop. The triage summary and open questions are
  already recorded in `_triage.md` and will surface in the end-of-run review queue; continue
  to the next stage.

## Re-pass mode (answer loop)

When re-understanding a node named in a `worklist.json` entry, read that entry's
`guidance` field and treat it as Reviewer instruction — a signed-off answer to an
earlier question about this document. Re-comprehend with it in context, then
`understand-commit`. If your re-tagging changes the node's `report_sections`, note the
affected sections so the Reviewer can decide whether to re-draft them; do not assume it.
