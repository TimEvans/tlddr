# tl-ddr — Draft Stage Design

**Status:** approved design, pre-implementation
**Date:** 2026-06-30
**Type:** proof-of-concept (stage 3 of 4)

The Draft stage is where the understood vault becomes a report. For each section of a
user-provided report template, the host agent gathers the source documents tagged to that
section, reads their content, and drafts the section as a list of grounded, individually-cited
claims. Deterministic Python validates every citation, aggregates groundedness signals, and
(at Assemble) projects two artifacts: the clean published report and a per-section reviewer
companion.

This is the model-reasoning half of the second model seam (Understand was the first). In
best-practice terms it is **template-driven, attributed grounded generation built on agentic
RAG**: an outline/template drives section-by-section generation (STORM), each claim carries
claim-level attribution to source pages (AIS / ALCE / Anthropic Citations API), retrieval is
size-tiered with on-demand escalation (parent-document retrieval / Self-RAG), groundedness is
verified by a judge cascade (RAGAS faithfulness), and the system abstains rather than
fabricates (Anthropic "say I don't know"). The due-diligence report is the application;
nothing in the machinery is specific to it.

---

## Where this sits

```
Extract ──► Understand ──► Draft (per section) ──► Assemble ──► report + reviewer sidecar
[done]       [done]          [THIS SPEC]            [this spec: deterministic roll-up]
                                  │
                                  └──── Quarantine queue (shared Question store) ◄── human loop
```

Carry-forward architecture (unchanged, from `2026-06-28-tl-ddr-design.md`):
- **Model = the host agent.** Drafting and verification run as `SKILL.md` procedures; the
  tested `tlddr` CLI does everything deterministic. No programmatic LLM client in this stage.
- **No content clone.** Faithful content lives once in the `ExtractedDoc` store
  (`.tlddr/extracted/<id>.json`); the vault `Node` is an overlay + `extracted_id` pointer.
- **Grounding guardrail.** Citations resolve to source `(node_id, page)` in the store, never
  to a node's description/overlay text.
- **Machine-trust at the seams.** The model never writes a citation, section tag, or edge the
  CLI hasn't validated against a known set; unknown references are dropped or quarantined.

---

## The six design decisions

### D1 — Section guidance: variable-richness, carried verbatim, agent adapts
The section profile carries whatever per-section content the user authored, at whatever
richness: nothing (a bare heading), a guiding sentence, or a full template with stub tables,
figure placeholders, and bullets-to-address. The model adapts — a bare heading is inferred
against from the heading path + tagged nodes; a full template is treated as both the output
skeleton to fill **and** the checklist to address. We neither invent guidance the user did not
give, nor flatten a rich template.

- **Implementation:** `Section` gains an optional `guidance: str | None` holding the user's
  verbatim per-section content (markdown, so a stub table survives intact). `generate-sections`
  grows to preserve each section's *body* content, not just lift the heading.
- **Best-practice floor (refinement):** a bare heading is below the vendor-guide floor (be
  explicit about grounding + format). So every section draft is wrapped in a fixed
  **system-level grounding+format preamble** the template need not restate: ground only in
  provided context, cite every claim, a default structural expectation when guidance is thin,
  and a clear "done" definition.
- *Patterns:* STORM outline-then-write; LlamaIndex template-to-executable-plan; WriteHERE
  adaptive planning.

### D2 — Read strategy: size-tiered, with bounded + ranked escalation
Understand read only bounded slices. Draft must read the **real content** of a section's
tagged nodes to write citable claims. Strategy:
- **Short docs are read whole.** Large docs (the 137-page ISP, the 19 MB xlsx) are served as a
  **relevance-targeted page set**, never the whole document by reflex.
- **On-demand escalation (auto-deep-read):** the model may pull specific additional pages of a
  tagged node when a section needs them. Escalation is **bounded (a cap) and relevance-ranked**
  — never "load the whole large doc."
- The whole/targeted cutover is a tunable size threshold (page/char count), settled in proving.
- *Patterns:* Anthropic whole-corpus-under-threshold vs retrieve-above; parent-document
  retrieval (page = the parent granularity, giving clean provenance); Self-RAG agentic
  escalation. Guardrails forced by Lost-in-the-Middle and long-context saturation.

### D3 — DraftClaim: two orthogonal attribution axes
Output is an **ordered list of `DraftClaim`s** per section — each a single assertion bundled
with its provenance. The published prose is the claim texts concatenated; the reviewer sidecar
is rolled up from the claims' metadata. Each claim carries **two independent axes** (collapsing
them into one flag is lossy):
- **`support_level`** — *how strongly* the cited page backs the claim:
  `fully_supported | partially_supported | unsupported`. The safety axis (drives sidecar
  warnings + faithfulness eval). Three-way because binary cannot represent *partial* support.
- **`evidence_relation`** — *how* the claim derives from the source:
  `quoted` (extractive) | `inferred` (abstractive). The "logical inference" signal surfaced
  beside the report.
- The model declares only what it alone knows (text, citations, both axes). The **script
  derives** each cited node's source-confidence by lookup (the model never self-grades source
  trust) and **validates** every `(node_id, page)` resolves to a real page; unknown/out-of-range
  citations are dropped, and a claim left with zero valid citations becomes a finding (no orphan
  assertions).
- *Patterns:* AIS ("Attributable to Identified Sources"); ALCE citation precision/recall;
  FActScore (atomic claim unit licenses a per-claim label); TREC 2024 RAG support scale;
  Anthropic Citations API `(document, page_location)`.

### D4 — Reviewer sidecar: two surfaces, one shared queue
Two review surfaces sit on different axes and are not substitutes:
- **`_triage.md`** — node-centric, the run's *working* answer-surface (Understand + Draft):
  triage groups, coverage, isolated docs, open questions with answer slots (where the human
  answers).
- **`report_comments.md`** — section-centric, the *delivered* companion beside the report.
  Per section: provenance (every doc cited), warnings (low `support_level` / low-confidence
  sources leaned on), inferences (claims flagged `evidence_relation=inferred`), and the open
  questions blocking the section. A section with no source emits an explicit "insufficient
  evidence" entry (abstention).
- The sidecar is **deterministically assembled** (the model never writes it) at Assemble time
  from the validated `DraftClaim` metadata + the section-tied questions.
- **Bridge:** the single `Question` quarantine queue. One question, raised once, surfaces in
  both — in `_triage.md` to be answered, in the section's sidecar to inform the reviewer.

### D5 — Verification: a three-tier judge cascade, each tier rationing the next
Groundedness is verified by a cascade; automated judges exist to ration the expert's attention,
not replace it.
- **Tier B — deterministic readout (built now):** aggregate the validated claims —
  citation-validity rate, `support_level` histogram, unsupported/partial counts, `inferred`
  fraction, no-evidence/thin sections. Free, deterministic, repeatable. Catches structural
  defects and surfaces the drafter's self-report. *Limitation:* trusts the self-declared
  `support_level`; cannot catch a confident fabrication.
- **Tier C-lite — independent judge agent (built now):** a second, independent host-agent pass
  re-checks each claim's `text` against its cited page content and renders its own verdict.
  Catches drafter overclaims and source contradictions. Zero new dependencies — same host-agent
  seam as the rest of the pipeline. Disagreements (drafter says `fully_supported`, judge
  disagrees; source contradictions; no-evidence) become `Question`s (`raised_by=verify`) into
  the shared queue.
- **Tier Human — domain expert (apex):** the authoritative judge, with **rationed attention** —
  reviews only what B + C-lite surface, via `_triage.md` + the sidecar; answers trigger targeted
  re-passes.
- **C-full (staged next, not built):** ensemble C-lite's judge with a *local* deterministic NLI
  classifier (Vectara HHEM / AutoAIS) for robustness — FaithBench shows a single LLM judge is
  weak on hard cases. Deferred because it adds an ML dependency (`torch`/`transformers` + model
  weights) and B + C-lite + human review is a sound v1 checkpoint.
- This **is** RAGAS faithfulness, specialized: RAGAS decomposes-then-verifies; we already emit
  the atomic decomposition (the claim list), so faithfulness collapses to the per-claim verify.
  Crucially it needs **no gold report**, so it runs now and sidesteps the "no worked example yet"
  blocker. This cascade is the Draft **proving gate**.
- *Patterns:* RAGAS faithfulness; TruLens RAG triad; FActScore / SAFE; Vectara HHEM; FaithBench;
  selective-escalation human-in-the-loop.

### D6 — Human review interaction model: async queue (generation never blocks)
The non-negotiable principle: **generation never blocks on the human.** Drafting runs to
completion and produces draft + sidecar + a surfaced question queue; the expert reviews
**asynchronously** when ready; answered questions trigger **targeted re-passes** of the affected
sections (mechanism already designed and proven in Understand's `_triage` answer-slot loop).
The "key questions in front of the user, brainstorm-style" experience is honored by an optional
interactive **review session** over the surfaced queue — but architecturally review is
decoupled and resumable, which is what scales to a large vault. Interactive-blocking mid-run is
explicitly rejected (does not scale, hard to resume).

---

## Data contracts

New and changed pydantic models (in `tlddr/models.py` unless noted):

```python
class Section(BaseModel):                  # CHANGED: + guidance
    id: str
    title: str
    parent: str | None = None
    guidance: str | None = None            # verbatim per-section template content (markdown)

class SupportLevel(str, Enum):             # NEW — how strongly the source backs the claim
    FULLY_SUPPORTED = "fully_supported"
    PARTIALLY_SUPPORTED = "partially_supported"
    UNSUPPORTED = "unsupported"

class EvidenceRelation(str, Enum):         # NEW — how the claim derives from the source
    QUOTED = "quoted"                      # extractive: on the page
    INFERRED = "inferred"                  # abstractive: synthesized / dots connected

class Citation(BaseModel):                 # NEW
    node_id: str
    page: int
    source_confidence: Confidence | None = None   # DERIVED by the script at validation (lookup)

class DraftClaim(BaseModel):               # NEW — the atomic unit of drafted output
    section_id: str
    text: str                              # one assertion (model writes)
    sources: list[Citation]                # >= 1 after validation; else -> finding
    support_level: SupportLevel            # model declares
    evidence_relation: EvidenceRelation    # model declares

class Question(BaseModel):                 # UNCHANGED shape; raised_by gains "verify"
    # raised_by now one of: understand | draft | verify
    ...
```

Notes:
- The model emits each `DraftClaim` with `text`, `sources` (as `(node_id, page)`),
  `support_level`, `evidence_relation`. The script populates `Citation.source_confidence` with
  the cited node's `confidence_interpretation` (the "do I understand what it means" signal —
  the one most relevant to whether a claim resting on the source can be trusted) and validates
  page existence. The sidecar raises a warning when a claim leans on a node with low
  interpretation confidence **or** the claim's own `support_level` is partial/unsupported.
- `Question.raised_by` is a free `str` today, so adding `"verify"` needs no model change — only
  documentation and producer code.

---

## Stage flow (per section, script-orchestrated)

For each `Section` in the active `sections.json`:

1. **Gather** the nodes tagged to the section (`report_sections` contains the section id).
   No inbound nodes → emit an "insufficient evidence" `Question` (`raised_by=draft`,
   `section_id` set, `node_id=None`) and skip drafting.
2. **Read** (D2): the CLI serves each tagged node's content — whole if short, a
   relevance-targeted page set if large — from the `ExtractedDoc` store. The agent may escalate
   to additional bounded, ranked pages.
3. **Draft** (D1 + D3): the agent drafts the section against its `guidance` (+ the fixed
   grounding/format preamble), emitting an ordered list of `DraftClaim`s.
4. **Commit** (D3): the CLI validates every citation resolves to a real page, attaches
   source-confidence, drops invalid citations, turns zero-citation claims into findings, and
   persists the validated claims.
5. **Verify** (D5): Tier B readout is computed deterministically; the C-lite judge skill runs an
   independent pass and the CLI ingests its verdicts, raising `raised_by=verify` questions on
   disagreement.
6. **Assemble** (deterministic, stage 4): roll the validated claims up into the **published
   draft** (claim texts in order) and the **reviewer sidecar** (`report_comments.md`, from claim
   metadata + section-tied questions). Re-render `_triage.md`.
7. **Human review** (D6, async): the expert works the surfaced queue; answered questions trigger
   targeted re-drafts of the affected sections.

---

## CLI and skill surface

Deterministic CLI (tested Python; exact signatures fixed in the plan):
- `tlddr draft-read --extracted <dir> --id <node> [--pages <range>]` — serve a node's content
  for drafting: whole if under the size threshold, else the requested/targeted pages. The
  gatekeeper of what content the model sees.
- `tlddr draft-commit --claims <f> --section <id> --extracted <dir> --out <dir>` — validate the
  agent's `DraftClaim`s (citations resolve, axes valid, zero-citation → finding); persist
  validated claims; emit `raised_by=draft` questions for empty/thin sections.
- `tlddr draft-verify-commit --verdicts <f> --work <dir>` — ingest C-lite judge verdicts;
  raise `raised_by=verify` questions on disagreement.
- `tlddr draft-eval --work <dir>` — the Tier-B deterministic groundedness readout.
- `tlddr assemble --work <dir> --sections <f> --out <dir>` — produce the published draft +
  `report_comments.md` sidecar; re-render `_triage.md`.

Host-agent procedures (`skills/`):
- `skills/generate-sections/SKILL.md` — CHANGED: now also preserves each section's body content
  into `Section.guidance`.
- `skills/draft/SKILL.md` — NEW: per-section drafting (gather → `draft-read` → draft as claims
  against guidance + preamble → `draft-commit`).
- `skills/draft-verify/SKILL.md` — NEW: the C-lite independent judge (read each claim + its
  cited page, render a `support_level` verdict, emit disagreements).

Deterministic/model line (carry forward): the model drafts + judges; tested Python validates
citations, derives confidence, aggregates groundedness, detects empty/thin sections, and
orchestrates section-by-section. Assemble is pure deterministic roll-up.

---

## Proving approach (the Draft gate)

Run the full stage over the existing 20-doc corpus and the curated `sections.json`:
1. Draft every section → validated `DraftClaim`s; published draft + sidecar assembled.
2. **Tier B** readout: citation-validity 100% (no unresolved citations escape), a sane
   `support_level` distribution, the `inferred` fraction is plausible, no-evidence sections are
   correctly flagged.
3. **Tier C-lite**: the independent judge runs; disagreements surface as `raised_by=verify`
   questions in `_triage.md` + sidecar.
4. **Human-eyeball**: the draft reads coherently, every claim is traceable to a real page, and
   the sidecar honestly lists provenance, warnings, and inferences per section.

Faithfulness (groundedness) is measurable here **without a gold report**. The
draft-vs-handwritten gold comparison remains gated on a finished worked example (carried-forward
limitation), but it is not required to prove the stage produces grounded, honest output.

---

## Deferred / staged (designed, not built)

- **C-full** — ensemble the C-lite judge with a local NLI classifier (Vectara HHEM / AutoAIS);
  adds `torch`/`transformers` + weights. The robustness upgrade once B + C-lite + human review
  is proven.
- **Interactive (blocking) review** — explicitly rejected for the async model; revisit only if
  a real workflow demands live mid-run answers.
- **Gold-comparison evaluation** — gated on a finished worked-example report.
- Whole-doc **content digest** in nodes (phase-2); **contradiction-detection edges** (needs an
  adversarial pair); **vision path** for image-only pages — all carried forward from prior specs.

---

## Best-practice references

- Attribution: AIS — Rashkin et al., *Computational Linguistics* 2023; ALCE — Gao et al., EMNLP
  2023; FActScore — Min et al., EMNLP 2023; Attributed QA (extractive vs abstractive) — Bohnet
  et al.; TREC 2024 RAG track (3-way support scale); Anthropic Citations API.
- Retrieval: Anthropic Contextual Retrieval (threshold + ranking); parent-document retrieval;
  Self-RAG / agentic retrieval; Lost-in-the-Middle (Liu et al., TACL 2024).
- Generation: STORM (Stanford); LlamaIndex report-generation building blocks; WriteHERE.
- Faithfulness eval: RAGAS (faithfulness, context precision/recall); TruLens RAG triad; SAFE /
  LongFact (DeepMind); Vectara HHEM; FaithBench; RAGTruth.
- Abstention: Anthropic "reduce hallucinations / say I don't know"; Confidence-Aware RAG;
  AbstentionBench.
