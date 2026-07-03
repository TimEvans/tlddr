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
