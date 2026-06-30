from tlddr.models import (
    Section, SupportLevel, EvidenceRelation, Citation, DraftClaim, Confidence,
)


def test_section_guidance_defaults_none():
    assert Section(id="s1", title="Intro").guidance is None
    assert Section(id="s1", title="Intro", guidance="cover X").guidance == "cover X"


def test_draftclaim_round_trips_with_two_axes():
    claim = DraftClaim(
        section_id="s1",
        text="The plant has a 25-year design life.",
        sources=[Citation(node_id="r518", page=12, source_confidence=Confidence.HIGH)],
        support_level=SupportLevel.FULLY_SUPPORTED,
        evidence_relation=EvidenceRelation.QUOTED,
    )
    restored = DraftClaim.model_validate_json(claim.model_dump_json())
    assert restored.support_level is SupportLevel.FULLY_SUPPORTED
    assert restored.evidence_relation is EvidenceRelation.QUOTED
    assert restored.sources[0].page == 12
    assert restored.sources[0].source_confidence is Confidence.HIGH


def test_citation_source_confidence_optional():
    assert Citation(node_id="a", page=1).source_confidence is None
