# Answer Loop (D6) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the answer loop — a validated `answer-commit` CLI seam that ingests reviewer answers, routes each to the stage that can act on it, writes a deduped re-pass worklist, dedups on re-ingest so questions are never re-raised, and terminates on a dry re-verify — plus an interactive review-session skill.

**Architecture:** All new deterministic logic lives in one focused module, `tlddr/answer.py` (validation, routing, worklist building, question-identity for dedup, triage-slot parsing). The CLI grows one command (`answer-commit`) and modifies three existing seams (`draft-verify-commit` to dedup against resolved questions, `render_triage` to split Open/Resolved, `render_sidecar` to show accepted findings as disclosed caveats). The model-facing half is a new `skills/review/SKILL.md`. Answers reach a re-pass as guidance in `worklist.json`, never as citations — grounding is untouched.

**Tech Stack:** Python 3.14, pydantic, argparse, pytest. No new dependencies.

## Global Constraints

- **No new dependencies** — stdlib + pydantic only.
- **Machine-trust at the seam** — `answer-commit` validates every answer record against the known question set; unknown ids and invalid dispositions are reported and dropped, never silently accepted.
- **Grounding guardrail** — an answer is guidance only; it never becomes a citation. Claim citation validation in `draft-commit` is unchanged; claims still resolve to a real `(node_id, page)`.
- **Terminology** — the human role is the **Reviewer**, never "Engineer", in all code, skills, and docs.
- **No emojis** anywhere (code, comments, commits, docs).
- **Conventional commits**: `type(scope): description`.
- **Run tests** with `.venv/bin/pytest`. All 140 existing tests must stay green.
- **Branch** `feat/answer-loop` (already created off `main`).

---

## File Structure

**Create:**
- `tlddr/answer.py` — answer-loop deterministic core: `_normalize`, `question_identity`, `ingest_answers`, `build_worklist`, `parse_triage_answers`.
- `skills/review/SKILL.md` — the interactive review-session procedure.
- `tests/test_answer.py` — unit tests for `tlddr/answer.py` + the new `Question` fields.
- `tests/test_answer_cli.py` — end-to-end tests for the `answer-commit` command and the verify-dedup wiring.

**Modify:**
- `tlddr/models.py` — add `Disposition` enum; add `disposition` + `resolved` to `Question`.
- `tlddr/draft/verify.py` — `ingest_verdicts` gains a `suppress` set to skip verdicts matching resolved questions.
- `tlddr/understand/render.py` — `render_triage` splits questions into Open (answer slots) and Resolved (answer + disposition, no slot).
- `tlddr/draft/assemble.py` — `render_sidecar` shows accepted findings as disclosed caveats, hides resolved-revise, keeps open.
- `tlddr/cli.py` — add `answer_commit`, `_bump_repass_log`, `_format_worklist` helpers + `answer-commit` subcommand; rewire `draft_verify_commit`; add the B3 cycle warning to `assemble`.
- `skills/draft/SKILL.md`, `skills/understand/SKILL.md` — add a short "re-pass mode" note.
- `tlddr/CLAUDE.md`, `tlddr/understand/CLAUDE.md`, `tlddr/draft/CLAUDE.md`, `docs/HANDOFF.md`, `docs/chevron-run-status.md` — index/status updates.

---

### Task 1: Data model — `Disposition` enum + `Question` fields

**Files:**
- Modify: `tlddr/models.py:80-113`
- Test: `tests/test_answer.py`

**Interfaces:**
- Produces: `Disposition(str, Enum)` with members `REVISE = "revise"`, `ACCEPT = "accept"`; `Question.disposition: Disposition | None = None`; `Question.resolved: bool = False`.

- [ ] **Step 1: Write the failing test**

Create `tests/test_answer.py`:

```python
from tlddr.models import Question, Disposition


def test_question_answer_fields_default():
    q = Question(id="q-1", raised_by="verify", section_id="s1", question="is this right?")
    assert q.disposition is None
    assert q.resolved is False
    assert q.answer is None


def test_question_round_trips_resolved_answer():
    q = Question(id="q-1", raised_by="verify", section_id="s1", question="is this right?",
                 answer="Yes, keep it.", disposition=Disposition.ACCEPT, resolved=True)
    restored = Question.model_validate_json(q.model_dump_json())
    assert restored.disposition is Disposition.ACCEPT
    assert restored.resolved is True
    assert restored.answer == "Yes, keep it."
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_answer.py -v`
Expected: FAIL with `ImportError: cannot import name 'Disposition'`.

- [ ] **Step 3: Write minimal implementation**

In `tlddr/models.py`, add the enum after `EvidenceRelation` (after line 88):

```python
class Disposition(str, Enum):
    REVISE = "revise"      # answer routes to a re-pass
    ACCEPT = "accept"      # acknowledged finding; no re-pass; disclosed as a caveat
```

Then add two fields to `Question` (after `answer: str | None = None`, line 113):

```python
    disposition: Disposition | None = None
    resolved: bool = False
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/test_answer.py -v`
Expected: PASS (2 tests).

- [ ] **Step 5: Commit**

```bash
git add tlddr/models.py tests/test_answer.py
git commit -m "feat(models): add Disposition and Question answer-loop fields"
```

---

### Task 2: Question identity for dedup

**Files:**
- Create: `tlddr/answer.py`
- Test: `tests/test_answer.py`

**Interfaces:**
- Produces: `_normalize(text: str) -> str` (lowercase, whitespace-collapsed); `question_identity(q: Question) -> tuple[str, str, str]` returning `(raised_by, section_id-or-node_id-or-"", normalized question text)`.

- [ ] **Step 1: Write the failing test**

Add to `tests/test_answer.py`:

```python
from tlddr.answer import question_identity


def test_identity_ignores_case_and_whitespace():
    a = Question(id="v-1", raised_by="verify", section_id="s1", question="Off by ONE   page.")
    b = Question(id="v-9", raised_by="verify", section_id="s1", question="off by one page.")
    assert question_identity(a) == question_identity(b)


def test_identity_distinguishes_section_and_stage():
    base = dict(question="same text")
    q_s1 = Question(id="a", raised_by="verify", section_id="s1", **base)
    q_s2 = Question(id="b", raised_by="verify", section_id="s2", **base)
    q_draft = Question(id="c", raised_by="draft", section_id="s1", **base)
    assert question_identity(q_s1) != question_identity(q_s2)
    assert question_identity(q_s1) != question_identity(q_draft)


def test_identity_uses_node_id_when_no_section():
    q = Question(id="u-1", raised_by="understand", node_id="r972", question="what is this?")
    assert question_identity(q) == ("understand", "r972", "what is this?")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_answer.py -k identity -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'tlddr.answer'`.

- [ ] **Step 3: Write minimal implementation**

Create `tlddr/answer.py`:

```python
from tlddr.models import Question


def _normalize(text: str) -> str:
    """Fold case and collapse all whitespace so trivial rephrasings compare equal."""
    return " ".join(text.lower().split())


def question_identity(q: Question) -> tuple[str, str, str]:
    """Stable identity for dedup: same stage + same target + same (normalized) text."""
    target = q.section_id or q.node_id or ""
    return (q.raised_by, target, _normalize(q.question))
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/test_answer.py -k identity -v`
Expected: PASS (3 tests).

- [ ] **Step 5: Commit**

```bash
git add tlddr/answer.py tests/test_answer.py
git commit -m "feat(answer): add normalized question identity for dedup"
```

---

### Task 3: `ingest_answers` — validate, resolve, route, build worklist

**Files:**
- Modify: `tlddr/answer.py`
- Test: `tests/test_answer.py`

**Interfaces:**
- Consumes: `Question`, `Disposition` (Task 1).
- Produces:
  - `build_worklist(questions: list[Question]) -> dict` → `{"sections": [{"section_id", "guidance", "from"}], "nodes": [{"node_id", "guidance", "from"}]}`, deduped by target, sorted by target id, `guidance` = space-joined answers, `from` = list of question ids.
  - `ingest_answers(records: list[dict], questions: list[Question]) -> tuple[list[Question], dict, list[str]]` → the same `questions` list mutated in place (answer/disposition/resolved set, blocking cleared), the worklist from this batch's `revise` targets, and a list of human-readable drop messages.

- [ ] **Step 1: Write the failing test**

Add to `tests/test_answer.py`:

```python
from tlddr.answer import ingest_answers, build_worklist


def _q(id, raised_by, question="q?", section_id=None, node_id=None, blocking=False):
    return Question(id=id, raised_by=raised_by, question=question,
                    section_id=section_id, node_id=node_id, blocking=blocking)


def test_valid_answer_sets_fields_and_clears_blocking():
    qs = [_q("v-1", "verify", section_id="s1", blocking=True)]
    records = [{"id": "v-1", "disposition": "revise", "answer": "Keep it, cite p.47."}]
    updated, worklist, dropped = ingest_answers(records, qs)
    assert dropped == []
    q = updated[0]
    assert q.resolved is True
    assert q.disposition is Disposition.REVISE
    assert q.answer == "Keep it, cite p.47."
    assert q.blocking is False


def test_unknown_id_is_dropped():
    qs = [_q("v-1", "verify", section_id="s1")]
    records = [{"id": "nope", "disposition": "accept", "answer": "x"}]
    updated, worklist, dropped = ingest_answers(records, qs)
    assert len(dropped) == 1 and "nope" in dropped[0]
    assert updated[0].resolved is False


def test_invalid_disposition_is_dropped():
    qs = [_q("v-1", "verify", section_id="s1")]
    records = [{"id": "v-1", "disposition": "maybe", "answer": "x"}]
    updated, worklist, dropped = ingest_answers(records, qs)
    assert len(dropped) == 1 and "v-1" in dropped[0]
    assert updated[0].resolved is False


def test_verify_and_draft_route_to_section():
    qs = [_q("v-1", "verify", section_id="s1"), _q("d-1", "draft", section_id="s1")]
    records = [{"id": "v-1", "disposition": "revise", "answer": "A."},
               {"id": "d-1", "disposition": "revise", "answer": "B."}]
    _, worklist, _ = ingest_answers(records, qs)
    assert worklist["nodes"] == []
    assert len(worklist["sections"]) == 1
    entry = worklist["sections"][0]
    assert entry["section_id"] == "s1"
    assert entry["guidance"] == "A. B."          # deduped target, both answers joined
    assert sorted(entry["from"]) == ["d-1", "v-1"]


def test_understand_routes_to_node():
    qs = [_q("u-1", "understand", node_id="r972")]
    records = [{"id": "u-1", "disposition": "revise", "answer": "It supersedes r304."}]
    _, worklist, _ = ingest_answers(records, qs)
    assert worklist["sections"] == []
    assert worklist["nodes"][0]["node_id"] == "r972"
    assert worklist["nodes"][0]["guidance"] == "It supersedes r304."


def test_accept_does_not_enter_worklist():
    qs = [_q("v-1", "verify", section_id="s1")]
    records = [{"id": "v-1", "disposition": "accept", "answer": "Acceptable nit."}]
    updated, worklist, _ = ingest_answers(records, qs)
    assert updated[0].resolved is True
    assert worklist["sections"] == [] and worklist["nodes"] == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_answer.py -k "answer or route or worklist or blocking" -v`
Expected: FAIL with `ImportError: cannot import name 'ingest_answers'`.

- [ ] **Step 3: Write minimal implementation**

Append to `tlddr/answer.py` (add `Disposition` to the import):

```python
from tlddr.models import Question, Disposition


def build_worklist(questions: list[Question]) -> dict:
    """Group revise-questions by their re-pass target (dedup), joining guidance."""
    sections: dict[str, dict] = {}
    nodes: dict[str, dict] = {}
    for q in questions:
        if q.raised_by == "understand" and q.node_id:
            bucket = nodes.setdefault(q.node_id, {"guidance": [], "from": []})
        elif q.section_id:
            bucket = sections.setdefault(q.section_id, {"guidance": [], "from": []})
        else:
            continue
        if q.answer:
            bucket["guidance"].append(q.answer)
        bucket["from"].append(q.id)
    return {
        "sections": [{"section_id": k, "guidance": " ".join(v["guidance"]), "from": v["from"]}
                     for k, v in sorted(sections.items())],
        "nodes": [{"node_id": k, "guidance": " ".join(v["guidance"]), "from": v["from"]}
                  for k, v in sorted(nodes.items())],
    }


def ingest_answers(records: list[dict],
                   questions: list[Question]) -> tuple[list[Question], dict, list[str]]:
    """Validate answer records against the known question set, resolve matches, and
    build the deduped re-pass worklist from this batch's revise targets."""
    by_id = {q.id: q for q in questions}
    dropped: list[str] = []
    revised: list[Question] = []
    for r in records:
        qid = r.get("id")
        q = by_id.get(qid)
        if q is None:
            dropped.append(f"unknown question id '{qid}'")
            continue
        try:
            disposition = Disposition(r.get("disposition"))
        except ValueError:
            dropped.append(f"'{qid}': invalid disposition '{r.get('disposition')}'")
            continue
        q.answer = r.get("answer")
        q.disposition = disposition
        q.resolved = True
        q.blocking = False
        if disposition is Disposition.REVISE:
            revised.append(q)
    return questions, build_worklist(revised), dropped
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/test_answer.py -v`
Expected: PASS (all tests, including Tasks 1-2).

- [ ] **Step 5: Commit**

```bash
git add tlddr/answer.py tests/test_answer.py
git commit -m "feat(answer): ingest and validate answers, route to deduped worklist"
```

---

### Task 4: `parse_triage_answers` — the `--triage` slot fallback

**Files:**
- Modify: `tlddr/answer.py`
- Test: `tests/test_answer.py`

**Interfaces:**
- Produces: `parse_triage_answers(triage_md: str) -> tuple[list[dict], list[str]]` — reads `> answer:` slots under `### <id>` headings, requiring a leading `[revise]` / `[accept]` tag; returns answer records (`{"id", "disposition", "answer"}`) and a list of ids whose slot was filled but untagged (skipped). Unfilled slots are ignored silently.

- [ ] **Step 1: Write the failing test**

Add to `tests/test_answer.py`:

```python
from tlddr.answer import parse_triage_answers

_TRIAGE = """# Triage

## Open questions
### v-1
Off by one page.
> answer: [revise] Figure is right, cite p.47.

### v-2
Glossary drift.
> answer: [accept] Acceptable, disclose it.

### v-3
Untouched question.
> answer:

### v-4
Filled but not tagged.
> answer: I think this is fine.
"""


def test_parse_triage_reads_tagged_slots():
    records, skipped = parse_triage_answers(_TRIAGE)
    by_id = {r["id"]: r for r in records}
    assert by_id["v-1"] == {"id": "v-1", "disposition": "revise",
                            "answer": "Figure is right, cite p.47."}
    assert by_id["v-2"]["disposition"] == "accept"
    assert "v-3" not in by_id          # unfilled slot ignored
    assert "v-4" not in by_id          # untagged slot skipped
    assert skipped == ["v-4"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_answer.py -k triage -v`
Expected: FAIL with `ImportError: cannot import name 'parse_triage_answers'`.

- [ ] **Step 3: Write minimal implementation**

Append to `tlddr/answer.py` (add `import re` at the top of the file):

```python
_HEADING = re.compile(r"^###\s+(\S+)")
_ANSWER = re.compile(r"^>\s*answer:\s*(.*)$")
_TAG = re.compile(r"^\[(revise|accept)\]\s*(.*)$", re.IGNORECASE)


def parse_triage_answers(triage_md: str) -> tuple[list[dict], list[str]]:
    """Parse filled `> answer:` slots (with a leading [revise]/[accept] tag) into
    answer records. Untagged-but-filled slots are reported as skipped."""
    records: list[dict] = []
    skipped: list[str] = []
    current_id: str | None = None
    for line in triage_md.splitlines():
        heading = _HEADING.match(line)
        if heading:
            current_id = heading.group(1).strip()
            continue
        answer = _ANSWER.match(line)
        if answer and current_id:
            body = answer.group(1).strip()
            if not body:
                continue                       # unfilled slot
            tag = _TAG.match(body)
            if not tag:
                skipped.append(current_id)     # filled but no tag -> machine-trust skip
                continue
            records.append({"id": current_id, "disposition": tag.group(1).lower(),
                            "answer": tag.group(2).strip()})
    return records, skipped
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/test_answer.py -k triage -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add tlddr/answer.py tests/test_answer.py
git commit -m "feat(answer): parse triage answer slots as the --triage fallback"
```

---

### Task 5: Verify dedup — suppress verdicts matching resolved questions

**Files:**
- Modify: `tlddr/draft/verify.py:1-29`
- Test: `tests/test_draft_verify.py`

**Interfaces:**
- Consumes: `question_identity` (Task 2).
- Produces: `ingest_verdicts(verdicts, claims, suppress: set | None = None) -> list[Question]` — a candidate verify question whose `question_identity` is in `suppress` is skipped (already-resolved, not re-raised).

- [ ] **Step 1: Write the failing test**

Add to `tests/test_draft_verify.py`:

```python
from tlddr.answer import question_identity


def test_verdict_matching_resolved_question_is_suppressed():
    claims = [_claim(support=SupportLevel.FULLY_SUPPORTED)]
    verdicts = [{"index": 0, "support_level": "unsupported", "contradiction": False,
                 "note": "page does not state this"}]
    # first pass raises the question
    first = ingest_verdicts(verdicts, claims)
    assert len(first) == 1
    # that question is now resolved; feeding its identity as suppress skips the re-raise
    suppress = {question_identity(first[0])}
    assert ingest_verdicts(verdicts, claims, suppress) == []


def test_new_verdict_still_surfaces_despite_suppress():
    claims = [_claim(support=SupportLevel.FULLY_SUPPORTED)]
    verdicts = [{"index": 0, "support_level": "unsupported", "contradiction": False,
                 "note": "a different, genuinely new problem"}]
    suppress = {("verify", "s1", "some unrelated resolved question")}
    assert len(ingest_verdicts(verdicts, claims, suppress)) == 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_draft_verify.py -k suppress -v`
Expected: FAIL with `TypeError: ingest_verdicts() takes 2 positional arguments but 3 were given`.

- [ ] **Step 3: Write minimal implementation**

Rewrite `tlddr/draft/verify.py`:

```python
from tlddr.models import DraftClaim, SupportLevel, Question
from tlddr.answer import question_identity

_RANK = {SupportLevel.UNSUPPORTED: 0, SupportLevel.PARTIALLY_SUPPORTED: 1,
         SupportLevel.FULLY_SUPPORTED: 2}


def ingest_verdicts(verdicts: list[dict], claims: list[DraftClaim],
                    suppress: set | None = None) -> list[Question]:
    suppress = suppress or set()
    questions: list[Question] = []
    for v in verdicts:
        index = v.get("index")
        if not isinstance(index, int) or index < 0 or index >= len(claims):
            continue
        try:
            judged = SupportLevel(v["support_level"])
        except (KeyError, ValueError):
            continue
        claim = claims[index]
        downgrade = _RANK[judged] < _RANK[claim.support_level]
        if not (downgrade or v.get("contradiction")):
            continue
        reason = "contradiction" if v.get("contradiction") else \
            f"judge:{judged.value} < drafter:{claim.support_level.value}"
        note = (v.get("note") or "").strip()
        candidate = Question(
            id=f"verify-{index}", raised_by="verify", node_id=None,
            section_id=claim.section_id,
            question=f"[{reason}] '{claim.text[:80]}' — {note}".rstrip(" -"),
        )
        if question_identity(candidate) in suppress:
            continue
        questions.append(candidate)
    return questions
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/test_draft_verify.py -v`
Expected: PASS (all, including the 7 existing tests — the new `suppress` arg defaults to `None`).

- [ ] **Step 5: Commit**

```bash
git add tlddr/draft/verify.py tests/test_draft_verify.py
git commit -m "feat(verify): suppress verdicts matching already-resolved questions"
```

---

### Task 6: `render_triage` — split Open vs Resolved + re-derive display triage

**Files:**
- Modify: `tlddr/understand/render.py:1,28-37,57-67`
- Test: `tests/test_render.py`

**Interfaces:**
- Consumes: `derive_triage` (existing, `tlddr/understand/triage.py`).
- Produces: `render_triage` now (a) groups nodes by a **display triage re-derived from each node's unresolved questions** (so a node de-escalates once its blocking question is resolved — AD4's visible de-escalation, without mutating stored `node.triage`), and (b) splits questions into a `## Open questions` section (unresolved only, each with a `> answer:` slot) and, when any resolved questions exist, a `## Resolved questions` section (each showing `(disposition)` and the answer text, no slot).
- Note: pre-answer-loop this is a no-op — a node's unresolved questions equal its commit-time questions, so the re-derived triage matches the stored one. It only diverges (downward) once the loop resolves a question.

- [ ] **Step 1: Write the failing test**

Add to `tests/test_render.py` (import `Disposition`):

```python
from tlddr.models import Disposition


def test_triage_separates_open_and_resolved():
    nodes = [_node("a", Triage.GREEN)]
    open_q = Question(id="v-1", raised_by="verify", section_id="s1",
                      question="Open question here?")
    resolved_q = Question(id="v-2", raised_by="verify", section_id="s1",
                          question="Resolved question here?", answer="Yes, keep it.",
                          disposition=Disposition.ACCEPT, resolved=True)
    md = render_triage(nodes, [open_q, resolved_q])

    assert "## Open questions" in md
    assert "## Resolved questions" in md
    open_block = md.split("## Open questions")[1].split("## Resolved questions")[0]
    resolved_block = md.split("## Resolved questions")[1]

    assert "Open question here?" in open_block
    assert "> answer:" in open_block
    assert "Resolved question here?" not in open_block   # resolved not in Open

    assert "(accept)" in resolved_block
    assert "Yes, keep it." in resolved_block


def test_triage_omits_resolved_section_when_none():
    md = render_triage([_node("a", Triage.GREEN)], [])
    assert "## Resolved questions" not in md


def test_resolving_blocking_question_deescalates_node():
    # a node stored GREEN with a live blocking question re-derives to RED...
    node = _node("a", Triage.GREEN)
    blocking = Question(id="u-1", raised_by="understand", node_id="a",
                        question="Blocked on which spec?", blocking=True)
    red_md = render_triage([node], [blocking])
    red_block = red_md.split("## Red")[1].split("## Amber")[0]
    assert "[[a]]" in red_block
    # ...and once resolved, it drops out of Red (de-escalation is visible)
    resolved = Question(id="u-1", raised_by="understand", node_id="a",
                        question="Blocked on which spec?", blocking=False,
                        answer="Spec v3.", disposition=Disposition.REVISE, resolved=True)
    green_md = render_triage([node], [resolved])
    green_red_block = green_md.split("## Red")[1].split("## Amber")[0]
    assert "[[a]]" not in green_red_block
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_render.py -k "separates or omits_resolved or deescalates" -v`
Expected: FAIL — `## Resolved questions` not found / resolved question in open block / node stays in Red after resolution.

- [ ] **Step 3: Write minimal implementation**

Add the import at the top of `tlddr/understand/render.py` (after line 1):

```python
from tlddr.understand.triage import derive_triage
```

Replace the node-grouping line (line 31, `by_triage = {t: [n for n in nodes if n.triage is t] for t in _GROUP_ORDER}`) with a helper that re-derives from each node's unresolved questions. Add this helper above `render_triage`:

```python
def _display_triage(node: Node, questions: list[Question]) -> Triage:
    """Triage as it stands now: re-derive from the node's still-open questions so a
    resolved blocking question visibly de-escalates the node (never mutates stored state)."""
    node_qs = [q for q in questions if q.node_id == node.id and not q.resolved]
    return derive_triage(node.confidence_extraction, node.confidence_interpretation, node_qs)
```

and change the grouping inside `render_triage`:

```python
    by_triage = {t: [n for n in nodes if _display_triage(n, questions) is t]
                 for t in _GROUP_ORDER}
```

Then replace the final `## Open questions` block in `tlddr/understand/render.py` (lines 57-66) with:

```python
    open_qs = [q for q in questions if not q.resolved]
    resolved_qs = [q for q in questions if q.resolved]

    lines.append("## Open questions")
    if not open_qs:
        lines.append("None.")
    for q in open_qs:
        target = f" ([[{q.node_id}]])" if q.node_id else ""
        flag = " [blocking]" if q.blocking else ""
        lines.append(f"### {q.id}{flag}{target}")
        lines.append(q.question)
        lines.append("> answer:")
        lines.append("")

    if resolved_qs:
        lines.append("## Resolved questions")
        for q in resolved_qs:
            target = f" ([[{q.node_id}]])" if q.node_id else ""
            disposition = q.disposition.value if q.disposition else "resolved"
            lines.append(f"### {q.id} ({disposition}){target}")
            lines.append(q.question)
            lines.append(f"> answer: {q.answer or ''}")
            lines.append("")
    return "\n".join(lines) + "\n"
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/test_render.py -v`
Expected: PASS (all, including existing triage tests — the `## Open questions` heading and `> answer:` slots are unchanged for open questions).

- [ ] **Step 5: Commit**

```bash
git add tlddr/understand/render.py tests/test_render.py
git commit -m "feat(render): split triage questions into Open and Resolved"
```

---

### Task 7: `render_sidecar` — accepted findings as disclosed caveats

**Files:**
- Modify: `tlddr/draft/assemble.py:1-3,58-62`
- Test: `tests/test_draft_assemble.py`

**Interfaces:**
- Produces: `render_sidecar` now renders, per section: `**Open questions:**` (unresolved only), and `**Disclosed caveats (accepted findings):**` (resolved + `disposition == ACCEPT`, showing the answer). Resolved-revise questions are shown in neither (the correction is in the claims).

- [ ] **Step 1: Write the failing test**

Add to `tests/test_draft_assemble.py` (check existing imports; import `Question`, `Disposition`):

```python
from tlddr.models import Question, Disposition
from tlddr.draft.assemble import render_sidecar


def _s1_claim():
    from tlddr.models import DraftClaim, Citation, SupportLevel, EvidenceRelation, Confidence
    return DraftClaim(section_id="s1", text="A claim.",
                      sources=[Citation(node_id="n", page=1, source_confidence=Confidence.HIGH)],
                      support_level=SupportLevel.FULLY_SUPPORTED,
                      evidence_relation=EvidenceRelation.QUOTED)


def test_sidecar_shows_accepted_as_caveat_hides_revise():
    sections = [Section(id="s1", title="Overview")]
    claims = [_s1_claim()]
    questions = [
        Question(id="v-open", raised_by="verify", section_id="s1", question="Still open?"),
        Question(id="v-acc", raised_by="verify", section_id="s1", question="Minor nit?",
                 answer="Acceptable.", disposition=Disposition.ACCEPT, resolved=True),
        Question(id="v-rev", raised_by="verify", section_id="s1", question="Was wrong?",
                 answer="Fixed it.", disposition=Disposition.REVISE, resolved=True),
    ]
    md = render_sidecar(sections, claims, questions)
    assert "Open questions" in md and "Still open?" in md
    assert "Disclosed caveats" in md and "Minor nit?" in md and "Acceptable." in md
    assert "Was wrong?" not in md          # resolved-revise hidden
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_draft_assemble.py -k "caveat" -v`
Expected: FAIL — "Disclosed caveats" not found and/or "Was wrong?" present.

- [ ] **Step 3: Write minimal implementation**

In `tlddr/draft/assemble.py`, add `Disposition` to the model import (line 1-3):

```python
from tlddr.models import (
    DraftClaim, Section, Question, SupportLevel, EvidenceRelation, Confidence, Disposition,
)
```

Replace the section-questions block (lines 58-61):

```python
        section_qs = [q for q in questions if q.section_id == s.id]
        open_qs = [q for q in section_qs if not q.resolved]
        caveats = [q for q in section_qs
                   if q.resolved and q.disposition is Disposition.ACCEPT]
        if open_qs:
            lines.append("**Open questions:**")
            lines += [f"- ({q.raised_by}) {q.question}" for q in open_qs]
        if caveats:
            lines.append("**Disclosed caveats (accepted findings):**")
            lines += [f"- ({q.raised_by}) {q.question} — {q.answer or ''}".rstrip(" —")
                      for q in caveats]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/test_draft_assemble.py -v`
Expected: PASS (all, including existing sidecar tests — open questions render unchanged).

- [ ] **Step 5: Commit**

```bash
git add tlddr/draft/assemble.py tests/test_draft_assemble.py
git commit -m "feat(assemble): render accepted findings as disclosed caveats"
```

---

### Task 8: `answer-commit` CLI command (both input modes) + worklist

**Files:**
- Modify: `tlddr/cli.py:13-23` (imports), `:248-252` (`draft_verify_commit`), add `answer_commit` + helpers near `:248`, add subcommand `:328`, add dispatch `:390`.
- Test: `tests/test_answer_cli.py`

**Interfaces:**
- Consumes: `ingest_answers`, `parse_triage_answers` (Tasks 3-4), `question_identity` (Task 2), `understand_render` (existing).
- Produces:
  - `answer_commit(answers_path: Path | None, triage_path: Path | None, work_dir: Path, sections_path: Path | None = None, vault_dir: Path | None = None) -> None` — loads `questions.json`, ingests via the chosen input mode, persists resolved questions, writes `work_dir/worklist.json`, prints the worklist, and re-renders `_triage.md` when `vault_dir` is given.
  - `_format_worklist(worklist: dict) -> str`.
  - Rewired `draft_verify_commit`: builds a `suppress` set from resolved questions and preserves resolved verify questions across re-ingest.

- [ ] **Step 1: Write the failing test**

Create `tests/test_answer_cli.py`:

```python
import json
from pathlib import Path
from tlddr.cli import main
from tlddr.models import Question


def _work_with_questions(tmp: Path, questions: list[dict]) -> Path:
    base = tmp / "out"
    work = base / "work"
    nodes = work / "nodes"
    nodes.mkdir(parents=True)
    (work / "questions.json").write_text(json.dumps(questions))
    (work / "sections.json").write_text(json.dumps([{"id": "s1", "title": "Overview"}]))
    return base


def _load_qs(base: Path) -> list[dict]:
    return json.loads((base / "work" / "questions.json").read_text())


def test_answer_commit_resolves_and_writes_worklist(tmp_path):
    base = _work_with_questions(tmp_path, [
        {"id": "v-1", "raised_by": "verify", "section_id": "s1", "question": "Fix this?",
         "blocking": True},
        {"id": "v-2", "raised_by": "verify", "section_id": "s1", "question": "Nit?"},
    ])
    answers = tmp_path / "answers.json"
    answers.write_text(json.dumps([
        {"id": "v-1", "disposition": "revise", "answer": "Re-draft with p.47."},
        {"id": "v-2", "disposition": "accept", "answer": "Fine as is."},
    ]))

    assert main(["answer-commit", "--answers", str(answers), "--output", str(base)]) == 0

    qs = {q["id"]: q for q in _load_qs(base)}
    assert qs["v-1"]["resolved"] is True and qs["v-1"]["disposition"] == "revise"
    assert qs["v-1"]["blocking"] is False              # cleared
    assert qs["v-2"]["disposition"] == "accept"

    worklist = json.loads((base / "work" / "worklist.json").read_text())
    assert [s["section_id"] for s in worklist["sections"]] == ["s1"]   # revise only
    assert "Re-draft with p.47." in worklist["sections"][0]["guidance"]


def test_answer_commit_triage_mode(tmp_path):
    base = _work_with_questions(tmp_path, [
        {"id": "v-1", "raised_by": "verify", "section_id": "s1", "question": "Fix this?"},
    ])
    triage = tmp_path / "_triage.md"
    triage.write_text("## Open questions\n### v-1\nFix this?\n> answer: [revise] Cite p.47.\n")

    assert main(["answer-commit", "--triage", str(triage), "--output", str(base)]) == 0
    qs = {q["id"]: q for q in _load_qs(base)}
    assert qs["v-1"]["resolved"] is True
    assert qs["v-1"]["answer"] == "Cite p.47."


def test_answer_commit_rerenders_triage_with_resolved(tmp_path):
    base = _work_with_questions(tmp_path, [
        {"id": "v-1", "raised_by": "verify", "section_id": "s1", "question": "Fix this?"},
    ])
    answers = tmp_path / "answers.json"
    answers.write_text(json.dumps([{"id": "v-1", "disposition": "accept", "answer": "ok"}]))
    main(["answer-commit", "--answers", str(answers), "--output", str(base)])
    triage_md = (base / "vault" / "_triage.md").read_text()
    assert "## Resolved questions" in triage_md
    assert "(accept)" in triage_md


def test_answer_commit_reports_unknown_id(tmp_path, capsys):
    base = _work_with_questions(tmp_path, [
        {"id": "v-1", "raised_by": "verify", "section_id": "s1", "question": "Fix this?"},
    ])
    answers = tmp_path / "answers.json"
    answers.write_text(json.dumps([{"id": "ghost", "disposition": "accept", "answer": "x"}]))
    main(["answer-commit", "--answers", str(answers), "--output", str(base)])
    assert "ghost" in capsys.readouterr().out
    assert _load_qs(base)[0]["resolved"] is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_answer_cli.py -v`
Expected: FAIL — `answer-commit` is not a known subcommand (argparse SystemExit).

- [ ] **Step 3: Write minimal implementation**

In `tlddr/cli.py`, extend the imports (after line 23):

```python
from tlddr.answer import ingest_answers, parse_triage_answers, question_identity
```

Rewrite `draft_verify_commit` (lines 248-252) to build a suppress set and preserve resolved verify questions:

```python
def draft_verify_commit(verdicts_path: Path, work_dir: Path) -> None:
    verdicts = json.loads(verdicts_path.read_text())
    questions_path = work_dir / "questions.json"
    existing = ([Question.model_validate(q) for q in json.loads(questions_path.read_text())]
                if questions_path.exists() else [])
    suppress = {question_identity(q) for q in existing if q.resolved}
    new_qs = ingest_verdicts(verdicts, _load_claims(work_dir), suppress)
    _append_questions(
        work_dir, new_qs,
        drop=lambda q: q.get("raised_by") == "verify" and not q.get("resolved"))
    print(f"raised {len(new_qs)} verify questions")
```

Add the new functions just after `draft_verify_commit`:

```python
def _format_worklist(worklist: dict) -> str:
    lines = ["RE-PASS WORKLIST"]
    if worklist["sections"]:
        lines.append("Section re-passes (re-draft -> re-verify):")
        for s in worklist["sections"]:
            lines.append(f"  - {s['section_id']}   from: {', '.join(s['from'])}")
            lines.append(f"    guidance: {s['guidance']}")
    if worklist["nodes"]:
        lines.append("Node re-passes (re-understand):")
        for n in worklist["nodes"]:
            lines.append(f"  - {n['node_id']}   from: {', '.join(n['from'])}")
            lines.append(f"    guidance: {n['guidance']}")
    if not worklist["sections"] and not worklist["nodes"]:
        lines.append("(nothing to re-pass)")
    return "\n".join(lines)


def answer_commit(answers_path: Path | None, triage_path: Path | None, work_dir: Path,
                  sections_path: Path | None = None, vault_dir: Path | None = None) -> None:
    questions_path = work_dir / "questions.json"
    questions = ([Question.model_validate(q) for q in json.loads(questions_path.read_text())]
                 if questions_path.exists() else [])
    if triage_path is not None:
        records, skipped = parse_triage_answers(triage_path.read_text())
        for qid in skipped:
            print(f"skipped slot for '{qid}': filled but no [revise]/[accept] tag")
    else:
        records = json.loads(answers_path.read_text())

    updated, worklist, dropped = ingest_answers(records, questions)
    for message in dropped:
        print(f"dropped answer: {message}")
    questions_path.write_text(
        json.dumps([q.model_dump(mode="json") for q in updated], indent=2))
    (work_dir / "worklist.json").write_text(json.dumps(worklist, indent=2))
    print(_format_worklist(worklist))

    if vault_dir is not None:
        understand_render(work_dir, vault_dir, sections_path)
```

Add the subcommand in `main` (after the `dverify` parser, near line 330):

```python
    acommit = sub.add_parser("answer-commit",
                             help="ingest reviewer answers and build the re-pass worklist")
    asrc = acommit.add_mutually_exclusive_group(required=True)
    asrc.add_argument("--answers", type=Path, default=None)
    asrc.add_argument("--triage", type=Path, default=None)
    acommit.add_argument("--output", type=Path, default=None)
```

Add the dispatch branch (after the `draft-verify-commit` branch, near line 393):

```python
    if args.command == "answer-commit":
        paths = Paths(resolve_base(args.output))
        sections = paths.sections if paths.sections.exists() else None
        answer_commit(args.answers, args.triage, paths.work, sections, paths.vault)
        return 0
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/test_answer_cli.py tests/test_draft_cli.py -v`
Expected: PASS (new CLI tests + existing draft CLI tests, incl. the verify-idempotency test).

- [ ] **Step 5: Commit**

```bash
git add tlddr/cli.py tests/test_answer_cli.py
git commit -m "feat(cli): add answer-commit and wire verify dedup against resolved"
```

---

### Task 9: B3 backstop — re-pass counter + assemble cycle warning

**Files:**
- Modify: `tlddr/cli.py` (`answer_commit` + `assemble`)
- Test: `tests/test_answer_cli.py`

**Interfaces:**
- Consumes: `answer_commit`, `assemble` (existing).
- Produces: `_bump_repass_log(work_dir: Path, worklist: dict) -> None` writing `work_dir/repass_log.json` (`{target_id: count}`); `assemble` prints a warning for any target with count >= 3.

- [ ] **Step 1: Write the failing test**

Add to `tests/test_answer_cli.py`:

```python
def test_repass_log_warns_after_three_cycles(tmp_path, capsys):
    base = _work_with_questions(tmp_path, [
        {"id": "v-1", "raised_by": "verify", "section_id": "s1", "question": "Fix this?"},
    ])
    answers = tmp_path / "answers.json"
    answers.write_text(json.dumps([{"id": "v-1", "disposition": "revise", "answer": "redo"}]))

    # three answer-commit rounds against the same section
    for _ in range(3):
        main(["answer-commit", "--answers", str(answers), "--output", str(base)])

    log = json.loads((base / "work" / "repass_log.json").read_text())
    assert log["s1"] == 3

    capsys.readouterr()                       # clear
    main(["assemble", "--output", str(base)])
    assert "cycled 3 times" in capsys.readouterr().out
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_answer_cli.py -k repass_log -v`
Expected: FAIL — `repass_log.json` does not exist.

- [ ] **Step 3: Write minimal implementation**

In `tlddr/cli.py`, add the helper before `answer_commit`:

```python
def _bump_repass_log(work_dir: Path, worklist: dict) -> None:
    path = work_dir / "repass_log.json"
    log = json.loads(path.read_text()) if path.exists() else {}
    for item in worklist["sections"]:
        log[item["section_id"]] = log.get(item["section_id"], 0) + 1
    for item in worklist["nodes"]:
        log[item["node_id"]] = log.get(item["node_id"], 0) + 1
    path.write_text(json.dumps(log, indent=2))
```

In `answer_commit`, call it right after writing `worklist.json`:

```python
    (work_dir / "worklist.json").write_text(json.dumps(worklist, indent=2))
    _bump_repass_log(work_dir, worklist)
    print(_format_worklist(worklist))
```

In `assemble`, after loading `questions` and before/after writing the report (inside the `with bench.timed_stage(...)` block), add the warning:

```python
        repass_log_path = work_dir / "repass_log.json"
        if repass_log_path.exists():
            log = json.loads(repass_log_path.read_text())
            for target, count in sorted(log.items()):
                if count >= 3:
                    print(f"warning: '{target}' has cycled {count} times "
                          f"through the answer loop")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/test_answer_cli.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add tlddr/cli.py tests/test_answer_cli.py
git commit -m "feat(cli): count re-passes and warn on 3+ answer-loop cycles"
```

---

### Task 10: The review-session skill + re-pass notes + docs

**Files:**
- Create: `skills/review/SKILL.md`
- Modify: `skills/draft/SKILL.md`, `skills/understand/SKILL.md` (re-pass mode note)
- Modify: `tlddr/CLAUDE.md`, `tlddr/understand/CLAUDE.md`, `tlddr/draft/CLAUDE.md`, `docs/HANDOFF.md`, `docs/chevron-run-status.md`

**Interfaces:** none (host-agent procedure + documentation). Verification is a full green test run.

- [ ] **Step 1: Write the review skill**

Create `skills/review/SKILL.md`:

```markdown
---
name: review
description: Use when a Reviewer works the open question queue after a draft/verify run — an interactive, one-question-at-a-time session that ingests signed-off answers and drives the scoped re-passes.
---

# review

## Overview

The interactive review session for the answer loop. The Reviewer works the open
question queue one question at a time; each signed-off decision is committed via
`tlddr answer-commit`, which routes it to a re-pass. Generation never blocked on
the Reviewer — this session runs whenever they are ready, and is resumable.

## Deterministic/Agent Boundary

- **Agent (this session) supplies:** for each signed-off question, an answer record
  `{id, disposition, answer}` where `disposition` is `revise` (re-draft/re-understand
  with this answer as guidance) or `accept` (acknowledge as a disclosed caveat).
- **CLI validates and acts:** `answer-commit` validates each id against the question
  store and the disposition against `{revise, accept}`, sets the answer, clears
  `blocking`, and writes the deduped re-pass worklist. Unknown ids are reported and
  dropped.
- **Grounding guardrail:** an answer is guidance, never evidence. A re-draft still
  cites real `(node_id, page)` sources; the answer cannot become a citation.

## Output location

All paths are relative to the run's output base, `$TLDDR_OUTPUT` (default `.tlddr`).

    export TLDDR_OUTPUT=<your-output-dir>

## Prerequisites

- `$TLDDR_OUTPUT/work/questions.json` exists with open (unresolved) questions.
- `$TLDDR_OUTPUT/work/sections.json`, `nodes/`, and `extracted/` exist (a completed
  draft/verify run).

## Procedure

### 1. Load the open queue

Read `$TLDDR_OUTPUT/work/questions.json`. Work only the questions where `resolved`
is false. Order them blocking-first, then by section. Tell the Reviewer how many
open questions there are.

### 2. Present ONE question at a time

Do not batch. For each open question:

1. **State the question** clearly and plainly.
2. **Link the pertinent documents** for retrieval: the `[[node_id]]` of the source(s)
   and, for a `verify` question, the cited pages of the claim under review (look them
   up in `work/claims.json`). The Reviewer may need to open these before deciding.
3. **Offer a probable answer.** Say what you think the answer most likely is and why,
   grounded in the cited pages. Where the question genuinely admits more than one
   reading, present the **ranked interpretations** as options (best first), the way
   the brainstorming skill presents solution options.
4. **Discuss.** The Reviewer may push back, ask for more context, or check the docs.
   This conversation is NOT persisted — only the final decision is.

### 3. Sign-off (one deliberate decision)

When the Reviewer agrees, present the decision back as a single quoted, italicised
line and its disposition, for explicit approval, e.g.:

> _revise: the causal link to the Hess acquisition is correct — keep the sentence but
> re-cite it to p.47, which states it directly._

Only on the Reviewer's explicit nod does this become an answer record. Never commit an
answer that was not signed off.

### 4. Commit the batch

Accumulate the signed-off records into an answers file and commit them:

```
tlddr answer-commit --answers <answers.json> --output "$TLDDR_OUTPUT"
```

(Or, if the Reviewer filled `> answer:` slots in `_triage.md` directly with leading
`[revise]`/`[accept]` tags, commit those instead:
`tlddr answer-commit --triage "$TLDDR_OUTPUT/vault/_triage.md" --output "$TLDDR_OUTPUT"`.)

Read the printed RE-PASS WORKLIST.

### 5. Walk the worklist

For each **section** entry (re-draft): re-run the `draft` skill for that section with
the entry's `guidance` in context (as instruction, never as a citation), then re-run
`draft-verify` for it. Already-resolved questions will be suppressed on re-ingest; only
genuinely new problems surface.

For each **node** entry (re-understand): re-run the `understand` skill for that node
with the guidance in context, then `understand-commit`. If the node's section tags
change, the affected sections are candidates for a follow-up re-draft — surface them to
the Reviewer; do not re-draft them automatically.

### 6. Re-assemble and check convergence

```
tlddr assemble --output "$TLDDR_OUTPUT"
```

The loop has converged for a section when its re-verify raises zero new questions. If
`assemble` warns that a target has cycled 3+ times, stop and raise it with the
Reviewer rather than looping again.
```

- [ ] **Step 2: Add the re-pass note to the draft and understand skills**

Append this section to `skills/draft/SKILL.md`:

```markdown
## Re-pass mode (answer loop)

When re-drafting a section named in a `worklist.json` entry, read that entry's
`guidance` field and treat it as Reviewer instruction for this section — it records a
signed-off answer to an earlier question. Use it to steer the re-draft (what to keep,
fix, or drop). It is guidance only: every claim must still cite a real `(node_id, page)`;
the guidance text is never itself a citation. Then re-run `draft-verify` for the section.
```

Append this section to `skills/understand/SKILL.md`:

```markdown
## Re-pass mode (answer loop)

When re-understanding a node named in a `worklist.json` entry, read that entry's
`guidance` field and treat it as Reviewer instruction — a signed-off answer to an
earlier question about this document. Re-comprehend with it in context, then
`understand-commit`. If your re-tagging changes the node's `report_sections`, note the
affected sections so the Reviewer can decide whether to re-draft them; do not assume it.
```

- [ ] **Step 3: Update the module indexes and handoff docs**

Update `tlddr/CLAUDE.md` (cli.py section): add `answer-commit` to the subcommand list and note the new `answer_commit` / `_format_worklist` / `_bump_repass_log` functions; note `tlddr/answer.py` as a new top-level module (answer-loop core). Update the models.py entry: `Question` now carries `disposition` + `resolved`; add `Disposition` enum.

Update `tlddr/understand/CLAUDE.md` (render.py entry): `render_triage` now splits Open vs Resolved.

Update `tlddr/draft/CLAUDE.md` (verify.py + assemble.py entries): `ingest_verdicts` gains `suppress`; `render_sidecar` renders accepted findings as disclosed caveats.

Update `docs/HANDOFF.md`: move the answer loop from "the one open seam / direction 0" to DONE — a new "Stage: Answer loop (D6)" entry summarizing `answer-commit`, routing by `raised_by`, the deduped worklist, verify dedup, Open/Resolved triage, disclosed caveats, and the `skills/review` session. Update the pipeline diagram note (the loop is now closed) and the "Recommended immediate first action".

Update `docs/chevron-run-status.md`: the "Human-review tooling status" section — the answer loop is now BUILT; describe running `skills/review` over the 19 open verify questions and `answer-commit`.

- [ ] **Step 4: Run the full test suite**

Run: `.venv/bin/pytest`
Expected: PASS — all 140 existing tests plus the new answer-loop tests green.

- [ ] **Step 5: Commit**

```bash
git add skills/ tlddr/CLAUDE.md tlddr/understand/CLAUDE.md tlddr/draft/CLAUDE.md docs/HANDOFF.md docs/chevron-run-status.md
git commit -m "feat(skills): add review session and document the answer loop"
```

---

## Self-Review

**1. Spec coverage** (each spec section → task):
- AD1 (one validated `answer-commit`, both routes converge): Tasks 3 (`ingest_answers`), 4 (`parse_triage_answers`), 8 (CLI `--answers`/`--triage`). Covered.
- AD2 (routing by `raised_by`, cascade surfaced not automatic): Task 3 (`build_worklist` routes understand→node, draft/verify→section); Task 10 (understand re-pass note surfaces tag-change sections, does not auto-draft). Covered.
- AD3 (batched deduped worklist, answer-as-guidance, always re-verify): Task 3 (dedup by target + guidance join), Task 8 (worklist.json + print), Task 10 (skill re-verifies after re-draft). Covered.
- AD4 (answering clears `blocking`, triage recomputes; `blocks` reserved): Task 3 (`q.blocking = False`); Task 6 re-derives display triage from each node's unresolved questions at render, so de-escalation is visible on the next `_triage.md` (via `answer-commit`'s re-render in Task 8) without mutating stored `node.triage` — honors both the `revise` and `accept` cases; `blocks` untouched. Covered.
- AD5 (persist resolved; B1 dedup; convergence; accepted caveats; B3 warn): Task 1 (`resolved`), Task 5 + 8 (suppress-by-identity, preserve resolved verify), Task 6 (Open/Resolved), Task 7 (caveats), Task 9 (B3). Covered.
- Data contracts (`Disposition`, `Question` fields, answer-record, worklist): Tasks 1, 3, 8. Covered.
- CLI surface (`answer-commit`, changed `draft-verify-commit`/`assemble`/`render_triage`): Tasks 8, 9, 6, 5. Covered.
- Review-session skill + re-pass notes: Task 10. Covered.
- Proving approach (Chevron 19): exercised by the skill in Task 10; not a unit test (real model run), documented in chevron-run-status.

**2. Placeholder scan:** No TBD/TODO; every code step shows complete code; every test shows real assertions. Clean.

**3. Type consistency:** `ingest_answers(records, questions) -> (list[Question], dict, list[str])` and `build_worklist(questions) -> dict` used consistently in Tasks 3 and 8. `question_identity(q) -> tuple[str,str,str]` defined in Task 2, consumed in Tasks 5 and 8. `ingest_verdicts(verdicts, claims, suppress=None)` signature consistent Tasks 5, 8. Worklist keys (`sections`/`nodes`, `section_id`/`node_id`, `guidance`, `from`) consistent across Tasks 3, 8, 9. `Disposition.REVISE`/`ACCEPT` consistent throughout. No drift found.
