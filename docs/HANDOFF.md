# tl-ddr — Session Handoff

**Last updated:** 2026-06-30
**Repo:** `/home/tim/Github/tl-ddr` · branch `main` at the `draft-stage-design` merge (`45856cb`) · 96 tests passing

Point a fresh session at this file. It captures what tl-ddr is, what is built (now all four pipeline stages), every design decision already made (so they are not re-litigated), what is deferred, and the candidate next directions. Read this first, then the linked specs as needed.

---

## What tl-ddr is

A proof-of-concept that drafts **Due Diligence reports** from a pile of client source documents. The AI reads the whole document vault and drafts the report against a template, shifting the engineer's job from "read everything and write from scratch" to "review, correct, sign off." Its defining posture: **flag what it is unsure about instead of guessing** — for due diligence, an honest gap beats confident fabrication.

In industry terms it is a **template-driven, attributed grounded-generation system built on agentic RAG** (claim-level attribution per AIS/ALCE, agentic/tiered retrieval per Self-RAG, faithfulness eval per RAGAS, abstention). The due-diligence report is one application; nothing in the machinery is specific to it. The name is retained from the project's origin (no longer scoped to *technical* due diligence; a `tldreport` = "TempLate Driven Report" rename was floated and **deferred**). The success bar: a senior engineer looks at the output and says "this genuinely saved me time, and I trust how it got there."

**The pipeline (four stages + a cross-cutting channel) — all four now built:**
```
Extract ──► Understand ──► Draft (per section) ──► Assemble ──► report + reviewer sidecar
[done]       [done]          [done, proven]         [done: tlddr assemble]
   │             │                  │
   └──── Quarantine queue ◄─────────┘   (one Question store; understand/draft/verify all feed it)
```

---

## Where everything lives

| Thing | Path |
|---|---|
| Overall design spec (all stages, contracts) | `docs/superpowers/specs/2026-06-28-tl-ddr-design.md` |
| Understand stage spec / skill+sections spec / plan | `docs/superpowers/specs/2026-06-28-understand-stage-design.md`, `…/2026-06-30-understand-skill-and-sections.md`, `docs/superpowers/plans/2026-06-30-understand-skill-and-sections.md` |
| **Draft stage spec + plan** | `docs/superpowers/specs/2026-06-30-draft-stage-design.md`, `docs/superpowers/plans/2026-06-30-draft-stage.md` |
| Extraction recon plan / findings | `docs/superpowers/plans/2026-06-28-extraction-reconnaissance.md`, `docs/superpowers/reconnaissance-findings-2026-06-28.md` |
| Test corpora (4 sibling folders, gitignored) | `docs/test-reports/` — `Engineering reports test` (20 docs, fully prepared) + `Chevron 10-K filing`, `CONSOL Energy S-4 filing`, `Microsoft 10-K filing` (NEW, unprepared) |
| Report section-spec (headings-only) | `docs/test-reports/Engineering reports test/output_sections.md` |
| Python package | `tlddr/` (`tlddr/extract/`, `tlddr/understand/`, `tlddr/draft/`) — each subpackage has a `CLAUDE.md` index |
| Host-agent procedures (SKILL.md) | `skills/generate-sections`, `skills/understand`, `skills/draft`, `skills/draft-verify` |
| Tests | `tests/` (96 tests) |

**Memory** (`/home/tim/.claude/projects/-home-tim-Github-tl-ddr/memory/`) — read these:
- `brainstorm-decision-format.md` — present decisions as issue → options×criteria table → recommendation, one at a time.
- `dont-over-armor-controlled-systems.md` — right-size safeguards to real failure modes; don't over-engineer.
- `turbovault-navigation-vs-semantic.md` — TurboVault counts `_index`/`_triage` as edges; use the deterministic `isolated_nodes` for semantic isolation.
- `best-practice-first-decisions.md` — **top design criterion is settled industry best practice; verify via research, not memory.**

---

## What's DONE

### Stage 1 — Extract (merged, proven)
`tlddr extract --source <dir> --out <dir>` routes each file by **signal type** to a format extractor — all emitting one uniform `ExtractedDoc` (full faithful content + page-level provenance + warnings) to `.tlddr/extracted/<id>.json`, the content store the rest of the pipeline reads from. PDF (pymupdf), DOCX (python-docx, prose+tables; **note: `pages=[]`, no page markers**), XLSX (openpyxl, `--- sheet ---` markers, truncated/bloated), KMZ (stdlib, identity-only). Image-only pages flagged for vision (no model call yet).

### Stage 2 — Understand (merged, proven)
Deterministic toolkit (`tlddr/understand/`) + host-agent procedure. Model does comprehension/edges/section-tags; tested CLI does the deterministic work. CLI: `understand-slice`, `sections`, `understand-commit`, `understand-render`. Skills: `generate-sections` (now also captures per-section `guidance` verbatim), `understand`. Proving gate passed over all 20 docs (5 semantic clusters, honest triage, `r972` isolated).

### Stage 3 — Draft (merged + proven this session, `45856cb`)
The attributed grounded-generation stage. Built TDD across 10 tasks + a 3-finding seam-hardening fix, all reviewed (final whole-branch review by opus). See `2026-06-30-draft-stage-design.md` for the six decisions.
- **`tlddr/draft/`**: `pages.py` (`citable_pages`/`page_text` — page-addressing decision A), `read.py` (`build_read` tiered: whole if short, targeted pages + overview if large; `WHOLE_DOC_MAX_CHARS=20000`), `claims.py` (`validate_claims` — machine-trust: citations resolve to real pages, `section_id` validated, source-confidence looked up, zero-citation → finding), `eval.py` (`groundedness_readout`, `no_evidence_sections`), `verify.py` (`ingest_verdicts` — judge downgrade/contradiction → `raised_by=verify` question), `assemble.py` (`render_published` clean prose, `render_sidecar` provenance/warnings/inferences/questions).
- **CLI**: `draft-read`, `draft-commit`, `draft-verify-commit`, `draft-eval`, `assemble`.
- **Contracts** (`models.py`): `DraftClaim` (text, sources, `support_level` ∈ fully/partially/unsupported × `evidence_relation` ∈ quoted/inferred), `Citation` (node_id, page, looked-up source_confidence), `Section.guidance`.
- **Skills**: `skills/draft` (per-section draft loop), `skills/draft-verify` (independent C-lite judge).

### Stage 4 — Assemble (built as part of Draft)
`tlddr assemble --work <dir> --out <dir> --sections <f> --vault <dir>` is the pure deterministic roll-up: writes `report/report.md` (clean attributed draft) + `report/report_comments.md` (reviewer sidecar) and refreshes `vault/_triage.md` with all current questions. Output is markdown (house-style docx/PDF back end is deferred — see below).

### The Draft proving run (this session) — PASSED, eyeballed by the user
Drove `skills/draft` over the prepared engineering corpus (4 representative sections via parallel drafters reading real evidence), then `draft-eval`, the independent `skills/draft-verify` judge, and `assemble`. Result: **23 grounded claims** (16 fully / 6 partially / 1 unsupported; 18 quoted / 5 inferred). Every designed path fired on real data: machine-trust dropped an unresolvable citation → finding; low-confidence sources flagged; honest abstention (an explicit `unsupported` "no independent P50/P90 yield assessment exists" claim; a drafter declining to cite an unmappable workbook); and **the independent judge caught a genuine factual error** (a Broken Hill/N1 REZ mix-up, cross-verified against a second source) → `verify` question. Run artifacts are gitignored (`.tlddr/`, `vault/`, `report/`); regenerate via the skills.

---

## NEXT — candidate directions (all four stages exist; pick one to start)

No single "next stage" remains. The work now is hardening, broadening, and the deferred eval/output layers. Brainstorm the chosen one first (superpowers workflow). Recommended order:

**A. Harden + complete the current-corpus proving (recommended first).** Two real tooling findings the proving run surfaced, plus full coverage:
   1. **KMZ/identity docs are uncitable** — extractors that populate `pages[]` but emit no `--- page N ---` content marker make `citable_pages` return empty, so a claim citing them is dropped (it hit the AEMO GIS files). Fix: treat "pages present but no markers" as page 1 = whole content in `pages.py` (the Task-2 reviewer flagged this edge; now confirmed live). DOCX is fine because it has `pages=[]` → the page-less branch already gives it page 1.
   2. **`no_evidence_sections` conflates "no source" with "not drafted"** — on a partial run, sections with tagged nodes but no committed claims show as "insufficient evidence." Distinguish "no tagged nodes" (true abstention) from "not yet drafted."
   3. Draft the remaining 4 sections (key-technology + its type-1/type-2 children, operation-maintenance) for a complete report, then re-run end-to-end.

**B. Broaden to a new corpus.** Prep one of the new sibling filings (Chevron 10-K / CONSOL S-4 / Microsoft 10-K) through the full pipeline (`extract` → `understand` skill → `generate-sections` → `draft`). Proves cross-domain generalization (financial filings vs energy/engineering). Each needs its own work dirs — there is no "active vault"; you select by paths (e.g. `extract --source "docs/test-reports/Chevron 10-K filing" --out .tlddr/chevron`, then `--work .tlddr/chevron --vault vault/chevron`). A small `--profile <name>` deriving all paths from one name is the clean addition if juggling corpora becomes routine.

**C. Strengthen verification — build C-full.** The deferred robustness layer: ensemble the C-lite LLM-judge with a *local* deterministic NLI classifier (Vectara HHEM / AutoAIS) so faithfulness is independently machine-verified, not single-LLM-judged (FaithBench shows a lone judge is weak on hard cases). Adds `torch`/`transformers` — the only place new heavyweight deps enter.

**D. Output polish.** House-style docx/PDF rendering back end for `assemble` (currently markdown only). "Prove content first, make it pretty last" — content is now proven.

**E. Gold-comparison eval (gated).** The draft-vs-handwritten gap analysis still needs a **finished worked-example report** (none in the corpus). Groundedness/faithfulness already runs without gold (that is what the proving run exercised); the gold comparison is the missing evaluation signal.

---

## Decisions already made (do NOT re-litigate)

**Architecture** — Model = the host agent (SKILL.md = judgment, `tlddr` CLI = deterministic muscle; swap host = swap model, except the not-yet-built vision sub-path in Extract which is a programmatic seam). Deterministic/model boundary = the seams: Extract + Assemble = script; Understand + Draft reasoning = host agent. Every model output is structured data tested code validates and renders.

**The vault & node** — No content clone; the `Node` is an overlay + `extracted_id` pointer. Grounding guardrail: citations resolve to source `(node_id, page)`, never overlay text.

**Confidence & triage** — Two ordinal signals; extraction confidence script-derived, interpretation confidence LLM self-report; triage a deterministic rule, never hand-set.

**Machine-trust at every seam** — The model never gets a citation, edge, section-tag, or claim `section_id` trusted without CLI validation against a known set. Uniform across `understand-commit`, `draft-commit`, `draft-verify-commit` (verdict input hardened, commits idempotent).

**Draft (D1–D6, `2026-06-30-draft-stage-design.md`)** — (D1) section guidance is variable-richness, carried verbatim, agent adapts (bare heading → sentence → full template) + a fixed grounding/format preamble; (D2) size-tiered read, bounded + ranked escalation; (D3) two-axis `DraftClaim` (`support_level` × `evidence_relation`), citations validated, source-confidence looked up; (D4) two surfaces (`_triage.md` working / `report_comments.md` delivered) bridged by one `Question` queue, sidecar deterministically assembled; (D5) verification cascade B (deterministic readout) + C-lite (judge agent) + Human apex, C-full staged; (D6) async queue — generation never blocks, answers trigger re-passes.

**Edges** — Vocabulary `contradicts|supersedes|corroborates|references|same_subject|input_to`; agent proposes, script validates targets. Contradiction-detection escalation deferred (corpus is thematic, not adversarial).

---

## Deferred / known limitations (designed-for, not built)

- **C-full** (NLI-ensemble verification) — staged; the robustness upgrade over C-lite.
- **House-style docx/PDF output** — `assemble` emits markdown only.
- **Gold-comparison eval** — gated on a finished worked-example report.
- **KMZ/identity citability** + **`no_evidence` semantics** — the two proving-run tooling findings (direction A).
- **Vision path** (describe image-only pages) — not built; first real job is the single ISP cover thumbnail. **Contradiction-detection edges**, **content digest in nodes** — deferred. **XLSX extraction** bloated (~19 MB) + 200-row/sheet truncated — evidence-driven fix. **PDF table/multi-column** pages unverified.
- **Corpus caveat:** the engineering corpus is thematically-related public reports, not one client's project set, so per-section drafts read coherently but do not compose one project's report, and cross-document *contradiction* findings between sources can't be staged. The new filings (Chevron/CONSOL/Microsoft) are single-entity and may exercise this better.

---

## How a fresh session should start

1. Read this file. Then skim `2026-06-30-draft-stage-design.md` (Draft decisions + contracts) and `2026-06-28-tl-ddr-design.md` (overall architecture) for whichever direction you pick.
2. Read the four memory files — **decisions as issue → options×criteria → recommendation, one at a time; best-practice-first (verify via research); don't over-engineer.**
3. Superpowers workflow (user's global CLAUDE.md): `brainstorming` → `writing-plans` → `subagent-driven-development`, TDD throughout. Start the chosen direction with `brainstorming`.
4. **Environment:** Arch Linux, system Python 3.14, project venv at `.venv`. Run tests with `.venv/bin/pytest` (96 passing). Editable install (`pip install -e ".[dev]"`). Deps: pydantic, pymupdf, python-docx, openpyxl, pyyaml (+ pytest). No new deps in Draft.
5. **Re-create a working vault if needed:** `tlddr extract` over a corpus populates `.tlddr/extracted/`; `.tlddr/sections.json` exists for the engineering corpus; follow `skills/understand` then `skills/draft`. All run artifacts (`.tlddr/`, `vault/`, `report/`) and all of `docs/test-reports/` are gitignored.
6. **Git discipline:** branch off `main` for new work (don't commit to main directly — docs/handoff housekeeping excepted); conventional commits; no emojis (hard rule). TurboVault is live in `.mcp.json` (activates on session reload).

**Recommended immediate first action:** brainstorm **direction A** (harden the two proving-run findings + draft the remaining sections for a complete current-corpus report) — it is small, closes the loop the proving run opened, and leaves the pipeline fully exercised on one corpus before broadening (B) or deepening (C).
