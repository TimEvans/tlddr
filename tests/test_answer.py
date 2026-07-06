import pytest

from tlddr.models import Question, Disposition, QuestionStatus
from tlddr.answer import ingest_answers, build_worklist, parse_triage_answers


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


def _q(id, raised_by, question="q?", section_id=None, node_id=None, blocking=False):
    return Question(id=id, raised_by=raised_by, question=question,
                    section_id=section_id, node_id=node_id, blocking=blocking)


def test_valid_answer_sets_status_and_worklist():
    qs = [_q("v-1", "verify", section_id="s1", blocking=True)]
    records = [{"id": "v-1", "disposition": "revise", "answer": "Keep it, cite p.47."}]
    updated, worklist, dropped = ingest_answers(records, qs)
    assert dropped == []
    assert updated[0].status is QuestionStatus.REVISE_PENDING
    assert updated[0].answer == "Keep it, cite p.47."


def test_colliding_question_ids_raise_rather_than_silently_collapse():
    """A question set with duplicate ids is corrupt: resolving an answer by bare
    id would silently drop all but one (the original bug). ingest_answers must
    fail loud instead of collapsing them."""
    qs = [_q("q-0001", "understand", node_id="node_a"),
          _q("q-0001", "understand", node_id="node_b")]
    records = [{"id": "q-0001", "disposition": "revise", "answer": "x"}]
    with pytest.raises(ValueError, match="q-0001"):
        ingest_answers(records, qs)


def test_unknown_id_is_dropped():
    qs = [_q("v-1", "verify", section_id="s1")]
    records = [{"id": "nope", "disposition": "accept", "answer": "x"}]
    updated, worklist, dropped = ingest_answers(records, qs)
    assert len(dropped) == 1 and "nope" in dropped[0]
    assert updated[0].status is QuestionStatus.OPEN


def test_invalid_disposition_is_dropped():
    qs = [_q("v-1", "verify", section_id="s1")]
    records = [{"id": "v-1", "disposition": "maybe", "answer": "x"}]
    updated, worklist, dropped = ingest_answers(records, qs)
    assert len(dropped) == 1 and "v-1" in dropped[0]
    assert updated[0].status is QuestionStatus.OPEN


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


def test_accept_sets_accepted_status_and_no_worklist():
    qs = [_q("v-1", "verify", section_id="s1")]
    updated, worklist, _ = ingest_answers(
        [{"id": "v-1", "disposition": "accept", "answer": "Fine."}], qs)
    assert updated[0].status is QuestionStatus.ACCEPTED
    assert worklist["sections"] == [] and worklist["nodes"] == []


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


def test_parse_triage_handles_heading_suffixes():
    triage_with_suffixes = """# Triage

## Open questions
### v-1 [blocking] ([[r972]])
Off by one page.
> answer: [revise] Cite p.47.

### u-2 ([[r518]])
Node target only.
> answer: [accept] Fine.
"""
    records, skipped = parse_triage_answers(triage_with_suffixes)
    by_id = {r["id"]: r for r in records}
    assert by_id["v-1"] == {"id": "v-1", "disposition": "revise",
                            "answer": "Cite p.47."}
    assert by_id["u-2"] == {"id": "u-2", "disposition": "accept",
                            "answer": "Fine."}
    assert skipped == []


def test_parse_triage_ignores_resolved_section():
    """Resolved section questions must not appear in records or skipped."""
    triage_with_resolved = """# Triage

## Open questions
### v-open
An open question.
> answer:

### v-fill
A question to revise.
> answer: [revise] do it.

## Resolved questions
### v-done (accept)
A resolved question.
> answer: already decided earlier.
"""
    records, skipped = parse_triage_answers(triage_with_resolved)
    by_id = {r["id"]: r for r in records}

    # v-fill should be in records with revise disposition
    assert by_id["v-fill"] == {"id": "v-fill", "disposition": "revise", "answer": "do it."}

    # v-open should NOT be in records (empty slot)
    assert "v-open" not in by_id

    # v-done must NOT be in records or skipped (resolved section is ignored)
    assert "v-done" not in by_id
    assert "v-done" not in skipped
    assert skipped == []
