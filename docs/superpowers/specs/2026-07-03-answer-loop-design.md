# tl-ddr — Answer Loop (D6) Design

**Status:** approved design, pre-implementation
**Date:** 2026-07-03
**Type:** proof-of-concept (the cross-cutting Quarantine-queue answer loop; closes the first pass)

The answer loop turns tl-ddr's one-shot forward pass into a review cycle. Today questions
accumulate from understand/draft/verify into one `questions.json` and render into `_triage.md`
and `report_comments.md` with `> answer:` slots — but nothing ingests an answer or acts on it
(`Question.answer` is a slot nothing consumes; there is no CLI). This spec adds the one remaining
designed-but-unbuilt seam: a validated ingestion point where an answered question feeds back,
routes to the stage that can act on it, triggers a scoped re-pass with the answer as guidance,
and terminates idempotently. It makes the tool's defining posture — **review → correct → sign
off** — actually actionable.

In best-practice terms this is standard **human-in-the-loop (HITL)** for a RAG pipeline: the
generator runs to completion and writes to a review queue; a reviewer works the queue
asynchronously; approved answers gate a targeted re-pass — a **review/execution gate, not a
generation gate** (the dominant production pattern; blocking generation is explicitly avoided for
its overblocking/latency cost). Nothing here is specific to due diligence.

---

## Where this sits

```
Extract ─► Understand ─► Draft (per section) ─► Verify ─► Assemble ─► report + reviewer sidecar
                │            │                     │
                └──── Quarantine queue (one Question store) ◄──── THIS SPEC: the answer loop
                                    │
   open questions ─► review-session skill ─► answer-commit ─► worklist ─► re-pass ─► re-assemble
```

Carry-forward architecture (unchanged): model = the host agent; the tested `tlddr` CLI does
everything deterministic; no content clone (citations resolve to source `(node_id, page)`);
**machine-trust at every seam** — the CLI validates every ingested answer against the known
question set, exactly as `understand-commit` / `draft-commit` / `draft-verify-commit` validate
their inputs.

**Terminology:** the human in the loop is the **Reviewer** (tl-ddr is general-purpose, not
scoped to engineering due diligence).

---

## The five design decisions

### AD1 — Ingestion: one validated `answer-commit` seam, both routes converge (source-agnostic)

Answers are ingested through a single deterministic CLI seam, `answer-commit`, which takes
**structured answer records** and validates them like every other seam. Two producers converge on
it:

- **The interactive review-session skill** (the primary, recommended human path — see AD-Skill).
- **A future retrieval agent** that answers a question from the corpus, producing the same
  records.

A **lightweight fallback** lets a Reviewer hand-fill the existing `> answer:` markdown slots in
`_triage.md` with a leading `[revise]` / `[accept]` tag; a parser converts filled slots into the
same answer records. The seam is source-agnostic; the record contract is the contract.

- *Rejected:* markdown-slot-only (a future agent would have to edit markdown); structured-only
  (worst reviewer ergonomics). Both-routes-converge keeps one validated seam with good ergonomics.
- *Best practice:* the production HITL pattern — generate → review queue → validated commit on
  approval.

### AD2 — Routing: by `raised_by`, cascade surfaced (not automatic)

An answered question routes to the stage that produced it:

| `raised_by` | target field | acts on | re-pass |
|---|---|---|---|
| `understand` | `node_id` | the node | re-understand the node (answer as guidance) |
| `draft` | `section_id` | the section | re-draft the section |
| `verify` | `section_id` | the section (a claim in it) | re-draft the section |

**Cascade:** re-understanding a node can change its section tags (move it from section X to Y).
That means X and Y now need re-drafting — but the re-drafts are **surfaced as suggested
follow-ups, not run automatically**. The Reviewer stays in control of the fan-out.

- *Rejected:* route by target-field presence (loses the *why*); reviewer picks target each time
  (pushes derivable routing onto the human). `raised_by` is already set by every producer, so
  routing is a deterministic lookup with no new model judgment.
- *Best practice:* HITL "route feedback to the component that produced it" (RAGOps). Automatic
  transitive re-drafting is the overblocking trap; surfacing is right-sized.

### AD3 — Re-pass trigger & scoping: batched deduped worklist, answer-as-guidance, always re-verify

- **Trigger:** batched, **after** the review session — never mid-answer (D6: generation never
  blocks). `answer-commit` resolves the batch and writes a **deduped re-pass worklist** keyed by
  target. Multiple questions on one section collapse to a single re-draft (the Chevron 19 verify
  questions become the handful of distinct sections they touch).
- **Answer-as-guidance (grounding guardrail):** the answer reaches the re-pass as a
  **CLI-rendered guidance block** attached to its section/node. The drafting skill reads it as
  *instruction*; citation validation in `draft-commit` is unchanged. An answer can say "the
  causal link is correct — keep it, cite p.47," but it can **never itself be a citation**. Claims
  still resolve to a real `(node_id, page)`; honest abstention is untouched.
- **Always re-verify:** a re-drafted section's fresh claims go back through the C-lite judge
  (`draft-verify` → `draft-verify-commit`) before re-assemble. A correction must not escape the
  gate that catches drafting errors.

- *Rejected:* immediate per-answer re-pass (interactive-blocking, D6-rejected; duplicates work);
  skip re-verify (corrections escape the judge).
- *Best practice:* the pipeline's existing "run to completion, gate afterward" posture;
  dedup is standard idempotency.

### AD4 — `blocks` / `blocking`: answering clears `blocking`, triage recomputes, `blocks` reserved

- Answering a question flips its `blocking → false`; triage **deterministically recomputes** on
  re-render (RED → AMBER/GREEN), so the de-escalation is visible. A cleared **blocking**
  understand-question routes to a node re-pass like any other answered understand-question
  (blocking merely means it *also* affected triage).
- `blocks: list[str]` stays a **documented reserved field** — no producer populates it, so wiring
  a dependency graph is speculative. Activating it is a clean follow-up if a real corpus ever
  populates it.

- *Rejected:* activate `blocks` (auto-queue unblocked targets — the overblocking pattern the 2025
  literature flags; no producer evidence); hard blocking gate on generation (contradicts D6).
- *Best practice (researched):* non-blocking async review queues dominate production; hard gates
  are reserved for **irreversible actions**, and a reviewable draft is not one. Rule/graph
  guardrails carry a documented overblocking + latency pitfall; a NeurIPS 2025 poster questions
  whether workflow-induced dependency edges can be trusted. Matches the "don't over-armor" rule.

### AD5 — Termination, idempotency, audit

- **Resolved questions persist** (`resolved=true`, `answer`, `disposition`) — the Reviewer's
  dispositions are the audit trail due diligence requires. `_triage.md` renders **Open** (with
  `> answer:` slots) vs **Resolved** (answer + disposition shown).
- **Idempotency (B1 — dedup on re-ingest):** question identity =
  `(raised_by, section_id | node_id, normalized question text)`. On re-ingest after a re-pass,
  `draft-verify-commit` **suppresses** a fresh verdict that matches an already-**resolved**
  question; a genuinely new question surfaces. Re-verify always runs (honesty preserved); the
  Reviewer is never re-nagged on a settled item.
- **Convergence:** the loop is done for a section when a re-verify raises **0 new** questions — an
  observable "dry" signal, the standard iterative-review convergence criterion. The worklist is
  built only from the current `answer-commit` batch's `revise` targets, so it is **stateless** (no
  cross-session "already done?" tracking).
- **Accepted findings** (`disposition=accept`) drop off the `_triage.md` open list but surface in
  `report_comments.md` as **disclosed caveats** — a real limitation the reader should know. This
  preserves the D4 two-surface split (`_triage.md` = what's left to do; `report_comments.md` =
  what the reader should know).
- **B3 backstop (warn-only):** `assemble` emits a warning (never a hard stop) if a section has
  cycled 3+ times, so pathological oscillation is visible rather than silent.

---

## Data contracts

Changed pydantic models (in `tlddr/models.py`):

```python
class Disposition(str, Enum):            # NEW — the reviewer's decision on an answered question
    REVISE = "revise"                    # answer routes to a re-pass
    ACCEPT = "accept"                    # acknowledged finding; no re-pass; disclosed as a caveat

class Question(BaseModel):               # CHANGED: + disposition, + resolved
    id: str
    raised_by: str                       # understand | draft | verify
    node_id: str | None = None
    section_id: str | None = None
    question: str
    blocks: list[str] = Field(default_factory=list)   # reserved (AD4); no producer populates it
    blocking: bool = False
    answer: str | None = None            # now consumed by answer-commit
    disposition: Disposition | None = None   # NEW — set at answer-commit
    resolved: bool = False               # NEW — set at answer-commit
```

**Answer record contract** (the `answer-commit` input; produced by the skill, a retrieval agent,
or the slot parser):

```json
[
  {"id": "verify-3", "disposition": "revise",
   "answer": "Causal link to the Hess acquisition is correct — keep it, cite p.47."},
  {"id": "verify-5", "disposition": "accept",
   "answer": "Acceptable precision nit; disclose as a known caveat."}
]
```

**Worklist contract** (`work/worklist.json`; deduped by target, written by `answer-commit`):

```json
{
  "sections": [
    {"section_id": "sec-3", "guidance": "<resolved answers for this section>",
     "from": ["verify-3", "verify-8"]}
  ],
  "nodes": [
    {"node_id": "r972", "guidance": "<resolved answer>", "from": ["understand-12"]}
  ]
}
```

---

## CLI and skill surface

New deterministic CLI (tested Python; exact signatures fixed in the plan):

- `tlddr answer-commit (--answers <f> | --triage <f>) --work <dir> [--sections <f>] [--vault <dir>]`
  — validate answer records (id resolves to a known question; `disposition ∈ {revise, accept}`;
  unknown ids reported and dropped), set `answer` / `disposition` / `resolved=true`, flip
  `blocking→false` on resolved questions, write the deduped `worklist.json` from this batch's
  `revise` targets, and print it. Re-renders `_triage.md` (Open/Resolved) when `--vault` is given.
  Two mutually-exclusive input modes converge on the same validated record path (AD1):
  - `--answers <f>` — structured answer records (the review-session skill or a retrieval agent).
  - `--triage <f>` — the lightweight fallback: parse filled `> answer:` slots from a `_triage.md`
    (with leading `[revise]` / `[accept]` tags) into the same answer records. A slot with no
    tag, or an unrecognized tag, is reported and skipped (machine-trust — no silent default).

Changed CLI:

- `draft-verify-commit` — apply the AD5/B1 dedup: suppress a fresh verdict whose question
  identity matches an already-**resolved** question.
- `assemble` — render `_triage.md` as Open/Resolved; render accepted findings as disclosed
  caveats in `report_comments.md`; emit the B3 3+-cycle warning.
- `render_triage` (`understand/render.py`) — split Open vs Resolved; `> answer:` slots only on
  Open; resolved questions no longer drive `blocking`-triage (already cleared).

Host-agent procedures (`skills/`):

- `skills/review/SKILL.md` — **NEW**: the interactive review session (see below).
- `skills/draft`, `skills/understand` — grow a short "re-pass mode" note: read the guidance block
  for the target from the worklist and treat it as instruction (never as a citation).

Deterministic/model line (carry forward): the model converses and re-drafts/re-understands; the
tested CLI validates answers, routes, builds the worklist, dedups on re-ingest, and re-assembles.

---

## The review-session skill (`skills/review/SKILL.md`)

A tightly-written, brainstorm-style procedure — one question at a time, because each may need
real document checking by the Reviewer:

1. **Load** the **open** questions from `questions.json`, ordered blocking/RED first.
2. **Per question:** present it neatly, then **links to the pertinent documents**
   (`[[node_id]]` + the cited pages) for easy retrieval, then a **suggested probable answer** —
   or, where the question genuinely admits multiple readings, **ranked interpretations** presented
   like the brainstorming skill's solution options.
3. **Discuss freely.** Interim conversation is **never tracked or written to file.**
4. **Sign-off:** on agreement, present a **deliberate quoted/italicised decision** for explicit
   approval. Only the approved text — plus its `disposition` (revise/accept) — becomes an answer
   record. Nothing is committed without the nod.
5. **After the batch:** call `answer-commit`, walk the printed worklist (re-draft → re-verify per
   section; re-understand per node, surfacing any tag-change follow-ups), then re-`assemble`.

---

## Stage flow (the loop, script-orchestrated where deterministic)

1. **Review** (skill, async): Reviewer works the open queue one question at a time; signs off
   deliberate decisions. → answer records.
2. **Commit** (`answer-commit`): validate → set `answer`/`disposition`/`resolved`, clear
   `blocking`, write deduped `worklist.json`, print it.
3. **Re-pass** (skills, per worklist target):
   - section → `draft` (guidance block as instruction) → `draft-commit` → `draft-verify` →
     `draft-verify-commit` (B1 dedup).
   - node → `understand` (guidance) → `understand-commit`; if section tags changed, the CLI
     surfaces the affected sections as suggested follow-up re-drafts (AD2).
4. **Assemble:** re-render `report.md` + `report_comments.md` (accepted findings as disclosed
   caveats) + `_triage.md` (Open/Resolved). B3 warns at 3+ cycles.
5. **Converge:** a re-verify that raises 0 new questions is done for that section; an empty
   worklist means the round is done.

---

## Proving approach (the live test case)

The Chevron run's **19 open verify questions** (`docs/chevron-run-status.md`) are the ready-made
end-to-end test:

1. Run the review-session skill over the 19; sign off a mix of **accept** (the precision-nits) and
   at least one **revise** (e.g. a "…due to the Hess acquisition" causal embellishment → re-draft
   with the guidance to keep-and-cite or drop).
2. `answer-commit` resolves all 19, writes a worklist collapsing them to the handful of sections
   they touch (dedup proven), clears any blocking (triage de-escalates).
3. Re-draft + re-verify the revised sections; confirm B1 suppresses the already-resolved
   questions and only genuinely new ones surface; the loop converges (0 new).
4. Re-`assemble`; confirm accepted findings appear as disclosed caveats in `report_comments.md`,
   resolved questions show under Resolved in `_triage.md`, and grounding is intact (every claim
   still resolves to a real `(node_id, page)`).

Guardrails held throughout: ingestion validated at the seam; the re-pass never weakens grounding
or honest abstention; no question is re-raised forever.

---

## Deferred / staged (designed, not built)

- **`blocks` dependency graph** — reserved field; wire only if a producer ever populates it (AD4).
- **Automatic transitive re-drafting** on a node tag change — surfaced as suggestions, not run
  (AD2); revisit only if the fan-out proves common.
- **Retrieval-agent answer producer** — the contract is source-agnostic; the agent that answers
  from the corpus is a future producer, not built here.
- Interactive **blocking** review — explicitly rejected (D6 / AD4).

---

## Best-practice references

- HITL / async review queues: production HITL patterns (generate → review queue → gated commit);
  RAGOps (route feedback to the producing component); LLMOps deployment surveys (non-blocking
  dominates; hard gates reserved for irreversible actions).
- Overblocking / dependency-graph caution: workflow-optimization survey (guardrail overblocking +
  latency pitfall); NeurIPS 2025 "Can Dependencies Induced by LLM-Agent Workflows Be Trusted?".
- Convergence: iterative "loop until no new findings" review.
- Grounding/faithfulness (carried forward): AIS / ALCE attribution; RAGAS faithfulness; the
  answer-as-guidance-never-evidence guardrail keeps claims pinned to real pages.
