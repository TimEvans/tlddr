from tlddr.models import Question, Disposition
from tlddr.answer import question_identity


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
