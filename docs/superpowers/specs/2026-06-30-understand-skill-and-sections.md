# tl-ddr — Understand: the Skill, Section-tagging, and the Proving Run

**Status:** approved design, pre-implementation
**Date:** 2026-06-30
**Builds on:** `2026-06-28-understand-stage-design.md` (the stage's contracts and the deterministic/model boundary) and `2026-06-28-tl-ddr-design.md` (the four-stage architecture). Where this refines those, the refinement governs.

This slice makes the Understand stage come alive end-to-end. The deterministic toolkit (`tlddr understand-slice` / `understand-commit` / `understand-render`, plus confidence/edges/triage/render helpers) is already built and tested in isolation. What is missing is the procedure a host agent follows to drive it, the section-tagging capability against a user-provided report structure, the holistic edge pass, and the first model-driven run over the corpus. This document records the design decisions for that slice.

## Scope

**In:** the per-run Understand procedure (a `SKILL.md`), a one-time section-generation sub-step, section-tagging against the generated structure, the holistic cross-document edge pass, the section-no-evidence and connectivity coverage surfaced into triage, and the first proving run over all 20 corpus documents.

**Out (unchanged from prior design):** the content digest (phase-2), auto-deep-read escalation, contradiction-detection edges (no adversarial pair to prove against), and the Draft/Assemble stages.

## Terminology

To keep names honest across the spec and the code:

| Plain name (this spec) | Code / artifact | What it is |
|---|---|---|
| raw section file | e.g. `output_sections.md` | the user's report headings, as provided |
| **sections.json** | generated artifact | the curated, canonical section structure the run keys off |
| per-doc notes | `enrichment/<id>.json` | the agent's per-document comprehension output |
| node | `vault/<id>.md` + `Node` record | one vault entry per document (overlay + pointer) |
| slice | output of `understand-slice` | the bounded view of one document the agent reads |
| section-spec | the concept | the report's section structure in general (raw file → sections.json) |

## The flow

The stage runs in a one-time **Setup** plus a per-run sequence of four phases. Colour of responsibility in parentheses: user / CLI (deterministic) / agent (LLM) / TurboVault (MCP).

```
SETUP (once per section-spec)
  raw section file (user)
    └─► generate sub-step: agent interprets structure → user steers → materialize  (agent + user)
          └─► sections.json  (canonical section structure)

PER RUN (over the corpus)
  inputs: .tlddr/extracted/*.json (from Extract)  +  sections.json (from Setup)
  load sections.json once                                            (agent)
  Phase 1 — Comprehend (per doc)
    understand-slice → bounded slice                                 (CLI)
    comprehend → per-doc notes: description, doc_type, section tags,
      interpretation-confidence, questions; NO edges yet             (agent)
  Phase 2 — Relate (holistic, once)
    read all per-doc notes → propose typed edges across the set →
      add related[] to each notes file                               (agent)
  Phase 3 — Commit + Render
    understand-commit (per doc): validate edges + validate section
      tags + extraction-confidence + triage → node                  (CLI)
    understand-render: vault/, _index.md, _triage.md backbone        (CLI)
  Phase 4 — Coverage
    add vault to TurboVault → explore isolation/clusters/hubs →
      write agent coverage layer into _triage.md                    (agent + MCP)

  PROVING GATE: user eyeballs vault/ + _triage.md and judges it a trustworthy map.
```

## Decisions

### D1 — The section-spec mirrors the full heading tree; every heading is a fit-target

The generated structure faithfully reflects **every** heading in the raw file, including sub-headings (e.g. `Technology type 1/2` under `Key Technology`). The template is taken at face value: tl-ddr's job is to comprehend the vault and find the best fit against whatever headings it is given. A vague or placeholder heading demands **more interpretive effort from the agent**, not curation by us — a detailed heading gives more guidance, a lean one gives less. If genuinely nothing fits a heading, that is a legitimate no-evidence finding, not a false alarm to engineer away.

*Rejected:* collapsing the tree to the "meaningful" H2 themes (pre-judging which headings count — that judgment belongs to comprehension, not to a curation pass).

### D2 — The skill loads the section structure once; the slice stays per-doc

`sections.json` is a run-level input, identical for all documents. The skill reads it once at the top of the run and the agent holds it while it works through the docs. The bounded slice keeps one job — representing a single document — and gains no profile dependency. `understand-slice` stays a pure function of one `ExtractedDoc`.

### D3 — Defer commit; one holistic edge pass over the per-doc notes

Edges are the core value and must be proposed **holistically**, with the agent seeing every document's description, not one-doc-at-a-time. Therefore commit is deferred until edges exist:

- **Phase 1** writes a `enrichment/<id>.json` per doc carrying description, doc_type, section tags, interpretation-confidence, and questions — **no edges**.
- **Phase 2** is a single pass in which the agent reads *all* the per-doc notes (that pile **is** the index of all node descriptions) and proposes typed edges across the whole set, adding `related[]` to each notes file.
- **Phase 3** commits the now-complete notes and renders.

This requires **zero new deterministic code** — `build_slice`, `build_node`, and `validate_edges` are unchanged. The per-doc notes files are the description index; they exist regardless and are inspectable.

*Rejected:* commit-as-you-go with per-doc edges (edges proposed from partial context); a separate `understand-relate` command with an idempotent edge-attach and intermediate rendered index (resumability/auditability machinery a single-session run does not need — added later if corpus scale demands mid-run resume).

### D4 — Triage is a deterministic backbone plus an agent coverage layer

`_triage.md` has two clearly-owned layers in one surface:

- **Deterministic backbone (CLI / `render`):** the triage lights (red/amber/green), open questions, and **section no-evidence** (which section ids have zero tagged docs). Mechanical derivations, script-owned and unit-tested.
- **Agent coverage layer (agent + TurboVault):** the agent adds the vault to TurboVault, explores connectivity / thin clusters / hubs interactively, and writes its findings **directly into `_triage.md`** as a trusted coverage layer over the backbone — e.g. annotating isolated nodes the per-document confidence signals would never catch.

This encodes a principle for the whole project: **the deterministic layer is the foundation, not the whole thing; at some point trust is yielded to the agent, and the engineer's review of the triage surface is exactly where that trust is checked.** No `coverage.json` render-fold — laundering agent output through a script buys a purity that is not a project goal and fights the interactive TurboVault workflow.

TurboVault earns its place because the system targets vaults of **thousands** of documents, where connectivity and centrality are not eyeballable. (The 20-document corpus is a minimal proving harness; design decisions are made against the spec and the real target, never against the toy corpus. Broken-link detection is *not* a useful TurboVault signal here — `validate_edges` makes the vault broken-link-free by construction, and we do not armor a vault we generate end-to-end.)

*Rejected:* agent appends free-form prose (no structure at all); a separate `_coverage.md` (splits the triage surface at the proving gate); `coverage.json` rendered deterministically (machinery to launder agent output, contrary to the trust principle).

### D5 — The section-spec is a user input; the CLI consumes it

The user provides the section structure; tl-ddr does not invent it. Once `sections.json` exists, the CLI reads it in exactly two new places, both machine-trust:

- **`understand-commit`** validates each doc's `report_sections` tags against the section ids in `sections.json` and **drops any tag the agent invented** — the same guarantee `validate_edges` gives links.
- **`understand-render`** computes **section no-evidence** for the triage backbone.

### D6 — A generation sub-step: agent interprets, user steers, CLI materializes `sections.json`

Turning the raw section file into the canonical structure is a one-time sub-step, distinct from the per-run loop, invoked via a subskill (working name `tlddr generate`, exact name TBD):

1. The user points the subskill at the raw section file (e.g. `tlddr generate @output_sections.md`).
2. The agent **interprets** the structure — infers nesting, recognizes placeholder slots, carries any guidance the template provides (richer than a deterministic slugify) — and **presents the proposed structure** for review.
3. The user **nods or steers** (rename, regroup, correct).
4. The curated **`sections.json`** is materialized — the single canonical source of section ids.

This realizes the original "model drafts a thin structured profile, human-curated" intent and the D4 trust principle (agent interprets, human is the checkpoint). It satisfies machine-trust — `sections.json` is the one id source both the tagging agent and the validator read, so ids always agree — and drift is not silent: regeneration is a deliberate, curated act, re-run when headings change.

*Rejected:* a deterministic-only parser (cannot read guidance prose from a rich template; would need a model pass anyway — two mechanisms for one job); the agent inventing ids per-run with no canonical source (validator cannot match; machine-trust breaks).

## Data shapes

**`sections.json`** — a flat, ordered list of sections, each carrying an id, title, and optional parent (and any guidance the template provides):

```json
[
  {"id": "permitting-environmental", "title": "Permitting and Environmental review"},
  {"id": "key-technology", "title": "Key Technology"},
  {"id": "key-technology-overview", "title": "Overview", "parent": "key-technology"},
  {"id": "key-technology-type-1", "title": "Technology type 1", "parent": "key-technology"},
  {"id": "key-technology-type-2", "title": "Technology type 2", "parent": "key-technology"},
  {"id": "energy-yield", "title": "Independent Energy Yield Assessment Summary"},
  {"id": "operation-maintenance", "title": "Operation and Maintenance"},
  {"id": "financial-model", "title": "Financial Model"}
]
```

The `parent` link is **context for the agent** (reading `Technology type 1` under `Key Technology` tells it "a slot for one of the project's technology types"), not roll-up machinery. The no-evidence pass checks every section id, sub-headings included.

**Per-doc notes** (`enrichment/<id>.json`) gain a `report_sections` field — a list of section ids the agent best-fit the document to. This is the only model-side addition; the existing `Node.report_sections` field already exists and is currently left empty.

## CLI changes required

- **`understand-commit` gains `--sections <path>`:** loads `sections.json`, validates `report_sections` tags against its ids (drops unknown ids, mirroring edge validation), and populates `Node.report_sections`.
- **`understand-render` gains `--sections <path>`:** computes section→nodes coverage and renders a "Section coverage" block (no-evidence sections called out) plus an "isolated nodes" note (nodes with no edges) into the `_triage.md` backbone.
- **A shared sections loader/validator** in `tlddr/understand/` (e.g. `sections.py`): parse/validate `sections.json`, expose the section-id set and the ordered list. Used by commit and render.
- **The `generate` subskill** produces `sections.json` (agent-authored, human-steered). Whether a thin `tlddr` command validates the written JSON shape is an implementation-plan detail.

All new deterministic helpers are unit-tested Python, consistent with the rest of the toolkit. Tag-validation and no-evidence are pure functions of `(nodes, sections.json)`.

## The proving run

**Setup:** run the `generate` sub-step over `output_sections.md` to produce a curated `sections.json` (the user steers it once).

**Run (all 20 documents):** Phase 1 comprehend each doc (with section tags) → Phase 2 holistic edge pass → Phase 3 commit + render → Phase 4 TurboVault coverage into `_triage.md`.

**Proving gate:** the user eyeballs `vault/` + `_triage.md` and judges it a trustworthy map of what is in the corpus — useful descriptions, sensible cross-document relationships, an honest traffic-light, meaningful section coverage, and connectivity flags. This is the make-or-break for the stage. It does **not** require the finished worked-example report (a Draft-stage concern, still not provided).

All 20 documents because the value is cross-document; subsetting would hide the edges, and the cost is small (20 bounded-slice comprehensions + one edge pass + one coverage exploration).

## Build principles carried

- **Honesty over coverage** — a flagged gap (no-evidence section, isolated node, low confidence) beats a confident fabrication.
- **Machine-trust at the seams** — the model never writes an edge target or a section tag that the CLI has not verified against a known set.
- **The deterministic boundary, then earned trust** — script-owned derivations form the backbone; agent judgment is layered on and checked by the human review of the triage surface.
- **Designed for scale, proven minimally** — decisions target vaults of thousands of documents; the 20-doc corpus only proves the shape.

## Open questions deferred to implementation planning

- The exact subskill name and whether the section-generation step is a standalone `SKILL.md` or a "Setup" phase of the Understand `SKILL.md`.
- The precise `sections.json` schema validation (required fields, parent-reference integrity) and whether a `tlddr` command enforces it.
- The exact TurboVault tool sequence for the coverage exploration and the shape of the agent coverage layer in `_triage.md`.
- How the `generate` sub-step renders its proposed structure for steering (the visual companion vs a terminal table).
- Section-tag granularity conventions (whether tagging a child implies the parent; current default: tag explicitly, no implicit roll-up).
