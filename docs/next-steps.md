# tl-ddr — Best-practice review & next steps

**Date:** 2026-07-03 · **Companion to:** `docs/HANDOFF.md`
**Scope:** first full-pass architecture review of all four stages + the answer loop against 2024–2026 RAG / attributed-generation research, cross-checked against the Chevron 10-K proving run.

This is the **findings + prioritized next-steps** doc. The block-by-block design brainstorm that follows from it lives in `docs/superpowers/` (specs/ideas), one decision at a time.

---

## Headline

The stack is **trustworthy and its most contrarian bet is validated.** On the Chevron 10-K: 547 claims, 100% cited, **0 fabrications, 0 contradictions**, honest abstention held end-to-end. Its biggest gamble — a **deterministic `section → node → page` router with no embeddings / vector store** — is what current practice recommends for a *known, bounded corpus* (cf. Anthropic dropping vector RAG from Claude Code for agentic retrieval). That is a decision to defend, not a gap.

The shortfalls are **concentrated, mostly cheap, and share two upstream root causes.** Nothing here is a rewrite.

---

## Block-by-block scorecard

| Block | vs best practice | Key gap | Next step (size) |
|---|---|---|---|
| **Extract** | Behind on financials | iXBRL/XBRL facts discarded — numbers re-read from rendered prose; 29/55 Chevron records 0-page; ragged-table width from row[0] only; vision path dead-flagged | Harvest XBRL tags as structured citable facts (M) |
| **Understand** | Behind — *clearest defect* | Front-8000-char prefix for whole-doc comprehension (`slice.py`); never samples past ~1.5K words → blind to risk factors, MD&A, notes | Map-reduce over the existing section map (**L**) |
| **Draft** | In-line / ahead | Per-section re-retrieval, no shared index (81% of tokens); retrieval = tag-membership only, no fallback | Shared page→section index / cluster MD&A (B-opt) (M) |
| **Verify** | **Behind — most consequential** | Single LLM judge, single pass, verdicts matched by fragile list-index; only catches downgrades | NLI check (Vectara HHEM) beside C-lite (**L**→M) |
| **Assemble** | Fine (deferred polish) | Space-join claims, no smoothing; clean `report.md` has no inline citations | Cosmetic; defer per "content first" |
| **Answer-loop** | Reasonable | Convergence is a raw counter; grounding guardrail skill-level only | Fine for now |
| **Attribution** | In-line, edging ahead | Page-level anchor coarser than span/sentence SOTA; no ALCE precision/recall metric | Span anchors + citation P/R (L) |
| **Eval** | Behind | No golden set, no component-wise eval, judge never validated vs human | Small versioned golden set in CI (M) |

---

## Chevron shortfalls — two upstream root causes

**Root cause A — the drafter reasons from rendered prose + partial context** (XBRL discarded + front-prefix comprehension):
- Gross-vs-net labeling error (verify-24: gross treasury repurchases labeled "net").
- Definition inversion (verify-513: "net of" where source says "net includes").
- Citation off-by-one — figure right, cited to the entry page not the fact page (5 of 19 questions).
- "Add a cause" over-reach — attributing 2025 changes to the Hess acquisition when the cited page is silent (7 of 19 questions).

**Root cause B — a single judge** can flag these as "partial" but can't independently confirm them with authority. The verification weak point for a high-stakes product.

**Separate, product-level — template fit:** ~40% of the 42-section annual-report template rendered `_(no content drafted)_` on a 10-K. Honest, but reads as empty scaffold. Parent/container headings (MD&A, Financials) render empty while children carry content — `no_evidence` semantics conflate "no source" / "not drafted" / "container heading."

**Cost:** 3.3M tokens, 81% in draft+verify, bulk re-reading the same 10-K TOC 26× + overlapping pages (the retrieval redundancy already quantified in `chevron/benchmark/CONCLUSIONS.md` Finding 4 and seeded in the B-opt brief).

---

## Low-hanging fruit (ranked ROI/effort)

1. **Kill the front-8000-char comprehension prefix** → map-reduce summaries over the `section → node → page` map that already exists. No new deps; removes a systematic blind spot; it is half of the B-opt hierarchical-index brief. Cheapest high-impact fix in the system.
2. **Add an NLI faithfulness check (Vectara HHEM / entailment) beside C-lite** — cheap, non-generative second signal, different failure modes. This is the deferred "C-full"; literature (FaithBench, PoLL) says a lone judge is the real risk.
3. **Harvest iXBRL/XBRL facts as structured citable numbers** — already ingesting the iXBRL; parsing the tags kills the gross/net + off-by-one class at the source.
4. **Fix the two known tooling edges** (HANDOFF direction A): KMZ/identity citability; split `no_evidence` into no-source / not-drafted / container-heading (fixes the empty-parent-heading rendering).

**Bigger lifts (structural, partly scoped):** the shared hierarchical index (B-opt — fixes draft redundancy *and* the understand prefix in one artifact); a golden-set eval harness; template-fit (prune/map the template to what a source can actually feed).

---

## Architecture drift found (not previously recorded)

**The designed "vault seam" (TurboVault) is bypassed.** Registered in `.mcp.json` and central to the design spec (its `suggest_links`/`recommend_related` structural candidates + coverage tools), but **nothing in `tlddr/` calls it.** Edges are all model-proposed with only referential validation; isolation/coverage is deterministic in `render.py`. Decision owed: formally retire it from the design, or wire it back as the cheap structural-candidate seed it was meant to be.

---

## Net

In-line to ahead on architecture and attribution; behind on verification rigor and whole-doc comprehension. The single cheapest fix (the comprehension prefix) is also one of the highest-impact.

**Brainstorm criteria (per Reviewer, 2026-07-03):** weigh every option against — (1) best-in-slot standard, (2) performance: generation quality *and* token usage, (3) robustness. One problem at a time; clear problem statement + tensions first, then a criteria-based recommendation.
