# Answer Loop — Hardening Design (post-smoke-test)

**Status:** approved design, pre-implementation
**Date:** 2026-07-03
**Branch:** `feat/answer-loop`
**Type:** proof-of-concept hardening (five fixes on the already-built answer loop)

The Chevron smoke test (`docs/superpowers/2026-07-03-answer-loop-smoke-test-findings.md`)
proved the answer loop's plumbing end-to-end but exposed that its prescribed re-pass
mechanism is the harmful one, and that several defects share a single root: **claims have
no durable identity.** This spec hardens the loop before merge. It addresses findings F3,
F5, F6, F9, and F10. F1 (drafter under-citation) and F8b (stronger verifier) are explicitly
out of scope — separate work.

---

## The shared root

A `DraftClaim` today is purely positional — "whatever is at index N in `claims.json`" — and
`draft-commit` does section-scoped replace-and-append, so re-committing a section moves its
claims to the end and every index shifts. That single fact causes:
- **F10** — verify questions minted `verify-{index}`; indices collide across re-passes (two
  different questions ended up sharing `verify-527`).
- **F5** — with no stable claim handle, dedup fell back to keying on claim text + the judge's
  free-text note; either drifting defeats suppression, so it almost never fires.
- **F9** — a surgical `draft-amend --claim <id>` has no id to target.

So we give claims a durable identity first; the rest follow.

---

## Design decisions

### AD-H1 — Durable surrogate claim id (root fix)
`DraftClaim` gains `id: str`: a durable **surrogate** key, assigned once at first commit,
**frozen** thereafter, and never derived from live content or position. Rejected: a
content-hash *identity* (breaks the moment `set_text` edits a claim — recreates F5) and a
positional/natural key (the status quo that broke). Surrogate-over-content-hash for mutable
records is settled identity design.

### AD-H2 — id format: content-hash at birth, frozen
The id is minted once as `claim-<first 8 hex of sha1(section_id + "\0" + text)>` and stored;
it is never recomputed, so later `set_text` edits do not change it. Deterministic (stable
test fixtures), needs no counter (sidesteps the replace-and-append coordination problem),
unique within `claims.json` (on the rare identical-initial-text collision within a section,
append `-2`, `-3`, …). Opaque, which is fine: the id is a machine handle you copy out of the
store, not something you type.

### AD-H3 — `draft-amend`: the sanctioned surgical re-pass
A new deterministic command replaces full-section regeneration as the re-pass mechanism.
It is a **batch, file-driven, task-based patch** — a constrained operation vocabulary, not
generic JSON Patch. Best-practice-verified: task-based/intent-revealing operations beat
generic field-patching for business-logic-heavy mutations, and a constrained op-set is
least-privilege for a safety-critical surface — you *cannot express* "mutate
`source_confidence`" or "rewrite `section_id`" because they are not operations, so the
grounding guardrail cannot be walked around (generic JSON Patch could target any path).

- **Input:** `--amendments <file>`, a list of records
  `{claim_id, set_text?, add_pages?: [{node_id, page}], set_support?, set_evidence?}`.
- **Behavior per record:** load the claim by `claim_id`; apply the ops; **re-validate the
  amended claim through the same `validate_claims` path** (every citation resolves to a real
  page, `source_confidence` re-derived from the node — the model's value never trusted);
  persist in place, preserving the claim id.
- **Drop-and-report** (consistent with `answer-commit`/`draft-commit`; each amendment is
  independent per-claim, so a partial apply corrupts no invariant): unknown `claim_id`,
  unresolvable added page, or invalid axis value → that amendment reported and skipped, the
  rest apply. No atomic-batch rollback, no `test`/precondition op (single-user local
  pipeline; no concurrent writer; the frozen id already gives stable targeting).
- **Division of labour:** `draft-commit` stays the **initial** drafting seam (first pass of
  a section; assigns ids). `draft-amend` is the **re-pass** seam (edits existing claims in
  place; preserves ids). Full-section regeneration is de-prescribed.

### AD-H4 — Claim-linked verify questions; stable id = dedup key
`Question` gains `claim_id: str | None` (verify questions set it; draft/understand questions
leave it `None`). The verdict contract changes from index-based to **claim-id-based**:
`{claim_id, support_level, contradiction, note}` — the judge already reads `claims.json`, so
it references the durable id and the fragile index leaves the contract entirely. The verify
question id becomes `verify-{claim_id}-{reason}` where `reason ∈ {downgrade, contradiction}`.

That id **is** the dedup key. Suppression in `draft-verify-commit` becomes: skip a candidate
if a question with that same id already exists in a non-`OPEN` status. No `question_identity`
tuple, no claim-text snippet, no free-text note in the key. Consequences:
- 527-type case (byte-identical claim, note varied) → suppressed (id depends only on
  `claim_id` + `reason`).
- collision case (different claims, same old index) → gone (different `claim_id`s → different
  ids).
- uniqueness is guaranteed by the dedup: a second `verify-{X}-downgrade` is never minted
  because the re-flag is suppressed rather than raised.

The `(claim_id, reason)` key is **deliberately coarse**: once a human has adjudicated "this
claim's support is contested," a differently-worded re-flag on the same claim+reason does not
re-nag; a genuinely new problem is still caught on the human's final read. This is the
intended behavior, not a limitation.

### AD-H5 — One lifecycle status (replaces `resolved` + `disposition` + a would-be `applied`)
A single state machine makes illegal combinations unrepresentable and future-proofs new
states, and it *unifies* three overlapping fields rather than adding a fourth.

```python
class QuestionStatus(str, Enum):
    OPEN           = "open"            # unanswered
    ACCEPTED       = "accepted"        # answered accept — terminal; disclosed as a caveat
    REVISE_PENDING = "revise_pending"  # answered revise — awaiting its re-pass
    REVISE_APPLIED = "revise_applied"  # re-pass executed — terminal
```

Transitions, all through existing seams:
- `OPEN → ACCEPTED` / `OPEN → REVISE_PENDING` at `answer-commit`, by the reviewer's
  disposition.
- `REVISE_PENDING → REVISE_APPLIED` when a re-pass commit touches the target:
  `draft-amend` (by `claim_id`), `draft-commit` (by `section_id`), `understand-commit`
  (by `node_id`) each flip their target's pending revises to applied. (No-op on an initial
  draft, since nothing is pending yet.)

`assemble` emits a **warn-only** line (same posture as the B3 cycle warning) listing any
question still `REVISE_PENDING` — a committed revise whose re-pass never ran, which is the
silent-drop F6 guards against. `applied`/`resolved`/accept/revise are all derived from
status; the standalone booleans are removed.

The **`Disposition` enum stays**, but only as the *input* vocabulary in answer records
(`{"disposition": "revise"}`); `ingest_answers` maps it to a `QuestionStatus`. Reviewer input
and stored lifecycle are cleanly separated.

---

## Data contracts

```python
class DraftClaim(BaseModel):            # CHANGED: + id
    id: str                             # durable surrogate, assigned at first commit, frozen
    section_id: str
    text: str
    sources: list[Citation] = Field(default_factory=list)
    support_level: SupportLevel
    evidence_relation: EvidenceRelation

class QuestionStatus(str, Enum):        # NEW
    OPEN = "open"; ACCEPTED = "accepted"
    REVISE_PENDING = "revise_pending"; REVISE_APPLIED = "revise_applied"

class Question(BaseModel):              # CHANGED: - resolved, - disposition; + claim_id, + status
    id: str                             # verify: verify-{claim_id}-{reason}
    raised_by: str
    node_id: str | None = None
    section_id: str | None = None
    claim_id: str | None = None         # NEW — verify questions link to their claim
    question: str
    blocks: list[str] = Field(default_factory=list)
    blocking: bool = False
    answer: str | None = None
    status: QuestionStatus = QuestionStatus.OPEN   # NEW — replaces resolved + disposition

# Disposition enum retained as answer-record input vocabulary only.
```

**Amendment record** (`draft-amend --amendments` input):
```json
[{"claim_id": "claim-3f9a2b1c", "add_pages": [{"node_id": "cvx-20251231", "page": 45}]},
 {"claim_id": "claim-7c1d40ab", "set_text": "…corrected text…",
  "set_support": "partially_supported"}]
```

**Verdict record** (`draft-verify-commit` input — CHANGED, index → claim_id):
```json
[{"claim_id": "claim-3f9a2b1c", "support_level": "partially_supported",
  "contradiction": false, "note": "…"}]
```

---

## CLI and skill surface

**New:**
- `tlddr draft-amend --amendments <f> --output <base>` — validated claim-level patch (AD-H3);
  flips amended claims' `REVISE_PENDING` verify questions → `REVISE_APPLIED`.

**Changed:**
- `draft-commit` — assign `id` to each claim lacking one (AD-H1/H2); flip the committed
  section's `REVISE_PENDING` questions → `REVISE_APPLIED`.
- `draft-verify-commit` — verdicts keyed on `claim_id`; mint `verify-{claim_id}-{reason}`;
  suppress a candidate whose id matches an existing non-`OPEN` question (AD-H4).
- `answer-commit` — set `status` from the reviewer's disposition (`OPEN → ACCEPTED` /
  `REVISE_PENDING`) instead of `resolved` + `disposition`. It no longer needs to mutate
  `blocking`: `_display_triage` filters to `OPEN` questions, so answering a question
  (→ non-`OPEN`) already de-escalates its node. `blocking` stays a property of the
  still-open question set.
- `understand-commit` — flip the committed node's `REVISE_PENDING` questions → `REVISE_APPLIED`.
- `assemble` — warn-only on lingering `REVISE_PENDING` (F6).
- `render_triage` / `render_sidecar` — read `status`: Open = `OPEN` (answer slots); Resolved =
  `!= OPEN`; disclosed caveats = `ACCEPTED`; hidden = `REVISE_*`. `_display_triage` filters to
  `OPEN` questions.

**Skills:**
- `skills/draft-verify` — emit `claim_id` (not `index`) in verdicts.
- `skills/draft` / `skills/review` re-pass mode — rewritten to author an `amendments.json` and
  drive `draft-amend`, not to regenerate the section via `skills/draft`.

---

## Testing approach

- Claim id: assigned at first commit, unique, stable across a `set_text` amend; collision
  suffix on identical initial text.
- `draft-amend`: each op (`add_pages`, `set_text`, `set_support`, `set_evidence`) applies and
  re-validates; unknown `claim_id` and unresolvable added page are dropped-and-reported;
  `source_confidence` is re-derived, not taken from input; committed report untouched by a
  dropped amendment.
- Verify dedup (**fixes the F5 masking test**): suppression holds when the judge `note` **and**
  the claim text both vary but `claim_id` + `reason` are unchanged. The old test used
  identical question text and masked the bug — the new test must vary both.
- Id stability (**F10 regression test**): two re-passes that reorder claims do not collide
  question ids and do not resurrect a resolved question.
- Lifecycle: `answer-commit` sets `ACCEPTED`/`REVISE_PENDING`; `draft-amend`/`draft-commit`/
  `understand-commit` flip pending→applied for their target; `assemble` warns on a lingering
  `REVISE_PENDING` and does not warn once applied.
- Render/sidecar read `status` correctly across all four states.

---

## Migration / compatibility

No migrator. The only existing `questions.json`/`claims.json` in the old shape is the
gitignored, backed-up Chevron run — a throwaway test artifact. New runs use the new shape.
If the Chevron artifacts must load again, regenerate or hand-migrate; not a project burden.

## Out of scope (separate work)
- **F1** — drafter under-citation / compound claims (draft-stage: atomic claims / cite every
  page). Upstream of the loop.
- **F8b** — stronger verify stage (C-full NLI ensemble) so review adjudicates trustworthy
  flags rather than re-verifying untrustworthy ones.

## Best-practice references
- Surrogate vs content-hash/natural keys for mutable records (identity design).
- Task-based / intent-revealing operations over generic JSON Patch for business-logic-heavy,
  safety-constrained mutations (Postman HTTP PATCH guidance; "case against generic PATCH/PUT";
  task-based-vs-CRUD). Least-privilege constrained op-set.
- Explicit lifecycle state machine over overlapping boolean flags (illegal states
  unrepresentable).
- Drop-and-report batch semantics (house consistency; independent per-item operations).
