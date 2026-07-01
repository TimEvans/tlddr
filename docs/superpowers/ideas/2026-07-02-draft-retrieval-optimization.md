# Brainstorm seed — Draft-stage retrieval optimization (separate retrieval from generation)

**Status:** pre-brainstorm brief. This is NOT an approved design. A future session should run the `superpowers:brainstorming` skill from here (issue → options×criteria → recommendation, one decision at a time; best-practice-first, verify via research) and only then write a spec.

## The problem (quantified on the Chevron run)

The Draft stage (and the draft-verify judge) **re-run retrieval independently for every section over the same large document**. On the Chevron 10-K run:

- 26 of 30 draft sections are anchored by the one 126-page 10-K.
- Each drafter's first `draft-read` returns the **126-page overview directory** (~4–5K tokens); ~26 drafters re-read it → **~100–130K tokens spent re-reading the table of contents alone.**
- Each drafter then **re-reads overlapping page content**: the 16 MD&A subsections all escalate into pages ~36–47; pages 36/39/40 were fetched by nearly every MD&A drafter.
- Result: the 16 MD&A leaves cost **~770K tokens** to draft ~12 pages of source. Draft total was 1.70M tokens; verify added 0.99M — the bulk carries this redundancy.

**Root cause:** the Draft stage **couples retrieval (find + read the right pages) into generation (draft the claims), per section, with no cross-section reuse.** The existing tiered read (`build_read`: overview→escalate) optimizes a *single* doc read (avoids dumping 599K chars) but there is no shared page→section index and no shared cache across drafters. This is the classic RAG anti-pattern: re-retrieving for every generation instead of retrieving once and generating many.

See `chevron/benchmark/CONCLUSIONS.md` (Finding 4) for the full data. Note this is a *cost/latency* problem only — quality was excellent (547 claims, 0 contradictions); do not trade away the per-section attribution or the honest-abstention behavior to fix it.

## Options already surfaced (starting point for the brainstorm, not a decision)

| Option | What it does | Redundancy removed | Cost / trade-off |
|---|---|---|---|
| **A. Cluster sections by shared evidence** | One drafter per *evidence region* instead of per section (e.g. all 16 MD&A subsections drafted by one subagent that reads pages 36–47 once; the 7 statements as another). | Both the overview re-read AND the page-content re-read for clustered sections (est. ~70–75% off the MD&A cluster). | Loses per-section isolation + per-section benchmark granularity; larger single-subagent context. Make clustering configurable (cluster for production, one-per-section for benchmarking). |
| **B. Precompute a page→section index (a "plan" step)** | One pass maps the 10-K's pages to sections up front (could be cheap/deterministic from the extractor's own captured heading markers, or one LLM pass); each drafter is *handed* its exact pages, skipping overview+escalate discovery. | The 26× directory re-read and the escalation exploration (~100–130K+). Overlapping *content* reads remain. | Adds one indexing pass; keeps one-subagent-per-section isolation (preserves attribution + benchmark granularity). RAG-correct separation of retrieval from generation. |
| **C. Shared prompt-cache prefix** | Read the shared pages once into a cached context block all drafters share (Anthropic caching → 10% input cost on cache hits). | The *cost* of re-reading (not the reads themselves) — repeated content billed at 1/10th. | Needs the orchestration/harness to share a cached prefix across subagents; the current "fresh subagent per task" model does not do this natively. Later optimization, platform-dependent. |

**Provisional lean (to be validated in the brainstorm, not adopted here):** B as the structural fix (RAG-correct, preserves isolation), with A stacked for dense clusters (MD&A) as a configurable production mode. C is cheapest to reason about but depends on a harness capability the current runtime doesn't expose. Irreducible floor: two sections that both genuinely need page 36 will each consume it once — that's fine; the fat is the ~26× directory re-read and the redundant escalation.

## Questions the brainstorm must settle

1. Where does the page→section index live and who builds it — a new deterministic `tlddr` step from the extractor's heading markers, a cheap LLM "plan" pass, or reuse of the understand-stage node tags? What is its contract?
2. Is clustering (A) a separate mode, or does the index (B) subsume the win? Measure B-alone vs B+A on the same corpus.
3. How to keep per-section attribution + the benchmark's per-section granularity if sections are clustered (A). (Emit per-section claims from a clustered drafter?)
4. Does the same optimization apply to draft-verify (the judge already reads only cited pages, so its redundancy is just the per-section overhead, not exploration)?
5. Regression guard: the fix must not weaken grounding (every claim still resolves to a real page) or honest abstention.

## Deliverables when this is picked up

`superpowers:brainstorming` → spec in `docs/superpowers/specs/` → `writing-plans` → `subagent-driven-development` (TDD, branch off main), same workflow as the HTML-extractor and benchmark-tooling slices.
