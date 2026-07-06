from tlddr.status import render_status, resume_point
from tlddr.runstate import STAGES


def _state(**overrides):
    stages = {s: {"status": "pending", "rounds": 0} for s in STAGES}
    stages.update(overrides)
    return {"config": {"preset": "quick"}, "corpus_fingerprint": "sha256:x", "stages": stages}


def test_resume_point_none_when_no_state():
    assert resume_point(None) == "none"


def test_resume_point_first_pending():
    st = _state(extract={"status": "done", "rounds": 1})
    assert resume_point(st) == "understand"


def test_resume_point_complete():
    st = {"stages": {s: {"status": "done", "rounds": 1} for s in STAGES}}
    assert resume_point(st) == "complete"


def test_render_no_run():
    out = render_status(None, [], [])
    assert "no run" in out.lower()


def test_render_shows_stage_rows_and_quarantine():
    from tlddr.models import Question, QuestionStatus
    st = _state(draft={"status": "done", "rounds": 2},
                verify={"status": "done", "rounds": 1})
    qs = [Question(id="v-a-downgrade", raised_by="verify", claim_id="a", section_id="s1",
                   question="q", status=QuestionStatus.OPEN),
          Question(id="v-b-downgrade", raised_by="verify", claim_id="b", section_id="s1",
                   question="q", status=QuestionStatus.REVISE_APPLIED)]
    rows = [{"stage": "draft", "tokens": 1000, "duration_ms": 5000}]
    out = render_status(st, rows, qs)
    assert "draft" in out and "2 round" in out          # round count shown
    assert "1000" in out or "1,000" in out or "1.0K" in out  # tokens rolled up
    assert "1 open" in out and "1 applied" in out        # quarantine by status
