# Shared Document Index — Design

**Status:** approved design, pre-implementation
**Date:** 2026-07-03
**Type:** proof-of-concept — structural change to how Understand and Draft see a document
**Decisions:** implements D1–D4 of `docs/superpowers/2026-07-03-review-decisions-log.md`; defines the leaf model D7 (structured facts) plugs into and D5 (verify scope) consumes.

A per-document **hierarchical index**, built once, that both Understand and Draft read — Understand reads its top (a global view of the whole doc), Draft routes to its leaves (the exact evidence pages for a section). One artifact fixes two currently-separate defects: Understand's front-8000-char comprehension prefix and Draft's per-section retrieval redundancy (81% of Chevron tokens). It also gives the verifier the correct evidence scope. The router is **deterministic** — no embeddings, no vector store, no clustering.

---

## Problem

Two defects, one root — the pipeline has **no shared representation of a document's structure**:

- **Understand** comprehends each large doc from `slice.py::build_slice` = `doc.content[:8000]` + the first 60 markers. On a large doc it forms `description`, `report_sections` tags, and edges from ~the first 1,500 words, blind to everything later. Cost is flat ~22K/doc *because* the sample is capped.
- **Draft** re-runs retrieval independently per section: each drafter re-reads the whole-doc overview (~26x the same directory on Chevron) and re-escalates into overlapping pages, with no shared index or cache. This is the classic RAG anti-pattern — re-retrieving per generation instead of retrieving once.
- **Verify** (consequence) reads only the drafter's cited pages, so it cannot confirm a fact that lives one page over — the smoke test's observed false-downgrade / failed-re-cite mode.

The fix is a single per-doc index whose **top** serves Understand's global query and whose **leaves** serve Draft's and Verify's local queries — the GraphRAG global/local split, made deterministic because tl-ddr already knows the query's target (a named report section) and Understand already produces a `report_section -> node` mapping.

---

## Design decisions

### SI-1 — One index, three consumers, staged build
The index is the single document-representation artifact. Understand reads section-node summaries (global); Draft routes by report-section to a section's leaves (local); Verify is handed the same leaves. Staged so nothing is throwaway: (a) the extractor captures heading/section provenance; (b) Understand samples structure-first from the skeleton; (c) Draft/Verify route to leaves. Steps (a)+(b) are the immediate comprehension-quality win; step (c) is the token prize.

### SI-2 — Structure-aware tree with a deterministic chunk fallback
Nodes are formed from the document's **own heading/section structure where it exists**, and from **deterministic page/size segmentation where it does not** (heterogeneous corpus; must degrade gracefully — no document may collapse to bare page numbers, today's failure). **Leaves are always raw** (a page, or — via the fact layer — a fact with provenance). Each non-leaf section-node carries a **route-only summary**. Depth = the document's native outline; **no synthetic recursive summary levels** (a deterministic router needs no level-by-level drill-down — RAPTOR's collapsed-tree finding). **No embeddings, no vector store, no clustering.** Full RAPTOR is shelved (D2), evidence-gated.

### SI-3 — Deterministic router + collapsed-tree presentation
Routing is a direct lookup: `report_section -> {section-nodes tagged with it, across all docs} -> their leaves`. No similarity, no top-k. Draft receives its section's **route-only summary and candidate leaves together** (collapsed-tree presentation), replacing the overview->escalate round-trip. **Grounding invariant (unchanged):** a claim cites a **raw leaf** (page or fact), **never a summary node** — summaries route and comprehend only, so a wrong summary can mis-route but can never corrupt a cited claim.

### SI-4 — Draft/Verify consumption
Draft default = **one drafter per section**, router-fed (preserves per-section isolation, attribution, honest abstention). **Clustering** sections that share an evidence region into one drafter is an **opt-in mode** for dense regions; a clustered drafter must still emit per-`section_id` claims (preserves the machine-trust commit + per-section benchmark). Verify mirrors this default/opt-in, and — the D5 scope-fix — the verifier (and any NLI signal) is handed **the section's leaves**, not merely the drafter's cited pages.

### SI-5 — Build split along the existing deterministic/model seam
- **Deterministic `tlddr` step** builds the **skeleton** — section-nodes with leaf page ranges — from the extractor's heading provenance, with the page/size chunk fallback. No model.
- **Model (the Understand pass)** emits, per section-node, a **route-only summary** and the **`report_sections` tag(s)** — the natural output of restructuring Understand's existing per-doc comprehension as map-reduce over sections (so the summaries are ~free, not a new stage). The CLI validates tags (machine-trust, against known section ids), same as `understand-commit`.

### SI-6 — Persistence: per-doc sibling artifact, profile split
Persisted as `work/doc_index/<node_id>.json` (matches the existing separate-store pattern; keeps `Node` lean). Each section-node carries: leaf refs (page range and/or fact refs), route-only summary, and `report_sections: list[SectionId]`. The **profile-agnostic** part (skeleton + summaries — describes the document, built once) is kept **separable from the profile-specific** part (tags — recomputed cheaply on a re-profile). `Node.report_sections` becomes a **derived rollup** (union of its section-nodes' tags) for coverage/back-compat; the fine-grained truth lives in the index.

---

## Data contracts

New artifact, keyed by the existing `node_id`. Leaf refs are a **discriminated union** so the structured-fact layer (D7) populates fact-leaves without a second index shape.

```python
class LeafRef(BaseModel):                 # a raw, citable evidence unit
    kind: Literal["page", "fact"]
    page: int | None = None               # kind == "page"
    fact_id: str | None = None            # kind == "fact" (into the fact store; D7)
    # grounding invariant: a claim cites a LeafRef, never a DocSection

class DocSection(BaseModel):
    section_node_id: str                  # stable within the doc; scheme settled in planning
    title: str                            # native heading text, or a fallback label
    parent_id: str | None = None          # native outline depth; None at top
    leaves: list[LeafRef]                 # raw evidence under this section
    route_summary: str                    # Understand byproduct; route/comprehend only
    report_sections: list[SectionId] = [] # profile-specific tags (machine-trust validated)
    origin: Literal["native", "fallback"] # heading-derived vs deterministic chunk

class DocIndex(BaseModel):
    node_id: NodeId
    source_sha256: str                    # rebuild trigger; ties to the ExtractedDoc
    sections: list[DocSection]            # the document's outline (native or fallback)
    built: Literal["skeleton", "enriched"]# skeleton = deterministic only; enriched = + summaries/tags
```

Consumers:
- **Understand** reads each `DocIndex`'s section skeleton to sample **structure-first** (replacing `build_slice`'s prefix), and writes back `route_summary` + `report_sections` (the `built: enriched` transition).
- **Draft** (`draft-read`): router resolves a report-section -> `DocSection`s tagged with it -> their `leaves`; returns `(route_summary, leaf content)` together.
- **Verify** (`draft-verify` / any NLI signal): same router resolves the section's leaves as the evidence scope.

Unchanged contracts it keys off: `ExtractedDoc` (content store), `Node` (overlay; `report_sections` now derived), `Citation(node_id, page)` — extended to reference a `LeafRef` as the fact layer lands.

---

## Prerequisites, dependencies, ordering

1. **Extractor heading provenance.** The HTML extractor's skipped heading inference (old design D3) must close — the skeleton needs section/heading boundaries, not just `--- page N ---`. Confirmed by the Reviewer as POC expedience, not doctrine. Where heading provenance is still thin/absent, SI-2's chunk fallback covers it.
2. **Post-hardening contracts.** Written against `DraftClaim.id`, `Question.claim_id`, `Question.status`, `draft-amend` (`specs/2026-07-03-answer-loop-hardening-design.md` merges first). The index does not touch claims directly — the router feeds Draft, which produces claims under the hardened contract — so the coupling is ordering, not shape.
3. **Fact layer (D7).** `LeafRef(kind="fact")` is defined here but **populated** by the structured-fact spec. Until that lands, all leaves are `kind="page"`; the union is forward-compatible.

---

## Out of scope (separate specs)

- **Structured-fact extraction (D7)** — XLSX/XBRL fact store that fills fact-leaves; this spec only reserves the leaf shape.
- **Verification NLI ensemble + eval (D5 item 3, D6)** — this spec delivers only the D5 *scope-widening* (handing Verify the section's leaves); the NLI signal and golden set are their own pillar.
- **Template applicability (D8)** and **TurboVault retirement (D9)** — unrelated to the index.
- **Full RAPTOR (embed-cluster-summarize)** and **edge-candidate seeding** — shelved, evidence-gated.

---

## Testing approach

- **Skeleton build:** native headings -> a `DocSection` per heading with correct leaf page ranges and `parent_id` outline; a doc with no/thin headings -> deterministic chunk fallback (`origin: fallback`), never bare page numbers.
- **Enrichment:** Understand writes `route_summary` + validated `report_sections`; unknown section tags dropped (machine-trust), same as `understand-commit`.
- **Router determinism:** a report-section resolves to exactly the leaves of the `DocSection`s tagged with it, across docs; stable across runs.
- **Collapsed-tree read:** `draft-read` returns `(route_summary, leaf content)` for a section without an overview->escalate round-trip; the 26x-overview redundancy is gone (assert a single directory read per section, not per drafter).
- **Grounding invariant:** a claim's citation resolves to a `LeafRef` (page/fact), never a `DocSection` summary.
- **Understand structure-first:** the comprehension sample draws from the whole outline, not `content[:8000]` (assert coverage of a late section on a large fixture).
- **Profile split:** re-tagging under a new profile recomputes `report_sections` **without** rebuilding skeleton/summaries; `Node.report_sections` derives as the union rollup.
- **Verify scope:** the judge/NLI evidence set for a section = the section's leaves (a fact one page beyond the drafter's citation is now in scope).

---

## Open questions for planning

1. **`section_node_id` scheme** — stable, deterministic, collision-safe within a doc; how the fallback names its synthetic sections (the router keys on these ids).
2. **Persistence split** — one `doc_index` file with a regenerated tag block over a cached skeleton, vs two files (profile-agnostic + profile-specific). Trade simplicity vs re-profile cost.
3. **Structure-first sample budget** — how Understand bounds what it reads from the outline (per-section snippet size / total budget) so comprehension stays cheap while covering the whole doc.
4. **`LeafRef`/`Citation` reconciliation** — exact citation anchor once facts are leaves; coordinate the shape with the D7 fact-layer spec so `Citation` extends cleanly rather than forking.
5. **Clustering mode mechanics** — how a clustered drafter emits per-`section_id` claims and how the router groups a dense region; measure index-alone vs index+clustering to confirm the opt-in is worth its complexity.
