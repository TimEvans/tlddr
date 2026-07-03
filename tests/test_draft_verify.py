from tlddr.draft.verify import ingest_verdicts
from tlddr.models import DraftClaim, Citation, SupportLevel, EvidenceRelation, Confidence
from tlddr.answer import question_identity


def _claim(section="s1", support=SupportLevel.FULLY_SUPPORTED):
    return DraftClaim(
        section_id=section, text="claimed strongly",
        sources=[Citation(node_id="n", page=1, source_confidence=Confidence.HIGH)],
        support_level=support, evidence_relation=EvidenceRelation.QUOTED,
    )


def test_judge_downgrade_raises_verify_question():
    claims = [_claim(support=SupportLevel.FULLY_SUPPORTED)]
    verdicts = [{"index": 0, "support_level": "unsupported", "contradiction": False,
                 "note": "page does not state this"}]
    qs = ingest_verdicts(verdicts, claims)
    assert len(qs) == 1
    assert qs[0].raised_by == "verify"
    assert qs[0].section_id == "s1"
    assert "page does not state this" in qs[0].question


def test_agreement_raises_nothing():
    claims = [_claim(support=SupportLevel.FULLY_SUPPORTED)]
    verdicts = [{"index": 0, "support_level": "fully_supported", "contradiction": False, "note": ""}]
    assert ingest_verdicts(verdicts, claims) == []


def test_contradiction_flag_always_raises():
    claims = [_claim(support=SupportLevel.PARTIALLY_SUPPORTED)]
    verdicts = [{"index": 0, "support_level": "partially_supported", "contradiction": True,
                 "note": "conflicts with r304"}]
    qs = ingest_verdicts(verdicts, claims)
    assert len(qs) == 1 and qs[0].raised_by == "verify"


def test_out_of_range_index_is_skipped():
    claims = [_claim()]
    verdicts = [{"index": 99, "support_level": "unsupported", "contradiction": False, "note": ""}]
    assert ingest_verdicts(verdicts, claims) == []


def test_missing_index_is_skipped():
    claims = [_claim()]
    verdicts = [{"support_level": "unsupported", "contradiction": False, "note": ""}]
    assert ingest_verdicts(verdicts, claims) == []


def test_invalid_support_level_is_skipped():
    claims = [_claim()]
    verdicts = [{"index": 0, "support_level": "bogus_value", "contradiction": False, "note": ""}]
    assert ingest_verdicts(verdicts, claims) == []


def test_missing_support_level_is_skipped():
    claims = [_claim()]
    verdicts = [{"index": 0, "contradiction": False, "note": ""}]
    assert ingest_verdicts(verdicts, claims) == []


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
