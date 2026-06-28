# tl-ddr — Understand Stage Design

**Status:** approved design, pre-implementation
**Date:** 2026-06-28
**Builds on:** `2026-06-28-tl-ddr-design.md` (overall four-stage architecture and contracts)

The Understand stage is the second movement of the pipeline: it turns the faithful, content-complete `ExtractedDoc` records produced by extraction into an **understood, linked vault** — one node per document, with a description, relationships to other documents, confidence signals, and a traffic-light triage — plus the coverage signal that feeds the human-in-the-loop quarantine surface.

This document records the decisions made while brainstorming the stage. Where it refines the original design doc, the refinement governs.

## Scope

**Understand is:** reduce-in → comprehend → relate → validate/derive → serialize → analyse → index. It produces the vault (`vault/`), the index (`_index.md`), and feeds the cross-cutting triage surface (`_triage.md`).

**Understand is not:** the **quarantine/triage channel** (cross-cutting; Understand is one of its two producers, Draft is the other) and the **section profile** (an *input*, authored once, not produced here). These plug into Understand; they are not steps within it.

## The division of labour (LLM vs deterministic)

The single most important clarification: **the LLM does all the comprehension; deterministic code never comprehends.** It only does the mechanical work around the model's judgment.

| Step | What | Who | Comprehension? |
|------|------|-----|----------------|
| 1. Reduce-in | Build the bounded slice from the `ExtractedDoc` (title, structure/headings/sheet-names, head sample, warnings) | `tlddr` CLI | No |
| 2. Comprehend | description, doc_type, interpretation confidence (and, later, section tags) | **host agent (LLM)** | **Yes** |
| 3. Relate | propose typed cross-doc edges + rationale | **host agent (LLM)** | **Yes** |
| 4. Validate + derive | edge target exists? extraction confidence; derive triage | `tlddr` CLI | No |
| 5. Serialize | write each node `.md` (frontmatter + body) from validated fields | `tlddr` CLI | No |
| 6. Analyse | coverage: isolated clusters, dead-ends, broken links, centrality | TurboVault (MCP) | No |
| 7. Index/triage render | `_index.md`, `_triage.md` | `tlddr` CLI | No |

## Orchestration

The deployable tool is three portable pieces: **`SKILL.md`** (the procedure and judgment), the **`tlddr` CLI** (the deterministic muscle, tested like `extract`), and **MCP / TurboVault** (vault ops and analysis). The *model* is whatever agentic host loads them.

- **All model/judgment work runs in the host agent** — comprehension, edge proposal, interpretation confidence, and (when built) image description. The host is multimodal; there is no separate programmatic model client.
- **All deterministic work runs in the `tlddr` CLI** — slice-building, extraction-confidence computation, edge validation, triage derivation, node serialization, index/triage rendering. These are unit-tested Python.
- **Vault ops run via MCP (TurboVault).**
- **Swapping the model = swapping the host.** Loading the same `SKILL.md` + `tlddr` + MCP into an isolated Copilot Studio session runs the stage identically; no code change. The "one model interface" is the host-agent boundary, not a Python `LLMClient`.

The comprehension is LLM judgment that is *reviewed*, not unit-tested. Testability lives in the deterministic helpers, which are Python regardless of host. If a headless, non-agentic batch mode is ever needed, those helpers are the right seam to add a programmatic client behind — nothing here forecloses it.

## Read strategy: bounded slice, with escalation

The model cannot read full content (the corpus is ~21M chars; the ISP workbook alone is ~5M tokens). For each document, the CLI builds a **bounded representative slice** — title, document structure (headings for prose, sheet names for spreadsheets), a head sample of content, and the extraction warnings — capped at a few thousand tokens. The agent comprehends from the slice.

This is cheap (one comprehension per doc) and adapts per signal type without separate code paths (the slice for the 19MB xlsx is its sheet names + the disclaimer sheet, never the body). The honesty mechanism is the escalation trigger: a document understood from too thin a slice reads as **low interpretation confidence**, which routes it to amber/quarantine. Automatic deep-reading of low-confidence docs (map-reduce over the full content) is designed-for but **deferred** — in the proving step, low confidence simply quarantines.

## Data model: the vault node

The faithful, content-complete representation of every document already exists in the `ExtractedDoc` store (`.tlddr/extracted/<id>.json`), page-structured. **The node does not clone it.** The node is the *understanding overlay plus a pointer* into that store. The content lives once.

A node is structured metadata (frontmatter, queryable via `query_metadata`) projected into a human-readable body (Obsidian / TurboVault):

```yaml
---
id: a6-cost-benefit-analysis
extracted_id: a6-cost-benefit-analysis      # pointer into the content store
doc_type: cost-benefit analysis appendix
report_sections: []                           # tagged vs the profile (deferred in proving)
confidence_extraction: high                   # script-derived from extraction signals
confidence_interpretation: medium             # LLM self-report
triage: amber                                  # derived (never hand-set)
open_questions: [q-0007]                       # section-tied quarantine refs
related:                                        # LLM-proposed, script-validated edges
  - {target: a3-renewable-energy-zones, relation: corroborates, rationale: "..."}
---
# A6 Cost-Benefit Analysis
<description: a readable paragraph — what it is + what it covers + key topics>
## Related
[[a3-renewable-energy-zones]] — corroborates: ...
## Open questions
See `_triage.md` (q-0007).
```

**Node anatomy decisions:**
- **Overlay + pointer, not a clone (and not a digest — yet).** The body carries a genuinely readable *paragraph* description (so the vault is browsable on its own), not a one-liner. A richer model-written **content digest** was considered and **deferred to phase-2**, because a *faithful* digest of a long document requires reading the whole document — which reopens the bounded-slice cost. A slice-based digest of a 137-page doc would look complete and not be. If A's nodes prove too thin to review or to drive Draft selection, that is the evidence to spend the whole-doc reads; until then we don't.
- **Grounding guardrail (in from the start).** Citations always resolve to `(node_id, page)` in the **source store**, never to the node's description/overlay text. So whether the node stays thin or later grows a digest, Draft grounds and cites against the evidence, never against the model's paraphrase. This is what makes the A→B (digest) upgrade safe.
- Provenance (`source_path`, `source_sha256`, `pages[]`) is not duplicated into the node; it is reached through `extracted_id`.

The node record composes the extracted record *by reference* (holds `extracted_id`), not by embedding or subclassing — consistent with composition over inheritance.

## The section profile (input)

Section tagging (step 2) maps each document to the report sections it is relevant to, against a machine-readable **profile**: per section `id`, `title`, and whatever guidance the source template provides (`purpose`, `expected_inputs`, `depth`, `example` — present if the template carries them, absent if it is lean).

- The profile is produced by the **model drafting a thin structured profile from the user's template, human-curated** — it *mirrors the template's richness* (lean headings stay lean; headings-with-guidance carry through). We do not invent guidance the user did not provide.
- It is materialized (not re-read raw each run) because two stages need a **stable section list**: Understand tags against fixed section ids, Draft loops section-by-section.
- The stand-in template for this POC is `Business-Case-Template-v11.docx` (now faithfully extractable, tables included).
- **Section tagging is deferred in the proving step** (see Proving scope) — it needs the profile authored first and is the least convincing capability on this thematically-mismatched corpus. It remains in the design; the coupling decision ("tag at understand time for early gap-finding") stands, sequenced after the core graph.

## Confidence and triage

Two confidence signals, assigned by the party that actually knows, both ordinal (`high` / `medium` / `low`):

- **Extraction confidence — script-derived.** The LLM only sees extracted text, not the source, so it cannot judge extraction fidelity. The signal already exists deterministically from extraction: `warnings`, `signal_type`, image-only/vision-flagged pages, XLSX truncations, text-layer coverage. The CLI computes it **proportionally** (one unread cover page in a 115-page doc barely dents it; an all-image doc or a truncated workbook drops it).
- **Interpretation confidence — LLM self-report.** "Do I actually understand what this is and how it relates?" — the one judgment genuinely in the model's gift, reported during comprehension.

Ordinal over floats: the signal feeds a three-colour light; `0.73` would be invented precision.

**Triage is a deterministic, transparent function** (never hand-set):

```
if any blocking open-question:                   RED
elif min(extraction, interpretation) == LOW:     RED
elif min == MEDIUM or any open-question:          AMBER
else (both HIGH, no questions):                   GREEN
```

## Cross-document edges

The core value: typed edges between documents, with rationale. Vocabulary: `contradicts | supersedes | corroborates | references | same_subject | input_to`.

- **Design (C):** a dedicated cross-doc pass in which the agent sees the **index of all node descriptions** and proposes edges holistically, plus — for the headline `contradicts` edge — a *targeted content-level comparison* of pairs flagged "same subject, worth a conflict check" (because similarity tools structurally cannot tell "agrees" from "contradicts").
- **Build (B):** for the proving step, the topical pass only. With just 20 documents the agent can consider all relationships from the description index directly; TurboVault `suggest_links` recall-seeding is not needed at this scale (it matters at hundreds of docs). The model is always the **semantic proposer**; TurboVault is never trusted for the label.
- **Contradiction-escalation is deferred** — this corpus is thematic, not adversarial, so it has no contradictions to detect or validate. Building it now would be untestable code. It is implemented when an adversarial document pair exists to prove it.
- **Validation (CLI):** every proposed edge's `target` must be a member of the known node-id set, or the edge is dropped. This is the entire machine-trust guarantee — the model never writes a link that is trusted without the target being verified to exist.

## Quarantine and the reviewer sidecar

**Quarantine** is cross-cutting, not part of Understand. Understand emits `open_questions` (section-tied where applicable) into the working answer-surface `_triage.md`; a resume consumes answers. Low-confidence or ambiguous documents produce a self-contained question.

**The reviewer sidecar** is a downstream (Draft/Assemble) output, recorded here because it imposes tracking requirements that must be honoured *now*. Alongside the published draft, the pipeline will produce a per-section reviewer companion (working name `report_comments.md`) containing, for each section: provenance (every document referenced), warnings (which low-confidence documents were used), open questions, and **clarifications on logical inferences** (where the model connected dots not explicitly stated). It keeps the published document clean while making the reasoning auditable.

For that sidecar to be assemblable, the upstream stages must track:
- **Node** carries confidence (already in this design).
- **Draft claim** must carry, per claim: its sources `(node_id, page)`, the source's confidence, and an **inference flag/note** (quoted vs inferred).
- **Open questions** must be tied to sections/refs so they aggregate under the right heading.

Relationship to `_triage.md`: the triage file is the *working* answer-surface *during* a run; the sidecar is the *delivered* reviewer companion *beside the final report*. Unanswered questions flow from the former into the latter. The exact relationship is settled when Draft is designed; flagged here so it is deliberate.

## Outputs

- `vault/` — one node `.md` per document (frontmatter overlay + readable body + validated wikilinks).
- `_index.md` — the navigable index tying the vault together.
- `_triage.md` — the traffic-light quarantine surface (red / amber / green), the working answer-surface.
- TurboVault coverage (isolated clusters, dead-ends, broken links, centrality) feeds the amber/green entries.

## Build principles carried

- **Honesty over coverage** — a flagged gap beats a confident fabrication; the triage surface and quarantine are first-class.
- **Everything traceable** — claims cite `(node_id, page)` into the source store; no orphan assertions; the grounding guardrail forbids citing overlay text.
- **Cross-document relationships are the value** — edges are built deliberately, in the proving step, not deferred.
- **The faithful store is the foundation** — the node is an index over the evidence, never a paraphrase of it.
- **Swappable seams** — model = host (swap the host), vault = MCP, deterministic muscle = CLI.

## Proving step

The make-or-break to prove: from bounded slices, can the model produce useful descriptions, sensible relationships, and an honest traffic-light — such that a senior engineer eyeballs the vault and trusts it as a map of what's there?

**Scope (all 20 documents):** descriptions + doc_type + the two confidences + triage + topical edges + `_index.md` + `_triage.md` + TurboVault coverage. All 20 because the value is cross-document — subsetting would hide the edges — and the cost is small (20 bounded-slice comprehensions + one edge pass).

**Deferred (designed-for, not built now):** section-tagging (needs the profile; weak on this corpus), contradiction-escalation (no adversarial pair to prove it), the content digest (phase-2), and auto-deep-read escalation (low confidence quarantines instead).

**Proving gate:** you eyeball `vault/` + `_triage.md` and judge it a trustworthy map. This does not require the finished worked-example report (still not provided) — the stage is about the vault, not a draft-vs-report diff.

## Open questions deferred to implementation planning

- The exact extraction-confidence formula (which signals, what proportional thresholds map to high/medium/low).
- The precise bounded-slice budget and how structure is sampled per signal type.
- The `tlddr` subcommand surface for the deterministic helpers, and how `SKILL.md` sequences them.
- The node-id / `extracted_id` reconciliation (they share the slug today; confirm they stay identical).
- The exact TurboVault tool sequence for indexing the generated vault and pulling coverage.
