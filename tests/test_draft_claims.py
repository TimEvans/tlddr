from tlddr.draft.claims import validate_claims
from tlddr.models import (
    ExtractedDoc, Node, PageProvenance, SignalType, ExtractMethod, Confidence, Triage,
    SupportLevel, EvidenceRelation,
)


def _doc(id="r518"):
    return ExtractedDoc(
        id=id, source_path=f"/x/{id}.pdf", source_sha256="a", signal_type=SignalType.MIXED,
        raw_title=id, content="--- page 12 ---\ndesign life 25 years",
        pages=[PageProvenance(page=12, method=ExtractMethod.PYMUPDF_TEXT, has_text_layer=True)],
        extractor="pdf",
    )


def _node(id="r518", interp=Confidence.HIGH):
    return Node(id=id, extracted_id=id, title=id, doc_type="report", description="d",
                confidence_extraction=Confidence.HIGH, confidence_interpretation=interp,
                triage=Triage.GREEN)


def _raw(section="s1", node="r518", page=12):
    return {
        "section_id": section, "text": "25-year design life.",
        "support_level": "fully_supported", "evidence_relation": "quoted",
        "sources": [{"node_id": node, "page": page}],
    }


def test_valid_claim_keeps_citation_and_attaches_confidence():
    claims, findings = validate_claims(
        [_raw()], docs={"r518": _doc()}, nodes={"r518": _node(interp=Confidence.MEDIUM)})
    assert findings == []
    assert len(claims) == 1
    assert claims[0].support_level is SupportLevel.FULLY_SUPPORTED
    assert claims[0].evidence_relation is EvidenceRelation.QUOTED
    assert claims[0].sources[0].source_confidence is Confidence.MEDIUM   # looked up, not self-graded


def test_bad_page_dropped_unknown_node_dropped_then_zero_citation_is_a_finding():
    raw = _raw()
    raw["sources"] = [{"node_id": "r518", "page": 99},     # page out of range
                      {"node_id": "ghost", "page": 1}]      # unknown node
    claims, findings = validate_claims(
        [raw], docs={"r518": _doc()}, nodes={"r518": _node()})
    assert claims == []                                     # no valid citation -> dropped
    assert len(findings) == 1
    assert findings[0].raised_by == "draft"
    assert findings[0].node_id is None
    assert findings[0].section_id == "s1"


def test_partially_valid_claim_keeps_only_resolvable_citations():
    raw = _raw()
    raw["sources"] = [{"node_id": "r518", "page": 12}, {"node_id": "r518", "page": 99}]
    claims, findings = validate_claims([raw], docs={"r518": _doc()}, nodes={"r518": _node()})
    assert findings == []
    assert [(c.node_id, c.page) for c in claims[0].sources] == [("r518", 12)]


def test_unknown_section_claim_dropped_with_finding():
    raw = _raw(section="ghost")
    claims, findings = validate_claims(
        [raw], docs={"r518": _doc()}, nodes={"r518": _node()},
        known_section_ids={"s1"})
    assert claims == []
    assert len(findings) == 1
    assert findings[0].raised_by == "draft"
    assert findings[0].section_id == "ghost"


def test_known_section_passes_through_unchanged():
    raw = _raw(section="s1")
    claims, findings = validate_claims(
        [raw], docs={"r518": _doc()}, nodes={"r518": _node()},
        known_section_ids={"s1"})
    assert findings == []
    assert len(claims) == 1


def test_no_known_section_ids_skips_section_validation():
    # Existing callers omit known_section_ids; ghost sections must not be dropped
    raw = _raw(section="ghost")
    claims, findings = validate_claims(
        [raw], docs={"r518": _doc()}, nodes={"r518": _node()})
    assert len(claims) == 1
    assert findings == []
