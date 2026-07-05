# Answer Loop Hardening Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Harden the answer loop (findings F3/F5/F6/F9/F10) by giving claims a durable id, replacing full-section regeneration with a validated claim-level `draft-amend`, making the verify question id the robust dedup key, and unifying the question lifecycle into one status enum.

**Architecture:** All changes are to the existing deterministic Python (`tlddr/`) plus two skills. The load-bearing move is a durable surrogate `DraftClaim.id`; everything else keys off it. Sequenced so the suite stays green between tasks: additive claim-id first, then the status migration as one cohesive swap, then the identity/dedup rewrite, the new command, the lifecycle markers, and finally skills/docs.

**Tech Stack:** Python 3.14, pydantic, argparse, pytest, hashlib (stdlib). No new dependencies.

## Global Constraints

- **No new dependencies** — stdlib + pydantic only.
- **Grounding guardrail** — every citation resolves to a real page; `source_confidence` is re-derived by the CLI, never taken from model input. `draft-amend` must re-validate through the same path.
- **Machine-trust / drop-and-report** — unknown ids and invalid inputs are reported and dropped, never silently accepted; each item validated independently (no atomic-batch rollback).
- **No emojis** anywhere (code, comments, commits).
- **Conventional commits**: `type(scope): description`.
- **Terminology**: the human role is **Reviewer**, never "Engineer".
- Run tests with `.venv/bin/pytest`. The suite must be green at the end of every task.
- Branch `feat/answer-loop` (already checked out).

---

## File Structure

**Modify:**
- `tlddr/models.py` — `DraftClaim.id`; `QuestionStatus` enum; `Question` gains `claim_id` + `status`, loses `resolved` + `disposition`.
- `tlddr/draft/claims.py` — `_claim_id()` helper; `validate_claims` assigns id.
- `tlddr/draft/verify.py` — `ingest_verdicts` keyed on `claim_id`, id-based dedup; drop `question_identity` usage.
- `tlddr/draft/amend.py` — **NEW**: `apply_amendments()`.
- `tlddr/answer.py` — `ingest_answers` sets `status`; remove dead `question_identity`/`_normalize` (Task 3).
- `tlddr/understand/render.py` — read `status` instead of `resolved`/`disposition`.
- `tlddr/draft/assemble.py` — `render_sidecar` reads `status`.
- `tlddr/cli.py` — `draft_commit` (assign ids, uniqueness, lifecycle flip); `draft_verify_commit` (claim_id verdicts, id dedup, status); `answer_commit` (status); `understand_commit` (lifecycle flip); `assemble` (REVISE_PENDING warning); new `draft-amend` command.
- Skills: `skills/draft-verify/SKILL.md` (emit `claim_id`); `skills/draft/SKILL.md` + `skills/review/SKILL.md` (re-pass mode → `draft-amend`).
- Indexes/docs: `tlddr/CLAUDE.md`, `tlddr/draft/CLAUDE.md`, `docs/HANDOFF.md`.

**Test:** `tests/test_draft_claims.py`, `tests/test_answer.py`, `tests/test_render.py`, `tests/test_draft_assemble.py`, `tests/test_draft_verify.py`, `tests/test_answer_cli.py`, and new `tests/test_amend.py`.

---

### Task 1: Durable claim id (AD-H1 / AD-H2)

**Files:**
- Modify: `tlddr/models.py` (`DraftClaim`), `tlddr/draft/claims.py`, `tlddr/cli.py` (`draft_commit`)
- Test: `tests/test_draft_claims.py`

**Interfaces:**
- Produces: `DraftClaim.id: str = ""` (durable surrogate); `tlddr.draft.claims._claim_id(section_id: str, text: str) -> str` → `claim-<8 hex>`; `validate_claims` assigns `id` (from `raw["id"]` if present, else computed); `draft_commit` guarantees ids unique across the committed store (collision → `-2`, `-3` suffix).

- [ ] **Step 1: Write the failing test**

Add to `tests/test_draft_claims.py`:

```python
from tlddr.draft.claims import validate_claims, _claim_id


def test_claim_id_is_deterministic_from_section_and_text():
    a = _claim_id("s1", "Design life is 25 years.")
    b = _claim_id("s1", "Design life is 25 years.")
    assert a == b and a.startswith("claim-")
    assert _claim_id("s1", "other") != a


def test_validate_claims_assigns_id_when_absent(_docs_and_nodes):
    docs, nodes = _docs_and_nodes
    raw = [{"section_id": "s1", "text": "Design life is 25 years.",
            "support_level": "fully_supported", "evidence_relation": "quoted",
            "sources": [{"node_id": "r518", "page": 12}]}]
    valid, _ = validate_claims(raw, docs, nodes, {"s1"})
    assert valid[0].id == _claim_id("s1", "Design life is 25 years.")


def test_validate_claims_preserves_supplied_id(_docs_and_nodes):
    docs, nodes = _docs_and_nodes
    raw = [{"id": "claim-fixed", "section_id": "s1", "text": "Design life is 25 years.",
            "support_level": "fully_supported", "evidence_relation": "quoted",
            "sources": [{"node_id": "r518", "page": 12}]}]
    valid, _ = validate_claims(raw, docs, nodes, {"s1"})
    assert valid[0].id == "claim-fixed"
```

Add this fixture at the top of `tests/test_draft_claims.py` if not present (check existing imports first; reuse the file's existing doc/node builders if it has them):

```python
import pytest
from tlddr.models import ExtractedDoc, Node, PageProvenance, SignalType, ExtractMethod, Confidence, Triage


@pytest.fixture
def _docs_and_nodes():
    doc = ExtractedDoc(id="r518", source_path="/x", source_sha256="a",
                       signal_type=SignalType.MIXED, raw_title="R518",
                       content="--- page 12 ---\ndesign life 25 years",
                       pages=[PageProvenance(page=12, method=ExtractMethod.PYMUPDF_TEXT, has_text_layer=True)],
                       extractor="pdf")
    node = Node(id="r518", extracted_id="r518", title="R518", doc_type="report", description="d",
                confidence_extraction=Confidence.HIGH, confidence_interpretation=Confidence.HIGH,
                triage=Triage.GREEN, report_sections=["s1"])
    return {"r518": doc}, {"r518": node}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_draft_claims.py -k "claim_id or assigns_id or preserves_supplied" -v`
Expected: FAIL — `cannot import name '_claim_id'` / `DraftClaim` has no `id`.

- [ ] **Step 3: Add the model field**

In `tlddr/models.py`, add `id` as the first field of `DraftClaim`:

```python
class DraftClaim(BaseModel):
    id: str = ""                       # durable surrogate, assigned at first commit, frozen
    section_id: str
    text: str
    sources: list[Citation] = Field(default_factory=list)
    support_level: SupportLevel
    evidence_relation: EvidenceRelation
```

- [ ] **Step 4: Assign the id in `validate_claims`**

In `tlddr/draft/claims.py`, add the import and helper at the top:

```python
import hashlib


def _claim_id(section_id: str, text: str) -> str:
    """Durable surrogate id, minted once from initial content; stored and frozen thereafter."""
    digest = hashlib.sha1(f"{section_id}\0{text}".encode()).hexdigest()[:8]
    return f"claim-{digest}"
```

In the `valid.append(DraftClaim(...))` call, pass the id (preserve supplied, else compute):

```python
        valid.append(DraftClaim(
            id=raw.get("id") or _claim_id(section_id, raw["text"]),
            section_id=section_id, text=raw["text"], sources=citations,
            support_level=SupportLevel(raw["support_level"]),
            evidence_relation=EvidenceRelation(raw["evidence_relation"]),
        ))
```

- [ ] **Step 5: Guarantee uniqueness in `draft_commit`**

In `tlddr/cli.py` `draft_commit`, after `committed.extend(valid)` and before the write, de-duplicate ids (first occurrence keeps its id; later collisions get a numeric suffix):

```python
    seen: dict[str, int] = {}
    for c in committed:
        if c.id in seen:
            seen[c.id] += 1
            c.id = f"{c.id}-{seen[c.id]}"
        else:
            seen[c.id] = 1
    (work_dir / "claims.json").write_text(
        json.dumps([c.model_dump(mode="json") for c in committed], indent=2))
```

- [ ] **Step 6: Run tests**

Run: `.venv/bin/pytest tests/test_draft_claims.py tests/test_draft_cli.py -v`
Expected: PASS. (Existing `DraftClaim(...)` constructions elsewhere still work — `id` defaults to `""`.)

- [ ] **Step 7: Commit**

```bash
git add tlddr/models.py tlddr/draft/claims.py tlddr/cli.py tests/test_draft_claims.py
git commit -m "feat(draft): give DraftClaim a durable surrogate id"
```

---

### Task 2: QuestionStatus lifecycle (AD-H5 core — the model swap)

**Files:**
- Modify: `tlddr/models.py`, `tlddr/answer.py` (`ingest_answers`), `tlddr/understand/render.py`, `tlddr/draft/assemble.py`, `tlddr/cli.py` (`draft_verify_commit` suppress source + drop predicate)
- Test: `tests/test_answer.py`, `tests/test_render.py`, `tests/test_draft_assemble.py`, `tests/test_answer_cli.py`

**Interfaces:**
- Produces: `QuestionStatus(str, Enum)` = `OPEN|ACCEPTED|REVISE_PENDING|REVISE_APPLIED`; `Question.status: QuestionStatus = OPEN` (replaces `resolved` + `disposition`). `Disposition` enum retained as answer-record input vocabulary. Derived predicates everywhere: open = `status is OPEN`; resolved = `status is not OPEN`; caveat = `status is ACCEPTED`.

- [ ] **Step 1: Write the failing test**

Replace the two `Question` field tests in `tests/test_answer.py` (the `disposition`/`resolved` ones) with:

```python
from tlddr.models import Question, QuestionStatus


def test_question_status_defaults_open():
    q = Question(id="q-1", raised_by="verify", section_id="s1", question="is this right?")
    assert q.status is QuestionStatus.OPEN
    assert q.answer is None


def test_question_round_trips_status_and_answer():
    q = Question(id="q-1", raised_by="verify", section_id="s1", question="q?",
                 answer="Yes.", status=QuestionStatus.ACCEPTED)
    restored = Question.model_validate_json(q.model_dump_json())
    assert restored.status is QuestionStatus.ACCEPTED
    assert restored.answer == "Yes."
```

Update the `ingest_answers` tests in the same file: replace assertions on `q.resolved`/`q.disposition` with `status`:

```python
def test_valid_answer_sets_status_and_worklist():
    qs = [_q("v-1", "verify", section_id="s1", blocking=True)]
    records = [{"id": "v-1", "disposition": "revise", "answer": "Keep it, cite p.47."}]
    updated, worklist, dropped = ingest_answers(records, qs)
    assert dropped == []
    assert updated[0].status is QuestionStatus.REVISE_PENDING
    assert updated[0].answer == "Keep it, cite p.47."


def test_accept_sets_accepted_status_and_no_worklist():
    qs = [_q("v-1", "verify", section_id="s1")]
    updated, worklist, _ = ingest_answers(
        [{"id": "v-1", "disposition": "accept", "answer": "Fine."}], qs)
    assert updated[0].status is QuestionStatus.ACCEPTED
    assert worklist["sections"] == [] and worklist["nodes"] == []
```

(Add `QuestionStatus` to the `test_answer.py` imports. Leave the unknown-id / invalid-disposition drop tests as-is.)

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_answer.py -k "status or worklist or accepted" -v`
Expected: FAIL — `cannot import name 'QuestionStatus'`.

- [ ] **Step 3: Migrate the model**

In `tlddr/models.py`, add the enum after `Disposition`:

```python
class QuestionStatus(str, Enum):
    OPEN = "open"                      # unanswered
    ACCEPTED = "accepted"              # answered accept — terminal; disclosed as a caveat
    REVISE_PENDING = "revise_pending"  # answered revise — awaiting its re-pass
    REVISE_APPLIED = "revise_applied"  # re-pass executed — terminal
```

Change `Question`: remove `disposition` and `resolved`, add `status` (keep everything else):

```python
class Question(BaseModel):
    id: str
    raised_by: str
    node_id: str | None = None
    section_id: str | None = None
    question: str
    blocks: list[str] = Field(default_factory=list)
    blocking: bool = False
    answer: str | None = None
    status: QuestionStatus = QuestionStatus.OPEN
```

- [ ] **Step 4: Migrate `ingest_answers`**

In `tlddr/answer.py`, update the imports and the resolve block:

```python
from tlddr.models import Question, Disposition, QuestionStatus
```

Replace the mutation inside the loop (the `q.answer = ...; q.disposition = ...; q.resolved = True; q.blocking = False` block) with:

```python
        q.answer = r.get("answer")
        q.status = (QuestionStatus.ACCEPTED if disposition is Disposition.ACCEPT
                    else QuestionStatus.REVISE_PENDING)
        if disposition is Disposition.REVISE:
            revised.append(q)
```

(Drop the `q.blocking = False` line — per AD-H5, answering de-escalates via `_display_triage`'s OPEN filter; `blocking` stays a property of the still-open set.)

- [ ] **Step 5: Migrate the consumers**

`tlddr/understand/render.py`: add `QuestionStatus` to the model import; in `_display_triage` change `not q.resolved` → `q.status is QuestionStatus.OPEN`; replace the open/resolved partition:

```python
    open_qs = [q for q in questions if q.status is QuestionStatus.OPEN]
    resolved_qs = [q for q in questions if q.status is not QuestionStatus.OPEN]
```

and in the resolved-render loop change the disposition line to show status:

```python
            lines.append(f"### {q.id} ({q.status.value}){target}")
```

`tlddr/draft/assemble.py`: change the model import (drop `Disposition`, add `QuestionStatus`); replace the sidecar partition:

```python
        section_qs = [q for q in questions if q.section_id == s.id]
        open_qs = [q for q in section_qs if q.status is QuestionStatus.OPEN]
        caveats = [q for q in section_qs if q.status is QuestionStatus.ACCEPTED]
```

`tlddr/cli.py` `draft_verify_commit`: change the suppress-set source and drop predicate to read status (still `question_identity`-keyed here; Task 3 replaces the mechanism). Add `QuestionStatus` to the cli imports:

```python
    suppress = {question_identity(q) for q in existing if q.status is not QuestionStatus.OPEN}
    new_qs = ingest_verdicts(verdicts, _load_claims(work_dir), suppress)
    _append_questions(
        work_dir, new_qs,
        drop=lambda q: q.get("raised_by") == "verify" and q.get("status", "open") == "open")
```

- [ ] **Step 6: Update the remaining tests**

In `tests/test_render.py`, `tests/test_draft_assemble.py`, `tests/test_answer_cli.py`: replace every `resolved=True` / `disposition=Disposition.X` on a `Question(...)` with `status=QuestionStatus.X` (ACCEPTED for accept, REVISE_PENDING/REVISE_APPLIED for revise), and every assertion on the JSON `"resolved"`/`"disposition"` keys with `"status"`. Example in `test_answer_cli.py`:

```python
    qs = {q["id"]: q for q in _load_qs(base)}
    assert qs["v-1"]["status"] == "revise_pending"
    assert qs["v-2"]["status"] == "accepted"
```

Update `test_draft_assemble.py`'s caveat test to construct `status=QuestionStatus.ACCEPTED` (caveat), `status=QuestionStatus.REVISE_PENDING` (hidden), `status=QuestionStatus.OPEN` (open).

- [ ] **Step 7: Run the full suite**

Run: `.venv/bin/pytest`
Expected: PASS — the swap is complete and no reference to `.resolved`/`.disposition` on `Question` remains. (Grep to confirm: `grep -rn "\.resolved\|\.disposition" tlddr/ | grep -iv "support\|node\|section"` returns nothing in `tlddr/`.)

- [ ] **Step 8: Commit**

```bash
git add tlddr/ tests/
git commit -m "refactor(models): unify Question resolved+disposition into a status enum"
```

---

### Task 3: Claim-linked verify questions + id-based dedup (AD-H4, fixes F5 + F10)

**Files:**
- Modify: `tlddr/models.py` (`Question.claim_id`), `tlddr/draft/verify.py`, `tlddr/cli.py` (`draft_verify_commit`), `tlddr/answer.py` (remove dead `question_identity`/`_normalize`)
- Test: `tests/test_draft_verify.py`

**Interfaces:**
- Consumes: `DraftClaim.id` (Task 1), `QuestionStatus` (Task 2).
- Produces: `Question.claim_id: str | None = None`; `ingest_verdicts(verdicts: list[dict], claims: list[DraftClaim], suppress_ids: set[str] | None = None) -> list[Question]` — verdicts key on `claim_id`, question id = `verify-{claim_id}-{reason}` (`reason ∈ {downgrade, contradiction}`), suppressed if id ∈ `suppress_ids`.

- [ ] **Step 1: Write the failing test**

Rewrite `tests/test_draft_verify.py`'s claim/verdict helpers and tests to be claim_id-based:

```python
from tlddr.draft.verify import ingest_verdicts
from tlddr.models import DraftClaim, Citation, SupportLevel, EvidenceRelation, Confidence, QuestionStatus


def _claim(cid="claim-a", section="s1", support=SupportLevel.FULLY_SUPPORTED, text="claimed strongly"):
    return DraftClaim(id=cid, section_id=section, text=text,
                      sources=[Citation(node_id="n", page=1, source_confidence=Confidence.HIGH)],
                      support_level=support, evidence_relation=EvidenceRelation.QUOTED)


def test_downgrade_raises_question_linked_to_claim():
    claims = [_claim()]
    qs = ingest_verdicts([{"claim_id": "claim-a", "support_level": "unsupported",
                           "contradiction": False, "note": "not stated"}], claims)
    assert len(qs) == 1
    assert qs[0].id == "verify-claim-a-downgrade"
    assert qs[0].claim_id == "claim-a"
    assert qs[0].section_id == "s1"
    assert "not stated" in qs[0].question


def test_unknown_claim_id_skipped():
    assert ingest_verdicts([{"claim_id": "ghost", "support_level": "unsupported",
                             "contradiction": False}], [_claim()]) == []


def test_agreement_raises_nothing():
    assert ingest_verdicts([{"claim_id": "claim-a", "support_level": "fully_supported",
                             "contradiction": False}], [_claim()]) == []


def test_contradiction_id_uses_contradiction_reason():
    qs = ingest_verdicts([{"claim_id": "claim-a", "support_level": "fully_supported",
                           "contradiction": True, "note": "conflicts"}], [_claim()])
    assert qs[0].id == "verify-claim-a-contradiction"


def test_suppressed_when_id_in_suppress_set():
    claims = [_claim()]
    v = [{"claim_id": "claim-a", "support_level": "unsupported", "contradiction": False}]
    assert ingest_verdicts(v, claims, {"verify-claim-a-downgrade"}) == []


def test_dedup_robust_to_note_and_text_drift():
    # F5 regression: same claim_id + reason must suppress even when note AND text vary
    claims_v1 = [_claim(text="original text", support=SupportLevel.FULLY_SUPPORTED)]
    first = ingest_verdicts([{"claim_id": "claim-a", "support_level": "unsupported",
                              "contradiction": False, "note": "reason one"}], claims_v1)
    suppress = {first[0].id}
    claims_v2 = [_claim(text="reworded text entirely", support=SupportLevel.FULLY_SUPPORTED)]
    again = ingest_verdicts([{"claim_id": "claim-a", "support_level": "unsupported",
                              "contradiction": False, "note": "a totally different note"}],
                            claims_v2, suppress)
    assert again == []      # suppressed on claim_id + reason, not text/note
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_draft_verify.py -v`
Expected: FAIL — `ingest_verdicts` still reads `index`; `Question` has no `claim_id`.

- [ ] **Step 3: Add `Question.claim_id`**

In `tlddr/models.py` `Question`, add after `section_id`:

```python
    claim_id: str | None = None        # verify questions link to their claim
```

- [ ] **Step 4: Rewrite `ingest_verdicts`**

Replace `tlddr/draft/verify.py` entirely:

```python
from tlddr.models import DraftClaim, SupportLevel, Question

_RANK = {SupportLevel.UNSUPPORTED: 0, SupportLevel.PARTIALLY_SUPPORTED: 1,
         SupportLevel.FULLY_SUPPORTED: 2}


def ingest_verdicts(verdicts: list[dict], claims: list[DraftClaim],
                    suppress_ids: set[str] | None = None) -> list[Question]:
    """Turn judge verdicts (keyed on claim_id) into verify questions. A question's id is
    verify-{claim_id}-{reason}; that id is the dedup key — a candidate whose id is already
    resolved (in suppress_ids) or already emitted in this batch is skipped."""
    suppress_ids = suppress_ids or set()
    by_id = {c.id: c for c in claims}
    questions: list[Question] = []
    emitted: set[str] = set()
    for v in verdicts:
        claim = by_id.get(v.get("claim_id"))
        if claim is None:
            continue
        try:
            judged = SupportLevel(v["support_level"])
        except (KeyError, ValueError):
            continue
        contradiction = bool(v.get("contradiction"))
        downgrade = _RANK[judged] < _RANK[claim.support_level]
        if not (downgrade or contradiction):
            continue
        reason = "contradiction" if contradiction else "downgrade"
        qid = f"verify-{claim.id}-{reason}"
        if qid in suppress_ids or qid in emitted:
            continue
        detail = "contradiction" if contradiction else \
            f"judge:{judged.value} < drafter:{claim.support_level.value}"
        note = (v.get("note") or "").strip()
        questions.append(Question(
            id=qid, raised_by="verify", claim_id=claim.id, section_id=claim.section_id,
            question=f"[{detail}] '{claim.text[:80]}' — {note}".rstrip(" -")))
        emitted.add(qid)
    return questions
```

- [ ] **Step 5: Rewire `draft_verify_commit` and remove dead code**

In `tlddr/cli.py` `draft_verify_commit`, switch the suppress set to ids:

```python
    suppress_ids = {q.id for q in existing if q.status is not QuestionStatus.OPEN}
    new_qs = ingest_verdicts(verdicts, _load_claims(work_dir), suppress_ids)
```

Remove the now-unused `from tlddr.answer import ... question_identity` import from `tlddr/cli.py` (keep `ingest_answers`, `parse_triage_answers`). Then delete `question_identity` and `_normalize` from `tlddr/answer.py` (confirm no other importers: `grep -rn "question_identity\|_normalize" tlddr/ tests/` — update/remove any stragglers; the `test_answer.py` identity tests from the loop build should be deleted).

- [ ] **Step 6: Run tests**

Run: `.venv/bin/pytest tests/test_draft_verify.py tests/test_answer.py tests/test_draft_cli.py -v`
Expected: PASS, including `test_dedup_robust_to_note_and_text_drift`.

- [ ] **Step 7: Commit**

```bash
git add tlddr/ tests/
git commit -m "feat(verify): key questions on claim_id; stable id is the dedup key"
```

---

### Task 4: `draft-amend` — the validated surgical re-pass (AD-H3, F9/F3)

**Files:**
- Create: `tlddr/draft/amend.py`, `tests/test_amend.py`
- Modify: `tlddr/cli.py` (new `draft_amend` function + `draft-amend` subcommand + dispatch)
- Test: `tests/test_amend.py`, `tests/test_answer_cli.py`

**Interfaces:**
- Consumes: `validate_claims` (Task 1), `DraftClaim.id`, `QuestionStatus`.
- Produces: `tlddr.draft.amend.apply_amendments(records, claims, docs, nodes, known_section_ids) -> tuple[list[DraftClaim], set[str], list[str]]` (updated full claim list, set of amended claim ids, drop messages); `draft_amend(amendments_path, extracted_dir, work_dir, sections_path=None) -> None` in cli.

- [ ] **Step 1: Write the failing test**

Create `tests/test_amend.py`:

```python
from tlddr.draft.amend import apply_amendments
from tlddr.models import (ExtractedDoc, Node, PageProvenance, SignalType, ExtractMethod,
                          Confidence, Triage, DraftClaim, Citation, SupportLevel, EvidenceRelation)


def _fixtures():
    doc = ExtractedDoc(id="n", source_path="/x", source_sha256="a", signal_type=SignalType.MIXED,
                       raw_title="N", content="--- page 1 ---\na\n--- page 2 ---\nb",
                       pages=[PageProvenance(page=1, method=ExtractMethod.PYMUPDF_TEXT, has_text_layer=True),
                              PageProvenance(page=2, method=ExtractMethod.PYMUPDF_TEXT, has_text_layer=True)],
                       extractor="pdf")
    node = Node(id="n", extracted_id="n", title="N", doc_type="report", description="d",
                confidence_extraction=Confidence.HIGH, confidence_interpretation=Confidence.HIGH,
                triage=Triage.GREEN, report_sections=["s1"])
    claim = DraftClaim(id="claim-a", section_id="s1", text="original",
                       sources=[Citation(node_id="n", page=1)],
                       support_level=SupportLevel.FULLY_SUPPORTED, evidence_relation=EvidenceRelation.QUOTED)
    return {"n": doc}, {"n": node}, [claim]


def test_add_page_and_set_text_preserve_id_and_validate():
    docs, nodes, claims = _fixtures()
    updated, amended, dropped = apply_amendments(
        [{"claim_id": "claim-a", "set_text": "fixed", "add_pages": [{"node_id": "n", "page": 2}]}],
        claims, docs, nodes, {"s1"})
    c = updated[0]
    assert dropped == [] and amended == {"claim-a"}
    assert c.id == "claim-a" and c.text == "fixed"
    assert sorted(s.page for s in c.sources) == [1, 2]


def test_unknown_claim_id_dropped():
    docs, nodes, claims = _fixtures()
    updated, amended, dropped = apply_amendments(
        [{"claim_id": "ghost", "set_text": "x"}], claims, docs, nodes, {"s1"})
    assert amended == set() and len(dropped) == 1 and updated[0].text == "original"


def test_unresolvable_added_page_drops_that_amendment():
    docs, nodes, claims = _fixtures()
    updated, amended, dropped = apply_amendments(
        [{"claim_id": "claim-a", "add_pages": [{"node_id": "n", "page": 99}]}],
        claims, docs, nodes, {"s1"})
    # page 99 does not resolve -> re-validation drops the added page; claim keeps its valid source
    assert amended == {"claim-a"} and sorted(s.page for s in updated[0].sources) == [1]


def test_set_support_and_evidence():
    docs, nodes, claims = _fixtures()
    updated, _, _ = apply_amendments(
        [{"claim_id": "claim-a", "set_support": "partially_supported", "set_evidence": "inferred"}],
        claims, docs, nodes, {"s1"})
    assert updated[0].support_level is SupportLevel.PARTIALLY_SUPPORTED
    assert updated[0].evidence_relation is EvidenceRelation.INFERRED
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_amend.py -v`
Expected: FAIL — `No module named 'tlddr.draft.amend'`.

- [ ] **Step 3: Implement `apply_amendments`**

Create `tlddr/draft/amend.py`:

```python
from tlddr.models import DraftClaim, ExtractedDoc, Node
from tlddr.draft.claims import validate_claims


def apply_amendments(records: list[dict], claims: list[DraftClaim],
                     docs: dict[str, ExtractedDoc], nodes: dict[str, Node],
                     known_section_ids: set[str] | None = None,
                     ) -> tuple[list[DraftClaim], set[str], list[str]]:
    """Apply claim-level edits in place and re-validate each amended claim through the same
    grounding checks as draft-commit. Returns (updated_claims, amended_ids, drop_messages).
    Drop-and-report: an unknown claim_id is reported; an amendment that fails validation is
    reported and the claim is left as-is."""
    by_id = {c.id: c for c in claims}
    dropped: list[str] = []
    amended: set[str] = set()
    raw_amended: list[dict] = []
    for r in records:
        cid = r.get("claim_id")
        claim = by_id.get(cid)
        if claim is None:
            dropped.append(f"unknown claim_id '{cid}'")
            continue
        raw = claim.model_dump(mode="json")
        if "set_text" in r:
            raw["text"] = r["set_text"]
        if "set_support" in r:
            raw["support_level"] = r["set_support"]
        if "set_evidence" in r:
            raw["evidence_relation"] = r["set_evidence"]
        for p in r.get("add_pages", []):
            raw["sources"].append({"node_id": p["node_id"], "page": p["page"]})
        raw_amended.append(raw)

    valid, findings = validate_claims(raw_amended, docs, nodes, known_section_ids)
    revalidated = {c.id: c for c in valid}
    for f in findings:
        dropped.append(f.question)
    updated = [revalidated.get(c.id, c) for c in claims]
    amended = set(revalidated)
    return updated, amended, dropped
```

Note: `validate_claims` preserves the supplied `id` (Task 1) and re-derives `source_confidence` and re-resolves every citation — so the added pages are validated and the model's confidence is never trusted. An invalid axis value or a claim left with zero resolvable citations becomes a `finding` (reported in `dropped`) and that claim keeps its prior committed value.

- [ ] **Step 4: Wire the CLI**

In `tlddr/cli.py`, add the import:

```python
from tlddr.draft.amend import apply_amendments
```

Add the function (near `draft_commit`):

```python
def draft_amend(amendments_path: Path, extracted_dir: Path, work_dir: Path,
                sections_path: Path | None = None) -> None:
    records = json.loads(amendments_path.read_text())
    docs = {p.stem: _load_doc(extracted_dir, p.stem) for p in extracted_dir.glob("*.json")}
    nodes = {n.id: n for n in (Node.model_validate_json(p.read_text())
                               for p in (work_dir / "nodes").glob("*.json"))}
    known_section_ids = section_ids(load_sections(sections_path)) if sections_path else None
    claims = _load_claims(work_dir)
    updated, amended, dropped = apply_amendments(records, claims, docs, nodes, known_section_ids)
    (work_dir / "claims.json").write_text(
        json.dumps([c.model_dump(mode="json") for c in updated], indent=2))

    questions_path = work_dir / "questions.json"
    questions = ([Question.model_validate(q) for q in json.loads(questions_path.read_text())]
                 if questions_path.exists() else [])
    flipped = 0
    for q in questions:
        if (q.claim_id in amended and q.status is QuestionStatus.REVISE_PENDING):
            q.status = QuestionStatus.REVISE_APPLIED
            flipped += 1
    questions_path.write_text(json.dumps([q.model_dump(mode="json") for q in questions], indent=2))
    for message in dropped:
        print(f"dropped amendment: {message}")
    print(f"amended {len(amended)} claims, applied {flipped} revise question(s)")
```

Add the subcommand (after the `draft-commit` parser):

```python
    damend = sub.add_parser("draft-amend", help="apply validated claim-level edits (the re-pass)")
    damend.add_argument("--amendments", required=True, type=Path)
    damend.add_argument("--output", type=Path, default=None)
```

Add the dispatch branch (after the `draft-commit` branch):

```python
    if args.command == "draft-amend":
        paths = Paths(resolve_base(args.output))
        sections = paths.sections if paths.sections.exists() else None
        draft_amend(args.amendments, paths.extracted, paths.work, sections)
        return 0
```

- [ ] **Step 5: Add a CLI integration test**

Add to `tests/test_answer_cli.py` (reuse its `_setup`-style base; a minimal one shown):

```python
def test_draft_amend_edits_claim_and_flips_revise(tmp_path):
    from tlddr.cli import main
    import json
    base = tmp_path / "out"; work = base / "work"; (work / "nodes").mkdir(parents=True)
    (work / "extracted").mkdir()
    from tlddr.models import ExtractedDoc, PageProvenance, SignalType, ExtractMethod
    doc = ExtractedDoc(id="n", source_path="/x", source_sha256="a", signal_type=SignalType.MIXED,
                       raw_title="N", content="--- page 1 ---\na\n--- page 2 ---\nb",
                       pages=[PageProvenance(page=1, method=ExtractMethod.PYMUPDF_TEXT, has_text_layer=True),
                              PageProvenance(page=2, method=ExtractMethod.PYMUPDF_TEXT, has_text_layer=True)],
                       extractor="pdf")
    (work / "extracted" / "n.json").write_text(doc.model_dump_json())
    (work / "claims.json").write_text(json.dumps([{
        "id": "claim-a", "section_id": "s1", "text": "orig",
        "sources": [{"node_id": "n", "page": 1}],
        "support_level": "fully_supported", "evidence_relation": "quoted"}]))
    (work / "questions.json").write_text(json.dumps([{
        "id": "verify-claim-a-downgrade", "raised_by": "verify", "claim_id": "claim-a",
        "section_id": "s1", "question": "q", "status": "revise_pending"}]))
    amend = tmp_path / "am.json"
    amend.write_text(json.dumps([{"claim_id": "claim-a", "set_text": "fixed",
                                  "add_pages": [{"node_id": "n", "page": 2}]}]))
    assert main(["draft-amend", "--amendments", str(amend), "--output", str(base)]) == 0
    claims = json.loads((work / "claims.json").read_text())
    assert claims[0]["text"] == "fixed" and sorted(s["page"] for s in claims[0]["sources"]) == [1, 2]
    q = json.loads((work / "questions.json").read_text())[0]
    assert q["status"] == "revise_applied"
```

- [ ] **Step 6: Run tests**

Run: `.venv/bin/pytest tests/test_amend.py tests/test_answer_cli.py -v`
Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add tlddr/draft/amend.py tlddr/cli.py tests/test_amend.py tests/test_answer_cli.py
git commit -m "feat(cli): add validated claim-level draft-amend re-pass"
```

---

### Task 5: Lifecycle markers on commit + assemble warning (AD-H5 remainder, F6)

**Files:**
- Modify: `tlddr/cli.py` (`draft_commit`, `understand_commit`, `assemble`)
- Test: `tests/test_answer_cli.py`

**Interfaces:**
- Consumes: `QuestionStatus` (Task 2), `Question.claim_id` (Task 3).
- Produces: `draft_commit` flips `REVISE_PENDING → REVISE_APPLIED` for questions matching the committed `section_id`; `understand_commit` flips for the committed `node_id`; `assemble` prints a warn-only line per lingering `REVISE_PENDING`.

- [ ] **Step 1: Write the failing test**

Add to `tests/test_answer_cli.py`:

```python
def test_assemble_warns_on_unapplied_revise(tmp_path, capsys):
    base = _work_with_questions(tmp_path, [
        {"id": "verify-claim-x-downgrade", "raised_by": "verify", "claim_id": "claim-x",
         "section_id": "s1", "question": "fix me", "status": "revise_pending"}])
    capsys.readouterr()
    main(["assemble", "--output", str(base)])
    assert "revise_pending" in capsys.readouterr().out.lower()


def test_assemble_silent_once_applied(tmp_path, capsys):
    base = _work_with_questions(tmp_path, [
        {"id": "verify-claim-x-downgrade", "raised_by": "verify", "claim_id": "claim-x",
         "section_id": "s1", "question": "fixed", "status": "revise_applied"}])
    capsys.readouterr()
    main(["assemble", "--output", str(base)])
    assert "revise_pending" not in capsys.readouterr().out.lower()
```

(If `_work_with_questions` from Task 8 of the loop plan isn't present in this file, add the small helper that writes `work/questions.json` + `work/sections.json` + empty `nodes/`.)

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_answer_cli.py -k "warns_on_unapplied or silent_once_applied" -v`
Expected: FAIL — no such warning printed.

- [ ] **Step 3: Add the assemble warning**

In `tlddr/cli.py` `assemble`, inside the `with bench.timed_stage(...)` block after `questions` is loaded, add:

```python
        pending = [q for q in questions if q.status is QuestionStatus.REVISE_PENDING]
        for q in pending:
            print(f"warning: {q.id} is revise_pending with no re-pass applied "
                  f"(section {q.section_id})")
```

- [ ] **Step 4: Add the commit lifecycle flips**

Add a small helper near `_append_questions` in `tlddr/cli.py`:

```python
def _apply_revises(work_dir: Path, match) -> None:
    """Flip REVISE_PENDING -> REVISE_APPLIED for questions the given predicate selects."""
    path = work_dir / "questions.json"
    if not path.exists():
        return
    questions = [Question.model_validate(q) for q in json.loads(path.read_text())]
    for q in questions:
        if q.status is QuestionStatus.REVISE_PENDING and match(q):
            q.status = QuestionStatus.REVISE_APPLIED
    path.write_text(json.dumps([q.model_dump(mode="json") for q in questions], indent=2))
```

In `draft_commit`, after writing `claims.json`, add (for each re-passed section):

```python
    for section in submitted_sections:
        _apply_revises(work_dir, lambda q, s=section: q.section_id == s)
```

In `understand_commit`, after writing the node's questions, add:

```python
    _apply_revises(out_dir, lambda q, nid=node.id: q.node_id == nid)
```

- [ ] **Step 5: Run tests**

Run: `.venv/bin/pytest tests/test_answer_cli.py tests/test_draft_cli.py tests/test_understand_cli.py -v`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add tlddr/cli.py tests/test_answer_cli.py
git commit -m "feat(cli): flip revises to applied on re-pass; warn on unapplied"
```

---

### Task 6: Skills + docs

**Files:**
- Modify: `skills/draft-verify/SKILL.md`, `skills/draft/SKILL.md`, `skills/review/SKILL.md`, `tlddr/CLAUDE.md`, `tlddr/draft/CLAUDE.md`, `docs/HANDOFF.md`

**Interfaces:** none (host-agent procedure + docs). Verification is a full green suite.

- [ ] **Step 1: Update the verify skill's verdict contract**

In `skills/draft-verify/SKILL.md`, change the verdict record from index-based to claim-id-based: verdicts are now `{claim_id, support_level, contradiction, note}` — the judge reads each claim's `id` from `claims.json` and references it (no more per-index ordering requirement). Update the "Agent supplies" and step-2 wording accordingly.

- [ ] **Step 2: Rewrite the re-pass mode in the draft + review skills**

In `skills/draft/SKILL.md` and `skills/review/SKILL.md`, replace the "Re-pass mode" section so it prescribes the **surgical** path: to act on a `revise` question, author an `amendments.json` (records `{claim_id, set_text?, add_pages?, set_support?, set_evidence?}` targeting the claim's `id` from `claims.json`) and run `tlddr draft-amend --amendments <f> --output "$TLDDR_OUTPUT"`, then re-run `draft-verify`. State explicitly: **do not regenerate the whole section** — a full re-draft churns unrelated claims and reopens accepted findings; amend only the claims the guidance names. Guidance is instruction, never a citation. Use `.venv/bin/tlddr` (or `.venv/bin/python -m tlddr.cli`) in every command example.

- [ ] **Step 3: Update the module indexes and handoff**

- `tlddr/CLAUDE.md`: `models.py` — `DraftClaim` gains `id`; `Question` now carries `claim_id` + `status` (not `resolved`/`disposition`); add `QuestionStatus`. `cli.py` — add `draft-amend`; note `draft_verify_commit` is claim_id/id-dedup based; note the lifecycle flips + assemble warning. Add `tlddr/draft/amend.py` and the new `answer.py` shape (question_identity removed).
- `tlddr/draft/CLAUDE.md`: `verify.py` — `ingest_verdicts(verdicts, claims, suppress_ids)`, claim_id-keyed, id = `verify-{claim_id}-{reason}`. `claims.py` — `_claim_id` + id assignment. Add `amend.py` (`apply_amendments`). `assemble.py` — reads `status`; warns on `REVISE_PENDING`.
- `docs/HANDOFF.md`: note the answer loop was hardened post-smoke-test (link the findings doc + this spec); the re-pass is now `draft-amend` (surgical), not full-section re-draft.

- [ ] **Step 4: Run the full suite**

Run: `.venv/bin/pytest`
Expected: PASS — all pre-existing tests plus the new ones green.

- [ ] **Step 5: Commit**

```bash
git add skills/ tlddr/CLAUDE.md tlddr/draft/CLAUDE.md docs/HANDOFF.md
git commit -m "docs(skills): prescribe surgical draft-amend re-pass; claim_id verdicts"
```

---

## Self-Review

**1. Spec coverage:**
- AD-H1 (durable id) → Task 1. AD-H2 (content-hash-at-birth, frozen, collision suffix) → Task 1 (`_claim_id`, `raw.get("id") or …`, `draft_commit` suffix). ✓
- AD-H3 (`draft-amend`, task-based ops, drop-and-report, re-validated, initial vs re-pass split) → Task 4 + Task 6 skill rewrite. ✓
- AD-H4 (claim_id link, verdict-by-claim_id, `verify-{claim_id}-{reason}`, id = dedup key, coarse) → Task 3. F5 masking-test fix → `test_dedup_robust_to_note_and_text_drift`. F10 → id no longer positional. ✓
- AD-H5 (`QuestionStatus` replacing resolved+disposition, transitions, assemble warning, Disposition kept as input, blocking subsumed) → Task 2 (model + answer-commit + consumers) and Task 5 (lifecycle flips + warning). ✓
- Data contracts (amendment record, verdict record) → Tasks 3, 4. ✓

**2. Placeholder scan:** No TBD/TODO; every code step shows complete code; every test has real assertions.

**3. Type consistency:** `_claim_id(section_id, text) -> str` (Task 1) consumed consistently. `apply_amendments(records, claims, docs, nodes, known_section_ids) -> (list[DraftClaim], set[str], list[str])` (Task 4) matches its cli caller. `ingest_verdicts(verdicts, claims, suppress_ids)` (Task 3) matches `draft_verify_commit`. `QuestionStatus` members (`OPEN/ACCEPTED/REVISE_PENDING/REVISE_APPLIED`) used identically across Tasks 2–5. `Question.status`/`.claim_id`/`DraftClaim.id` names consistent throughout. No drift found.
