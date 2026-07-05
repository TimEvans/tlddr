from tlddr.draft.assemble import render_published, render_sidecar
from tlddr.models import (
    Section, DraftClaim, Citation, Question, SupportLevel, EvidenceRelation,
    Confidence, QuestionStatus,
)


def _sections():
    return [Section(id="s1", title="Overview"), Section(id="s2", title="Gaps")]


def _claims():
    return [
        DraftClaim(section_id="s1", text="Design life is 25 years.",
                   sources=[Citation(node_id="r518", page=12, source_confidence=Confidence.HIGH)],
                   support_level=SupportLevel.FULLY_SUPPORTED,
                   evidence_relation=EvidenceRelation.QUOTED),
        DraftClaim(section_id="s1", text="Implies mid-life inverter swap.",
                   sources=[Citation(node_id="r304", page=3, source_confidence=Confidence.LOW)],
                   support_level=SupportLevel.PARTIALLY_SUPPORTED,
                   evidence_relation=EvidenceRelation.INFERRED),
    ]


def test_published_is_clean_prose_by_section():
    out = render_published(_sections(), _claims())
    assert "## Overview" in out
    assert "Design life is 25 years. Implies mid-life inverter swap." in out
    assert "r518" not in out and "fully_supported" not in out      # no provenance leaks into draft


def test_sidecar_lists_provenance_warnings_inferences_and_no_evidence():
    questions = [Question(id="q1", raised_by="verify", section_id="s1",
                          question="judge downgrade on claim 1")]
    out = render_sidecar(_sections(), _claims(), questions)
    assert "## Overview" in out
    assert "[[r518]]" in out and "[[r304]]" in out                  # provenance
    assert "r304" in out and "inference" in out.lower()             # inference surfaced
    assert "low" in out.lower()                                     # low-confidence warning
    assert "judge downgrade on claim 1" in out                      # open question
    assert "Gaps" in out and "insufficient evidence" in out.lower() # s2 no-evidence


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
        Question(id="v-open", raised_by="verify", section_id="s1", question="Still open?",
                 status=QuestionStatus.OPEN),
        Question(id="v-acc", raised_by="verify", section_id="s1", question="Minor nit?",
                 answer="Acceptable.", status=QuestionStatus.ACCEPTED),
        Question(id="v-rev", raised_by="verify", section_id="s1", question="Was wrong?",
                 answer="Fixed it.", status=QuestionStatus.REVISE_PENDING),
    ]
    md = render_sidecar(sections, claims, questions)
    assert "Open questions" in md and "Still open?" in md
    assert "Disclosed caveats" in md and "Minor nit?" in md and "Acceptable." in md
    assert "Was wrong?" not in md          # resolved-revise hidden
