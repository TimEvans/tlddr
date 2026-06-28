# tl-ddr — Session Handoff

**Last updated:** 2026-06-29
**Repo:** `/home/tim/Github/tl-ddr` · branch `main` at `5ab710d` · 54 tests passing

Point a fresh session at this file. It captures what's built, every design decision made (so they are not re-litigated), what's deferred, and the exact next step. Read this first, then the linked specs as needed.

---

## What tl-ddr is

A proof-of-concept that drafts **Technical Due Diligence (TDD) reports** from a pile of client source documents. The AI reads the whole document vault and drafts the report against a template, shifting the engineer's job from "read everything and write from scratch" to "review, correct, sign off." Its defining posture: **flag what it's unsure about instead of guessing** — for due diligence, an honest gap beats confident fabrication.

Name = TDD + tl;dr. The success bar: a senior engineer looks at the output and says "this genuinely saved me time, and I trust how it got there."

**The pipeline (four stages + a cross-cutting channel):**
```
Extract ──► Understand ──► Draft (per section) ──► Assemble ──► report
[done]       [toolkit done,    [not started]        [not started]
              skill next]
   │              │
   └──── Quarantine queue ◄──┘   (triage surface; both stages feed it)
```

---

## Where everything lives

| Thing | Path |
|---|---|
| Overall design spec | `docs/superpowers/specs/2026-06-28-tl-ddr-design.md` |
| Understand stage design spec | `docs/superpowers/specs/2026-06-28-understand-stage-design.md` |
| Extraction recon plan | `docs/superpowers/plans/2026-06-28-extraction-reconnaissance.md` |
| Understand toolkit plan | `docs/superpowers/plans/2026-06-28-understand-toolkit.md` |
| Extraction findings + fidelity audit | `docs/superpowers/reconnaissance-findings-2026-06-28.md` |
| Test corpus (20 source docs) | `docs/test-reports/Engineering reports test/` |
| **Report template (headings-only)** | `docs/test-reports/Engineering reports test/output_sections.md` |
| Python package | `tlddr/` (`tlddr/extract/`, `tlddr/understand/`) |
| Tests | `tests/` (54 tests) |

**Memory** (`/home/tim/.claude/projects/-home-tim-Github-tl-ddr/memory/`): user working preferences — read these.
- `brainstorm-decision-format.md` — how to present decisions (issue → options×criteria table → recommendation, one at a time).
- `dont-over-armor-controlled-systems.md` — right-size safeguards to real failure modes; don't over-engineer.

---

## What's DONE

### Stage 1 — Extract (merged, proving step passed)
`tlddr extract --source <dir> --out <dir>` routes each file by **signal type** (not extension) to a format extractor — all emitting one uniform `ExtractedDoc` record (full faithful content + page-level provenance + warnings). Verified over all 20 corpus docs: every document is identifiable from its extracted form.

- PDF (pymupdf): per-page text-layer probe; image-only pages flagged for vision + thumbnail (no model call yet).
- DOCX (python-docx, in-order body walk): prose **and tables** faithfully, in document order. (Originally mammoth — replaced after a fidelity audit found it dropped ~22% of table cells; now 100% cell coverage. mammoth dropped.)
- XLSX (openpyxl): sheet dump + messy-sheet/truncation warnings.
- KMZ (stdlib): identity only (name + placemark count, no geometry).
- The `ExtractedDoc.content` field holds the **full text** (not a snapshot) — this is the content store the rest of the pipeline reads from. Records live in `.tlddr/extracted/<id>.json`.

### Stage 2 — Understand: deterministic toolkit (merged)
The Python the Understand stage runs on (the host agent does comprehension; the CLI does everything deterministic). Modules in `tlddr/understand/`:
- `models.py` adds `Confidence`/`Triage`/`RelationType` enums, `Edge`/`Question`/`Node`.
- `slice.py` — `build_slice(doc)`: the bounded slice the agent reads.
- `confidence.py` — `extraction_confidence(doc)`: proportional, from extraction signals.
- `triage.py` — `derive_triage(...)`: the deterministic red/amber/green rule.
- `edges.py` — `validate_edges(...)`: drops edges to unknown/self targets (machine-trust).
- `node_render.py` / `render.py` — vault node markdown + `_index.md` / `_triage.md`.
- `commit.py` — `build_node(enrichment, doc, known_ids)`: assemble a validated `Node`.
- CLI: `tlddr understand-slice` / `understand-commit` / `understand-render`.

**Not done in Understand:** any model reasoning. The toolkit is proven in isolation (feed canned enrichment → get a vault). The comprehension, edge proposal, and section-tagging are the next slice.

---

## Decisions already made (do NOT re-litigate)

**Architecture / orchestration**
- **Model = the host agent.** Comprehension/edge-proposal/interpretation-confidence (and future image description) run in whatever agentic host loads the tool. The deployable unit is `SKILL.md` (judgment) + `tlddr` CLI (deterministic muscle) + MCP/TurboVault (vault ops). **Swap to Copilot = swap the host**, not a programmatic LLM client. (We explicitly rejected building an in-code `LLMClient`.)
- **Deterministic/model boundary = the seams.** Extract + Assemble = script; Understand + Draft reasoning = host agent. All deterministic helpers are tested Python.

**The vault & the node**
- **No content clone.** Faithful content lives once, in the `ExtractedDoc` store. The vault **Node is an understanding overlay + a pointer (`extracted_id`)**, never a copy. The vault markdown is a projection; content is reached through the store.
- **Node anatomy = overlay + pointer now**, with a *readable paragraph* description (so the vault is browsable). A richer model-written content **digest is deferred to phase-2** (a faithful digest of a long doc needs whole-doc reads, which reopens the bounded-slice cost). Reversible.
- **Grounding guardrail:** citations (a Draft concern) always resolve to source `(node_id, page)`, never to overlay/description text.

**Reading at scale**
- **Bounded slice + escalate.** 21M chars total (one xlsx is ~5M tokens) — the agent cannot read full content. It reads a bounded slice (title + structure + warnings + head sample). Low interpretation-confidence → quarantine. Auto-deep-read escalation is designed but deferred.

**Confidence & triage**
- Two ordinal signals (high/medium/low). **Extraction confidence is script-derived** (the LLM can't judge fidelity it didn't perform); **interpretation confidence is the LLM's self-report.** Triage is a deterministic rule: blocking question → RED; else min(ext,interp)==LOW → RED; else MEDIUM or any question → AMBER; else GREEN.

**Edges (the core value: cross-document relationships)**
- Vocabulary: `contradicts | supersedes | corroborates | references | same_subject | input_to`.
- **Design = C, build = B.** The agent proposes edges from the index of all node descriptions (20 docs fit in context); the script validates targets exist. The **contradiction-detection escalation** (content-level pair comparison) is designed but **deferred** — this corpus is thematic, not adversarial, so it has no contradictions to prove it against.

**Profile / report sections**
- The **section profile mirrors the template's richness** (lean headings → lean profile; we don't invent guidance). Produced by the model drafting a thin structured profile from the template, human-curated.
- Section-tagging is **coupled at Understand time** (for early "section X has no evidence" findings), but was **deferred in the toolkit slice** — it's the immediate next slice now that `output_sections.md` exists.

**The two Draft/Assemble outputs (recorded forward, tracking baked in)**
- Final draft produces **two artifacts**: the published document, and a per-section **reviewer sidecar** (working name `report_comments.md`) with provenance (docs referenced), warnings (low-confidence docs used), open questions, and **clarifications on logical inferences** (where the model connected dots not explicitly stated).
- This imposed upstream requirements already honoured: Node carries confidence; the draft-claim model must carry `(node_id, page)` + source-confidence + an **inference flag**; questions are section-tied. `_triage.md` is the *working* surface during a run; the sidecar is the *delivered* companion — unanswered questions flow into it.

---

## Deferred / known limitations (designed-for, not built)

- **XLSX extraction** is bloated (empty-cell pipe padding, ~19MB) and 200-row/sheet truncated — fix only when a drafted section needs the workbook (evidence-driven).
- **PDF table/multi-column pages** unverified (only a prose page was visually checked).
- **Vision path** (describe image-only pages) not built; first real job is the single ISP cover thumbnail.
- **Contradiction-detection edges** — needs an adversarial document pair to prove; the corpus has none.
- **Content digest** in nodes (phase-2), **auto-deep-read escalation** (phase-2).
- Seven minor toolkit findings logged in `.superpowers/sdd/progress.md` (all triaged DEFER by the final review) — e.g. KeyError diagnostics on malformed enrichment, a couple of untested confidence branches. None merge-blocking.

**Corpus caveat:** the 20 docs are thematically-related public energy/climate reports, not a single client's adversarial set. The new `output_sections.md` (a real TDD structure — Perimeter & Environmental / Key Technology / Energy Yield / O&M / Financial Model) **fits this corpus well**, so section-tagging is genuinely demonstrable. But cross-document *contradiction* findings can't be shown here.

---

## NEXT STEP — the Understand "skill + proving run" slice

This is where Understand comes alive end-to-end. It is a **brainstorm first** (new procedure + the profile/section-tagging design), then plan, then build. Scope:

1. **The section profile + tagging.** Turn `output_sections.md` (headings only — a deliberate *lean-profile inference* test) into a thin structured profile; have the agent tag each doc's `report_sections` against it during comprehension; surface the "section has no evidence" finding. The toolkit currently leaves `report_sections: []`.
2. **Author `SKILL.md`** — the procedure the host agent follows: per doc, `tlddr understand-slice` → comprehend + propose edges + raise questions → write enrichment JSON → `tlddr understand-commit`; after all docs, `tlddr understand-render`; then add the vault to **TurboVault** and pull coverage (isolated clusters, dead-ends, broken links) to enrich `_triage.md`.
3. **The edge-proposal pass** — the agent sees the index of all node descriptions and proposes typed edges (toolkit only *validates* them).
4. **First model-driven proving run** over all 20 docs → the **proving gate: the user eyeballs `vault/` + `_triage.md` and judges it a trustworthy map.** (Does not need the finished worked-example report — that's a Draft-stage concern and still not provided.)

**TurboVault** is installed and live (registered in `.mcp.json`, a local Rust MCP server, 44 tools). Used as the analysis/render layer over a vault the script writes — not in the write path.

---

## How a fresh session should start

1. Read this file, then skim `docs/superpowers/specs/2026-06-28-understand-stage-design.md` (the decisions in full).
2. Read the two memory files (working preferences) — **present design decisions as issue → options×criteria table → recommendation, one at a time; don't over-engineer.**
3. This work uses the **superpowers workflow** (per the user's global CLAUDE.md): `brainstorming` → `writing-plans` → `subagent-driven-development`, with TDD throughout. Start the next slice with the **brainstorming** skill.
4. **Environment:** Arch Linux, system Python 3.14, project venv at `.venv` (binary wheels confirmed working on 3.14). Run tests with `.venv/bin/pytest`. The package is installed editable (`pip install -e ".[dev]"`). Deps: pydantic, pymupdf, python-docx, openpyxl, pyyaml (+ pytest dev).
5. **Git discipline:** branch off `main` for new work (don't commit to main directly); conventional commits; no emojis anywhere (hard user rule).

The immediate first action of the next session: invoke `brainstorming` and work the "skill + section-tagging + proving run" design, one decision at a time.
