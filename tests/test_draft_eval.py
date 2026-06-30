from tlddr.draft.eval import groundedness_readout, no_evidence_sections
from tlddr.models import (
    Section, DraftClaim, Citation, SupportLevel, EvidenceRelation, Confidence,
)


def _claim(section, support, relation):
    return DraftClaim(
        section_id=section, text="t",
        sources=[Citation(node_id="n", page=1, source_confidence=Confidence.HIGH)],
        support_level=support, evidence_relation=relation,
    )


def _sections():
    return [Section(id="s1", title="Intro"), Section(id="s2", title="Empty Section")]


def test_no_evidence_sections_flags_uncovered():
    claims = [_claim("s1", SupportLevel.FULLY_SUPPORTED, EvidenceRelation.QUOTED)]
    assert [s.id for s in no_evidence_sections(claims, _sections())] == ["s2"]


def test_readout_counts_support_and_inference():
    claims = [
        _claim("s1", SupportLevel.FULLY_SUPPORTED, EvidenceRelation.QUOTED),
        _claim("s1", SupportLevel.PARTIALLY_SUPPORTED, EvidenceRelation.INFERRED),
    ]
    out = groundedness_readout(claims, _sections())
    assert "2 claims" in out
    assert "fully_supported: 1" in out
    assert "partially_supported: 1" in out
    assert "inferred: 1" in out
    assert "Empty Section" in out                # the no-evidence section is named
