# tl-ddr — Session Handoff

**Last updated:** 2026-06-30
**Repo:** `/home/tim/Github/tl-ddr` · branch `main` at the `understand-skill-sections` merge · 65 tests passing

Point a fresh session at this file. It captures what tl-ddr is, what is built, every design decision already made (so they are not re-litigated), what is deferred, and the next step: **the Draft stage**. Read this first, then the linked specs as needed.

---

## What tl-ddr is

A proof-of-concept that drafts **Technical Due Diligence (TDD) reports** from a pile of client source documents. The AI reads the whole document vault and drafts the report against a template, shifting the engineer's job from "read everything and write from scratch" to "review, correct, sign off." Its defining posture: **flag what it is unsure about instead of guessing** — for due diligence, an honest gap beats confident fabrication.

Name = TDD + tl;dr. The success bar: a senior engineer looks at the output and says "this genuinely saved me time, and I trust how it got there."

**The pipeline (four stages + a cross-cutting channel):**
```
Extract ──► Understand ──► Draft (per section) ──► Assemble ──► report
[done]        [done,            [NEXT]              [not started]
            proven end-to-end]
   │              │                  │
   └──── Quarantine queue ◄──────────┘   (triage surface; Understand + Draft both feed it)
```

---

## Where everything lives

| Thing | Path |
|---|---|
| Overall design spec (all four stages, contracts) | `docs/superpowers/specs/2026-06-28-tl-ddr-design.md` |
| Understand stage design spec | `docs/superpowers/specs/2026-06-28-understand-stage-design.md` |
| Understand skill + section-tagging spec (this slice) | `docs/superpowers/specs/2026-06-30-understand-skill-and-sections.md` |
| Understand skill + section-tagging plan (this slice) | `docs/superpowers/plans/2026-06-30-understand-skill-and-sections.md` |
| Extraction recon plan / findings | `docs/superpowers/plans/2026-06-28-extraction-reconnaissance.md`, `docs/superpowers/reconnaissance-findings-2026-06-28.md` |
| Test corpus (20 source docs) | `docs/test-reports/Engineering reports test/` (gitignored) |
| **Report section-spec (headings-only)** | `docs/test-reports/Engineering reports test/output_sections.md` |
| Python package | `tlddr/` (`tlddr/extract/`, `tlddr/understand/`) |
| **Host-agent procedures (SKILL.md)** | `skills/understand/SKILL.md`, `skills/generate-sections/SKILL.md` |
| Tests | `tests/` (65 tests) |

**Memory** (`/home/tim/.claude/projects/-home-tim-Github-tl-ddr/memory/`): user working preferences + project gotchas — read these.
- `brainstorm-decision-format.md` — present decisions as issue → options×criteria table → recommendation, one at a time.
- `dont-over-armor-controlled-systems.md` — right-size safeguards to real failure modes; don't over-engineer.
- `turbovault-navigation-vs-semantic.md` — TurboVault over the generated vault counts `_index`/`_triage` as edges; use the deterministic `isolated_nodes` for semantic isolation.

---

## What's DONE

### Stage 1 — Extract (merged, proven)
`tlddr extract --source <dir> --out <dir>` routes each file by **signal type** (not extension) to a format extractor — all emitting one uniform `ExtractedDoc` record (full faithful content + page-level provenance + warnings). Verified over all 20 corpus docs: every document is identifiable from its extracted form. Records live in `.tlddr/extracted/<id>.json` — **the content store the rest of the pipeline reads from** (`ExtractedDoc.content` is the full text, page-structured via `pages[]`).
- PDF (pymupdf), DOCX (python-docx, prose + tables in order), XLSX (openpyxl, with truncation warnings), KMZ (stdlib, identity-only). Image-only pages flagged for vision + thumbnail (no model call yet).

### Stage 2 — Understand (merged, proven end-to-end this session)
The deterministic toolkit **and** the host-agent procedure that drives it. The model does comprehension/edges/section-tags; the tested `tlddr` CLI does everything deterministic.

**Deterministic toolkit** (`tlddr/understand/`): `slice.py` (bounded slice), `confidence.py` (script-derived extraction confidence), `triage.py` (deterministic red/amber/green), `edges.py` (machine-trust edge validation), `sections.py` (load/validate `sections.json` + validate section tags), `commit.py` (`build_node`), `node_render.py` / `render.py` (vault node + `_index.md` + `_triage.md`, incl. section-coverage + isolated-node blocks).

**CLI surface:**
- `tlddr understand-slice --extracted <dir> --id <id>` — the bounded slice the agent reads.
- `tlddr sections --sections <sections.json>` — load/validate/print the canonical section structure.
- `tlddr understand-commit --enrichment <f> --extracted <dir> --out <dir> --sections <sections.json>` — validate the agent's enrichment (edges + section tags, machine-trust) into a `Node`.
- `tlddr understand-render --work <dir> --vault <dir> --sections <sections.json>` — render the vault, `_index.md`, `_triage.md` (triage groups + section no-evidence + isolated docs).

**Host-agent procedures:**
- `skills/generate-sections/SKILL.md` — one-time: agent interprets the user's raw heading file → user steers → materializes `sections.json` (the canonical `{id, title, parent?}` structure).
- `skills/understand/SKILL.md` — per run: load sections → Phase 1 comprehend each doc (slice → enrichment notes, no edges) → Phase 2 holistic edge pass over all notes → Phase 3 commit + render → Phase 4 TurboVault coverage layered into `_triage.md` → proving gate.

**The proving run (this session) PASSED its gate.** Over all 20 docs: useful descriptions, sensible typed cross-document edges (5 coherent clusters; `r972` correctly flagged isolated), honest triage (5 red = thin-slice/low-confidence docs), and section coverage where the placeholder `Technology type 1/2` slots best-fit the wind/solar/nuclear papers. Run artifacts (`.tlddr/`, `vault/`) are gitignored; regenerate with the two skills. `sections.json` for the corpus is at `.tlddr/sections.json`.

---

## NEXT STEP — the Draft stage

This is where the vault becomes a report. **Brainstorm first** (per the superpowers workflow), then plan, then build. The overall design (`2026-06-28-tl-ddr-design.md`, the DRAFT sections) already fixes the shape:

**What Draft does:** model, **per section**, script-orchestrated. For each section in the section-spec: gather the nodes tagged to it (`report_sections`), read the relevant **source content** (from the `ExtractedDoc` store, not the overlay), draft against the section's guidance, and emit `DraftClaim`s — each carrying its sources as `(node_id, page)` citations.

**Two artifacts (decided, tracking already honored upstream):**
1. The **published draft** (clean).
2. A per-section **reviewer sidecar** (working name `report_comments.md`) with, per section: provenance (every doc referenced), warnings (which low-confidence docs were used), open questions, and **clarifications on logical inferences** (where the model connected dots not explicitly stated).

**Contracts already in the design** (`2026-06-28-tl-ddr-design.md` §Data contracts):
- `DraftClaim` carries, per claim: its sources `(node_id, page)`, the source's confidence, and an **inference flag** (quoted vs inferred) — this is what makes the sidecar assemblable.
- **Grounding guardrail (in from the start):** citations always resolve to `(node_id, page)` in the **source store**, never to a node's description/overlay text. The node is an index over the evidence, never a paraphrase of it.
- A section with **no inbound nodes** → a Draft-stage quarantine finding (`raised_by=draft`, `section_id` set, `node_id=None`) — itself a due-diligence finding. A section that comes back **thin** → flagged for review.

**Design tensions to work in the Draft brainstorm (genuinely open):**
1. **Section-spec richness.** The current `generate-sections` produces a lean `{id, title, parent}` (the test template is headings-only). The design's `SectionSpec` also carries `purpose` / `expected_inputs` / `depth` / `example` to ground per-section drafting. Decide: does Draft need the richer fields, and does `generate-sections` grow to interpret/elicit them — or does the model infer per-section guidance from the bare heading? (Mirror the lean-profile principle: don't invent guidance the user didn't provide, but Draft may need *some* depth signal.)
2. **Reading content for drafting reopens the bounded-slice cost.** Understand deliberately reads only bounded slices. Draft must read the *actual relevant content* of the tagged docs to write grounded claims — which for long docs (the 137-page ISP, the 19MB xlsx) is exactly the whole-doc read Understand avoided. This is where **auto-deep-read escalation** (designed, deferred in Understand) likely has to land. Decide the read strategy per section: which pages of which tagged nodes, how bounded.
3. **DraftClaim provenance + inference mechanics** — how the model emits `(node_id, page)` + source-confidence + the quoted-vs-inferred flag, and how the script validates citations resolve to real pages in the source store.
4. **The sidecar structure + its relationship to `_triage.md`** — `_triage.md` is the *working* answer-surface during a run; the sidecar is the *delivered* companion beside the final report. Unanswered questions flow from the former into the latter. Settle the exact relationship now that Draft is being designed.

**Deterministic/model line for Draft (carry forward):** the model drafts + emits structured `DraftClaim`s; tested Python validates citations, detects empty/thin sections, and orchestrates section-by-section. Assemble (stage 4) is then pure deterministic roll-up.

---

## Decisions already made (do NOT re-litigate)

**Architecture / orchestration**
- **Model = the host agent.** Comprehension / drafting / edge-proposal run in whatever agentic host loads the tool. The deployable unit is `SKILL.md` (judgment) + `tlddr` CLI (deterministic muscle) + MCP/TurboVault (vault ops). Swap to Copilot = swap the host, not a programmatic LLM client. (For the *vision* sub-path inside Extract — not built yet — a programmatic model-seam client is the intended seam; that is the one exception.)
- **Deterministic/model boundary = the seams.** Extract + Assemble = script; Understand + Draft reasoning = host agent. Every model output is structured data that tested deterministic code validates and renders.

**The vault & the node**
- **No content clone.** Faithful content lives once, in the `ExtractedDoc` store. The vault `Node` is an understanding overlay + a pointer (`extracted_id`), never a copy. The vault markdown is a projection.
- **Grounding guardrail:** citations resolve to source `(node_id, page)`, never to overlay/description text.
- A richer model-written content **digest** in nodes is deferred to phase-2 (a faithful digest of a long doc needs whole-doc reads — which Draft's read-strategy decision now confronts directly).

**Confidence & triage**
- Two ordinal signals (high/medium/low). **Extraction confidence is script-derived** (the LLM can't judge fidelity it didn't perform); **interpretation confidence is the LLM's self-report.** Triage is a deterministic rule: blocking question → RED; else min(ext,interp)==LOW → RED; else MEDIUM or any question → AMBER; else GREEN. Never hand-set.

**Edges (the cross-document value)**
- Vocabulary: `contradicts | supersedes | corroborates | references | same_subject | input_to`.
- The agent proposes edges holistically from the index of all node descriptions; the script validates every `target` is a known node-id (the entire machine-trust guarantee). **Contradiction-detection escalation** (content-level pair comparison) is designed but deferred — this corpus is thematic, not adversarial.

**Section-spec & tagging (this slice, D1–D6 in `2026-06-30-understand-skill-and-sections.md`)**
- The section-spec is a **user-provided input**; tl-ddr does not invent it. It mirrors the full heading tree — every heading (incl. sub-headings) is a fit-target; vague headings mean more agent interpretive effort, not curation.
- A one-time **generate sub-step** (agent interprets the raw heading file → user steers → materializes `sections.json`) produces the canonical structure. The CLI consumes it: validate section tags at commit (drop invented ones, machine-trust), compute section no-evidence at render.
- **Triage = deterministic backbone (CLI) + agent coverage layer (TurboVault).** The deterministic layer is the foundation; agent judgment is layered on and **checked by the human review of the triage surface** — the trust checkpoint.

**The two Draft/Assemble outputs** — published document + per-section reviewer sidecar (`report_comments.md`). Recorded forward; the upstream tracking it requires (Node confidence; DraftClaim's `(node_id, page)` + source-confidence + inference flag; section-tied questions) is already honored.

---

## Deferred / known limitations (designed-for, not built)

- **Auto-deep-read escalation** — low interpretation-confidence currently just quarantines. Draft's read-strategy decision (tension #2 above) likely forces this to be built.
- **Content digest** in nodes (phase-2).
- **Contradiction-detection edges** — needs an adversarial document pair to prove; the corpus has none.
- **Vision path** (describe image-only pages) not built; first real job is the single ISP cover thumbnail.
- **XLSX extraction** is bloated (empty-cell padding, ~19MB) and 200-row/sheet truncated — fix only when a drafted section needs the workbook (evidence-driven).
- **PDF table/multi-column pages** unverified (only a prose page was visually checked).

**Corpus caveat:** the 20 docs are thematically-related public energy/climate reports, not a single client's adversarial set. The `output_sections.md` (a real TDD structure) fits this corpus well, so section-tagging and the understanding map are genuinely demonstrable — but cross-document *contradiction* findings cannot be shown here. **No finished worked-example report exists yet:** the draft-vs-handwritten gap analysis (the core Draft evaluation signal) cannot fully run until one is provided. Draft can still produce a draft + sidecar to eyeball; the gold-comparison is what's gated.

---

## How a fresh session should start

1. Read this file, then skim `2026-06-28-tl-ddr-design.md` (the DRAFT + Assemble sections and the `DraftClaim` / `SectionSpec` / `Question` contracts) and `2026-06-30-understand-skill-and-sections.md` (what Understand now produces and the deterministic/agent-trust principle).
2. Read the three memory files (working preferences + the TurboVault gotcha) — **present design decisions as issue → options×criteria table → recommendation, one at a time; don't over-engineer.**
3. This work uses the **superpowers workflow** (per the user's global CLAUDE.md): `brainstorming` → `writing-plans` → `subagent-driven-development`, with TDD throughout. Start the Draft slice with the **brainstorming** skill, working the four design tensions above one at a time.
4. **Environment:** Arch Linux, system Python 3.14, project venv at `.venv` (binary wheels confirmed working on 3.14). Run tests with `.venv/bin/pytest`. Package installed editable (`pip install -e ".[dev]"`). Deps: pydantic, pymupdf, python-docx, openpyxl, pyyaml (+ pytest dev).
5. **Re-create the working vault if needed:** `tlddr extract` over the corpus populates `.tlddr/extracted/`; `.tlddr/sections.json` exists (regenerate via `skills/generate-sections`); follow `skills/understand/SKILL.md` to rebuild `vault/`. All run artifacts are gitignored.
6. **Git discipline:** branch off `main` for new work (don't commit to main directly); conventional commits; no emojis anywhere (hard user rule). TurboVault is live in `.mcp.json` (activates on session reload).

The immediate first action of the next session: invoke `brainstorming` and work the Draft-stage design (read strategy, section-spec richness, DraftClaim provenance, the reviewer sidecar), one decision at a time.
