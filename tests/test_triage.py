from tlddr.understand.triage import derive_triage
from tlddr.models import Confidence, Triage, Question


def q(blocking=False):
    return Question(id="q", raised_by="understand", question="?", blocking=blocking)


def test_both_high_no_questions_is_green():
    assert derive_triage(Confidence.HIGH, Confidence.HIGH, []) is Triage.GREEN


def test_any_low_is_red():
    assert derive_triage(Confidence.LOW, Confidence.HIGH, []) is Triage.RED
    assert derive_triage(Confidence.HIGH, Confidence.LOW, []) is Triage.RED


def test_blocking_question_is_red_even_if_confident():
    assert derive_triage(Confidence.HIGH, Confidence.HIGH, [q(blocking=True)]) is Triage.RED


def test_medium_is_amber():
    assert derive_triage(Confidence.HIGH, Confidence.MEDIUM, []) is Triage.AMBER


def test_open_nonblocking_question_is_amber():
    assert derive_triage(Confidence.HIGH, Confidence.HIGH, [q(blocking=False)]) is Triage.AMBER
