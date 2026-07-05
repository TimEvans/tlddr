# Best-practice review — brainstorm decisions log

**Date:** 2026-07-03 · **Companion to:** `docs/next-steps.md` (findings), `docs/HANDOFF.md`
**Criteria used for every decision (Reviewer):** (1) best-in-slot standard, (2) performance — generation quality *and* token usage, (3) robustness.

Compact record of the nine design decisions taken in the post-review brainstorm, so they are not re-litigated. Each spec that follows cites its decision number here. Full option/criteria reasoning was worked one problem at a time; only the settled decision + rationale is recorded.

**Cross-cutting caveat (Reviewer):** the Chevron 10-K is a convenient *public* test case, **not** representative of the corpus breadth. No decision is optimized for filings; where a filing-specific technique appears (XBRL) it is one instance of a corpus-agnostic principle.

---

## 1–4 · The shared document index (one problem, staged)

**Problem.** Two separately-framed defects are one: Understand comprehends large docs from a front-8000-char prefix (`slice.py`), and Draft re-runs retrieval per section over the same doc (81% of Chevron tokens; 26x TOC re-read). One artifact — a per-doc hierarchical index — fixes both: understand reads its top (global), draft routes to its leaves (local).

- **D1 — Treat as one document-representation problem; build the shared index, staged.** Point-fixing understand alone leaves the token prize (draft = 51% of tokens) untouched. Stage: (a) extractor captures heading provenance, (b) understand samples structure-first, (c) draft routes to leaves. Nothing throwaway.
- **D2 — Structure-*aware* tree (not structure-native): prefer the document's own outline, deterministic page/size chunk fallback where headings are thin/absent.** Corpus is heterogeneous and structure-unknown; must degrade gracefully. Each section-node carries a **route-only summary** produced as Understand's byproduct (≈free — reuses the existing per-doc comprehension budget). Depth = native outline, **no synthetic recursive levels**. **No embeddings / vector store / clustering.** Full RAPTOR (embed-cluster-summarize) explicitly **shelved**, evidence-gated — it manufactures a router where none exists; tl-ddr already has a deterministic one, so it takes RAPTOR's one useful ingredient (summaries as a semantic handle) via the cheap fallback and leaves the deps. (Note: RAPTOR's deps are not just torch — an embedding model + vector store + UMAP/sklearn clustering regardless of local-vs-hosted embeddings.)
- **D3 — Draft consumption: router-fed collapsed-tree navigation; per-section drafting default; clustering opt-in.** The deterministic router hands each drafter its section summary + candidate leaf pages *together* (collapsed-tree), killing the overview->escalate discovery. Per-section isolation stays the default (preserves attribution + honest abstention — the product's core). Clustering sections that share an evidence region into one drafter is an **opt-in mode** scoped to dense regions; a clustered drafter must still emit per-`section_id` claims. **Verify mirrors draft** (default per-section; opt-in cluster).
- **D4 — Build contract: deterministic skeleton + model summaries/tags folded into Understand; per-doc sibling artifact.** A `tlddr` step builds the skeleton (section-nodes -> leaf page ranges) from extractor headings + chunk fallback. Understand emits each section-node's route-only summary + `report_sections` tags (machine-trust validated against known ids). Persisted as `work/doc_index/<node_id>.json`. **Profile-agnostic** (skeleton + summaries, built once) kept **separable from profile-specific** (tags, recomputed per template). `Node.report_sections` survives as a derived rollup.

**Why (criteria):** best-in-slot = GraphRAG global/local split + document-summary-index pattern, structure-aware not structure-dependent; quality = kills the comprehension blind spot *and* the draft redundancy, isolation preserved; tokens = the summaries are ~free, draft discovery redundancy removed, clustering captures dense-region overlap opt-in; robustness = deterministic router (no embeddings), summaries route-only so they can never corrupt a cited claim, graceful degradation on unstructured docs.

**Prerequisite:** the HTML extractor's skipped heading inference (old design D3) closes — confirmed by the Reviewer as POC expedience, not a long-term decision.

---

## 5 · Verification — beyond a single LLM judge

**Problem.** Faithfulness rests on one generative judge (C-lite) that shares the drafter's biases and reads only the drafter's cited pages. Smoke test confirmed both failure modes: it **missed facts stated verbatim on unchecked pages** (scope) and was "right about *where* a fact lives, wrong about *what it means*" (semantics); the Reviewer had to hand-`grep`.

- **D5 — Scope-widening + NLI ensemble; claim-id anchoring already done upstream.** Three parts: (1) **widen the verifier's evidence to the section's leaf pages via the index** (not just cited pages) — fixes the false downgrades / re-cite confirmation; NLI inherits the blind spot without this. (2) **claim-id verdict anchoring** — *already implemented* by the answer-loop hardening (AD-H1/H4); dropped from this scope. (3) **NLI entailment ensemble** (Vectara HHEM or equivalent) as an orthogonal, non-generative second signal — *this is the hardening spec's out-of-scope F8b*, deliberately left for this work. **Local model preferred over a hosted entailment API** on data-governance grounds (client text stays on-box) even though it adds torch — the sanctioned dep location.

**Why (criteria):** best-in-slot = NLI is the top automatic faithfulness signal; ensembling with an LLM judge is the researched standard (a jury of LLMs adds correlated lenses, not orthogonal ones); quality = orthogonal lens attacks the exact shared drafter/judge failure mode; tokens = HHEM scoring is not LLM generation, cheapest real upgrade; robustness = reproducible fixed-weight signal, scope-fix + id-fix clear real bugs, local keeps data on-box.

**Sequence within the thread:** scope-widening (cheap, deterministic, index-dependent) -> NLI ensemble. Integrates with hardening's `(claim_id, reason)` verdict/dedup contract.

---

## 6 · Evaluation — a harvested golden set

**Problem.** No fixed yardstick: can't tell if the index, the widened scope, or the NLI threshold improved or regressed grounding. Full gold-report comparison is blocked (no worked-example report; corpus breadth means one report covers one use case).

- **D6 — Harvested claim-level golden set + small hand-labeled anchor; defer full gold-report comparison.** The answer-loop review sessions **produce labels as a byproduct** — post-hardening, re-cites are structured `draft-amend {add_pages}` records (retrieval labels), `set_text`/`set_support` are faithfulness corrections, and `QuestionStatus` carries the accept/revise call. Harvest those; measure faithfulness precision/recall of **both** the judge and the NLI signal *vs human labels*, retrieval recall (trivial with the deterministic router), and the NLI threshold's risk-coverage curve. **Defer** end-to-end completeness (gold-report) to when a worked example exists.

**Why (criteria):** best-in-slot = component-wise eval *with judge-validation-against-human* (ARES/DeepEval); reference-free-only is a rung below (unvalidated automatic metrics can be confidently wrong); quality = validates the exact signals the index + NLI fixes target; tokens = labels harvested not generated; robustness = human anchor breaks circularity, versioned + CI-gated.

**Two methodological must-dos:** (1) sample the judge's *passes*, not just its flags, or you measure precision but never recall; (2) keep corpus-agnostic and corpus-tagged (like `bench.py`) — start Chevron, never overfit to filings.

---

## 7 · Structured-fact layer (root-cause A, corpus-agnostic)

**Problem.** The drafter reads numbers from rendered prose/markdown tables (width from row[0] only; XLSX 200-row cap; structured layers discarded) -> gross-labeled-"net", definition inversion, off-by-one citations.

- **D7 — Source-agnostic structured-fact layer where a machine-readable source exists; fold in table-rendering fixes; defer VLM/table-model.** *Not* an XBRL problem — the general defect is discarding machine-readable numeric sources; it hits **spreadsheets** (the most general input) as hard as filings. Extract facts `(concept, period, unit, value, provenance)` from **XLSX cells** and **XBRL tags** into a citable fact store; facts are **citable leaves with provenance** (advances span-level attribution and **shares the index leaf model** — leaves = pages OR facts). Fold in the cheap fixes (row-width bug, XLSX read-values-only fixes bloat + cap + fidelity together). **Defer** the table-structure VLM (Option B) as evidence-gated — same bar as RAPTOR.

**Why (criteria):** best-in-slot = "prefer the structured layer", applied to the general case (spreadsheets) first, filings as a free rider; quality = removes an entire observed error class at source; tokens = compact, span-citable, fewer page re-reads; robustness = deterministic, degrades to today's behavior on bad/absent tags.

---

## 8 · Template fit (the ~40%-empty scaffold)

**Problem.** ~40% of the Chevron template rendered `_(no content drafted)_`, conflating three cases: inapplicable-to-corpus, applicable-but-unsourced (a real finding), and container headings (a rendering artifact). The honest-gap signal drowns in noise.

- **D8 — Author-declared applicability + calibration pre-pass; fold in rendering-semantics fix.** Applicability **cannot be inferred** (absence of evidence is exactly the gap to flag) — it must be **declared** by the template author as a property of the report *type* (corpus-independent). Add a `requirement` field to `SectionSpec` (required / optional / conditional); a deterministic coverage-calibration pass (reusing Understand's section tags) then renders required-but-unsourced as a finding, optional-unsourced as quiet omission, containers as structural headings, and skips drafting empty sections.

**Why (criteria):** best-in-slot = calibrated selective-generation applied to templates, general not corpus-specific; quality = biggest reader-visible jump, honest gaps made precise; tokens = skips empty-section drafting; robustness = one enum in the runtime profile + a deterministic pass, proportionate (not over-armored).

---

## 9 · Retire TurboVault as the vault seam

**Problem.** The design spec centers the vault on TurboVault, but nothing in `tlddr/` calls it; coverage is deterministic (`isolated_nodes`), edges are model-proposed, and TurboVault's graph analysis is documented-polluted (counts `_index`/`_triage` as edges).

- **D9 — Retire TurboVault as the vault seam; document the deterministic vault as the architecture.** Keep the seam *contract*, swap its implementation from the polluted MCP to the pydantic-validated write + `render.py` that already backs it. Drop the Phase-4 manual exploration. `.mcp.json` registration harmless to leave; the design must not depend on it. **Guard:** the real problem it nominally addressed — edge-recall in a corpus too large for the model's holistic pass — is genuine; if it resurfaces, solve it consistently with the architecture (the shared index's structure, or a deterministic co-occurrence signal), **not** by resurrecting the MCP. (Reviewer: "interesting to see if it's needed as the edge-candidate seed in the future" — evidence-gated follow-on.)

**Why (criteria):** best-in-slot = right-size deps to real failure modes; the vault is fully controlled (design says link rot is not a risk); quality = ends spec/impl drift; robustness = one fewer dep, no documented-wrong analysis in the loop, spec matches reality. **Concretely a doc edit** (`2026-06-28-tl-ddr-design.md` seam table + vault section) + dropping the `skills/understand` Phase-4 note; no `tlddr/` code change.

---

## Spec grouping & order

1. **Shared document index** (D1–D4) + leaf model admitting facts (D6/D7 coupling) — `specs/2026-07-03-shared-document-index-design.md`. Build first; everything keys off it.
2. **Structured-fact layer** (D7) — populates fact-leaves; plugs into the index leaf model.
3. **Verification + eval pillar** (D5, D6) — scope-widening (index-dependent) + NLI ensemble (F8b) + harvested golden set.
4. **Template applicability** (D8) — small standalone.
5. **TurboVault retirement** (D9) — doc edit.

**Global sequencing constraint:** all of the above are written against the **post-hardening contracts** (`DraftClaim.id`, `Question.claim_id`, `Question.status`, `Disposition` as input-only, `draft-amend`). The answer-loop hardening (`specs/2026-07-03-answer-loop-hardening-design.md`) merges first.
