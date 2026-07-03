from tlddr.models import Question, Disposition
from tlddr.answer import question_identity, ingest_answers, build_worklist, parse_triage_answers


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
