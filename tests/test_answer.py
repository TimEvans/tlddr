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
