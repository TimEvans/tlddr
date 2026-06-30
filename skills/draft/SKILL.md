---
name: draft
description: Use when driving the tlddr Draft stage over a committed vault — produces a grounded, attributed report draft from the node corpus and section structure.
---

# draft

## Overview

Per-run procedure for the Draft stage of tl-ddr. The host agent drafts each section by reading evidence pages and emitting grounded claims; the deterministic `tlddr` CLI validates, persists, and surfaces findings. The output is a grounded claims store that assembles into an attributed report.

## Deterministic/Agent Boundary

The CLI owns persistence and quality gates:

- **Agent supplies:** claim text, `support_level`, `evidence_relation`, and `sources` (node_id + page pairs it actually read).
- **CLI validates and drops:** unresolvable citations (unknown node_id or page not in the doc's page index), and turns zero-citation claims into findings. Claims tagged to a section id that does not exist in `sections.json` are also dropped with a finding (mirroring how Understand drops unknown section tags).
- **Corollary:** if a claim is silently absent from the committed store, the CLI dropped it — either the node_id does not exist, the page is not in the extracted record, or the section_id is not a known section. Check ids, page numbers, and section ids.

## Prerequisites

Before starting any section:

1. **Committed vault** — `.tlddr/nodes/*.json` must exist. If missing, run the `understand` skill first.
2. **Curated sections** — `.tlddr/sections.json` must exist. If missing, run the `generate-sections` skill.
3. **Extracted store** — `.tlddr/extracted/*.json` must exist (the canonical content store).

## Phase 1 — Identify evidence per section

For each section in `sections.json`:

1. Find all node files whose `report_sections` array contains this section's id. Scan `.tlddr/nodes/*.json` and collect every node where `report_sections` includes the section id.

2. If no nodes are tagged for a section, the CLI will emit a no-evidence finding for any claim submitted for that section. Skip drafting for sections with zero tagged nodes — they will be called out in the groundedness readout.

## Phase 2 — Read evidence (per section)

For each node tagged to the current section:

### 2a. Attempt whole-doc read

```
tlddr draft-read --extracted .tlddr/extracted --id <node_id>
```

- If the document is short enough (under the internal threshold), the entire content is returned. Read it fully and proceed to Phase 3.
- If the document is large, the CLI returns an overview listing each page number with its character count and a short leading snippet.

### 2b. Request specific pages (large documents only)

From the overview, identify which pages are relevant to this section, then fetch them:

```
tlddr draft-read --extracted .tlddr/extracted --id <node_id> --pages 1,4,7
```

The response contains only the requested pages. Re-call with a different page list if more content is needed. Only cite pages you have actually read — citations to pages you have not fetched will be dropped at commit time.

## Phase 3 — Draft the section

Draft each section against its `guidance` field from `sections.json` (if non-null) plus this fixed grounding preamble:

- Ground every claim exclusively in the evidence you have read. Do not introduce outside knowledge.
- Cite every claim with `(node_id, page)`. If a fact appears on multiple pages or nodes, cite all.
- Mark each claim `quoted` (close paraphrase or direct extract from the source) or `inferred` (logical conclusion drawn from source material).
- Assess each claim's support level: `fully_supported` (the cited source unambiguously backs the claim), `partially_supported` (the source partially backs it or the connection requires inference), or `unsupported` (you cannot link the claim to the cited source).
- If `guidance` is null or thin, fall back to a default structure: leading summary finding, supporting evidence points, caveats or limitations.
- Draft one section at a time and commit before moving to the next.

## Phase 4 — Emit and commit

### 4a. Write claims JSON

Write the claims array for this section to a temporary file (e.g. `.tlddr/draft-<section_id>.json`):

```json
[
  {
    "section_id": "<section-id>",
    "text": "<one factual claim in one or two sentences>",
    "support_level": "fully_supported",
    "evidence_relation": "quoted",
    "sources": [
      {"node_id": "<node-id>", "page": 3}
    ]
  },
  {
    "section_id": "<section-id>",
    "text": "<another claim>",
    "support_level": "partially_supported",
    "evidence_relation": "inferred",
    "sources": [
      {"node_id": "<node-id>", "page": 5},
      {"node_id": "<other-node-id>", "page": 2}
    ]
  }
]
```

Each file must be a JSON array, even if it contains a single claim. All claims in a single commit call must share the same `section_id` — the commit is section-scoped.

### 4b. Commit

```
tlddr draft-commit \
  --claims .tlddr/draft-<section_id>.json \
  --extracted .tlddr/extracted \
  --work .tlddr \
  --sections .tlddr/sections.json
```

The CLI validates each claim's citations, drops those that cannot be resolved, turns zero-citation claims into findings, and writes the valid claims to the committed store. Claims tagged to an unknown section id are dropped with a finding. The commit is section-scoped: re-committing for the same section replaces all prior claims for that section cleanly.

After each commit, delete or overwrite the temporary file before drafting the next section.

## Phase 5 — Evaluate and assemble

### Evaluate groundedness

Once all sections are drafted and committed:

```
tlddr draft-eval --work .tlddr --sections .tlddr/sections.json
```

Prints: total claims, support level breakdown (fully/partially/unsupported), evidence relation split (quoted vs inferred), and a list of sections with no evidence. Review this readout before assembling. A high proportion of `partially_supported` or `unsupported` claims is a signal to re-read evidence or re-draft.

### Assemble the report

```
tlddr assemble \
  --work .tlddr \
  --out report \
  --sections .tlddr/sections.json \
  --vault vault
```

Writes `report/report.md` (the attributed draft, claims assembled under section headings) and `report/report_comments.md` (open findings and verify questions surfaced as inline comments). Also refreshes `vault/_triage.md` with all current questions (including draft and verify findings) so the D6 answer loop has an up-to-date answer surface. Share both report files with the user.

## Proving Gate

Stop. Ask the user to review `report/report.md` and `report/report_comments.md` and confirm:

- Every section's claims are faithful to the source evidence.
- The groundedness readout (support levels, no-evidence sections) is acceptable.
- Open findings in `report_comments.md` are understood and handled or acknowledged.

Do not proceed to draft-verify or any downstream stage until the user approves.
