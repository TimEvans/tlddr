from tlddr.draft.amend import apply_amendments
from tlddr.models import (ExtractedDoc, Node, PageProvenance, SignalType, ExtractMethod,
                          Confidence, Triage, DraftClaim, Citation, SupportLevel, EvidenceRelation)


def _fixtures():
    doc = ExtractedDoc(id="n", source_path="/x", source_sha256="a", signal_type=SignalType.MIXED,
                       raw_title="N", content="--- page 1 ---\na\n--- page 2 ---\nb",
                       pages=[PageProvenance(page=1, method=ExtractMethod.PYMUPDF_TEXT, has_text_layer=True),
                              PageProvenance(page=2, method=ExtractMethod.PYMUPDF_TEXT, has_text_layer=True)],
                       extractor="pdf")
    node = Node(id="n", extracted_id="n", title="N", doc_type="report", description="d",
                confidence_extraction=Confidence.HIGH, confidence_interpretation=Confidence.HIGH,
                triage=Triage.GREEN, report_sections=["s1"])
    claim = DraftClaim(id="claim-a", section_id="s1", text="original",
                       sources=[Citation(node_id="n", page=1)],
                       support_level=SupportLevel.FULLY_SUPPORTED, evidence_relation=EvidenceRelation.QUOTED)
    return {"n": doc}, {"n": node}, [claim]


def test_add_page_and_set_text_preserve_id_and_validate():
    docs, nodes, claims = _fixtures()
    updated, amended, dropped = apply_amendments(
        [{"claim_id": "claim-a", "set_text": "fixed", "add_pages": [{"node_id": "n", "page": 2}]}],
        claims, docs, nodes, {"s1"})
    c = updated[0]
    assert dropped == [] and amended == {"claim-a"}
    assert c.id == "claim-a" and c.text == "fixed"
    assert sorted(s.page for s in c.sources) == [1, 2]


def test_unknown_claim_id_dropped():
    docs, nodes, claims = _fixtures()
    updated, amended, dropped = apply_amendments(
        [{"claim_id": "ghost", "set_text": "x"}], claims, docs, nodes, {"s1"})
    assert amended == set() and len(dropped) == 1 and updated[0].text == "original"


def test_unresolvable_added_page_drops_that_amendment():
    docs, nodes, claims = _fixtures()
    updated, amended, dropped = apply_amendments(
        [{"claim_id": "claim-a", "add_pages": [{"node_id": "n", "page": 99}]}],
        claims, docs, nodes, {"s1"})
    # page 99 does not resolve -> re-validation drops the added page; claim keeps its valid source
    assert amended == {"claim-a"} and sorted(s.page for s in updated[0].sources) == [1]


def test_set_support_and_evidence():
    docs, nodes, claims = _fixtures()
    updated, _, _ = apply_amendments(
        [{"claim_id": "claim-a", "set_support": "partially_supported", "set_evidence": "inferred"}],
        claims, docs, nodes, {"s1"})
    assert updated[0].support_level is SupportLevel.PARTIALLY_SUPPORTED
    assert updated[0].evidence_relation is EvidenceRelation.INFERRED


def test_invalid_axis_isolated_not_fatal():
    docs, nodes, claims = _fixtures()
    # Create a second valid claim for testing batch isolation
    claim_b = DraftClaim(id="claim-b", section_id="s1", text="second",
                        sources=[Citation(node_id="n", page=1)],
                        support_level=SupportLevel.FULLY_SUPPORTED, evidence_relation=EvidenceRelation.QUOTED)

    updated, amended, dropped = apply_amendments(
        [{"claim_id": "claim-a", "set_support": "not_a_real_value"},
         {"claim_id": "claim-b", "set_text": "fixed b"}],
        [claims[0], claim_b], docs, nodes, {"s1"})

    # claim-a should NOT be amended due to invalid support value
    assert "claim-a" not in amended
    assert any("claim-a" in msg and "set_support" in msg for msg in dropped)

    # claim-b should be successfully amended
    assert "claim-b" in amended
    assert updated[1].text == "fixed b"

    # claim-a should remain unchanged (original values)
    assert updated[0].text == "original"
    assert updated[0].support_level == SupportLevel.FULLY_SUPPORTED

    # Test invalid evidence_relation as well
    updated2, amended2, dropped2 = apply_amendments(
        [{"claim_id": "claim-a", "set_evidence": "not_valid_evidence"}],
        [claims[0]], docs, nodes, {"s1"})

    assert "claim-a" not in amended2
    assert any("claim-a" in msg and "set_evidence" in msg for msg in dropped2)
