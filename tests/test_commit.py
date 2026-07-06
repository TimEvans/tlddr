from tlddr.understand.commit import build_node
from tlddr.models import ExtractedDoc, SignalType, Triage, Confidence


def _doc(id="a6"):
    return ExtractedDoc(
        id=id, source_path=f"/x/{id}.pdf", source_sha256="a",
        signal_type=SignalType.BORN_DIGITAL_REPORT, raw_title="A6 Report",
        content="body", pages=[], warnings=[], extractor="docx",
    )


def _enrichment():
    return {
        "doc_type": "cost-benefit analysis",
        "description": "A CBA appendix.",
        "confidence_interpretation": "medium",
        "report_sections": ["financial-model", "ghost-section", "financial-model"],
        "related": [
            {"target": "a3", "relation": "corroborates", "rationale": "shared data"},
            {"target": "ghost", "relation": "references", "rationale": "does not exist"},
        ],
        "questions": [{"id": "q-1", "question": "Which scenario?", "blocking": False}],
    }


def test_build_node_validates_edges_sections_and_derives_triage():
    node, dropped_edges, dropped_sections, questions = build_node(
        _enrichment(), _doc(),
        known_node_ids={"a6", "a3"},
        known_section_ids={"financial-model", "energy-yield"},
    )
    assert node.extracted_id == "a6"
    assert node.title == "A6 Report"
    assert node.confidence_extraction is Confidence.HIGH      # clean docx
    assert node.confidence_interpretation is Confidence.MEDIUM
    assert [e.target for e in node.related] == ["a3"]          # ghost dropped
    assert [d.target for d in dropped_edges] == ["ghost"]
    assert node.report_sections == ["financial-model"]        # known, deduped
    assert dropped_sections == ["ghost-section"]              # unknown dropped
    assert node.triage is Triage.AMBER                          # medium + a question
    assert node.open_questions == ["a6:q-1"]
    assert questions[0].node_id == "a6"
    assert questions[0].raised_by == "understand"


def test_build_node_mints_node_scoped_question_ids():
    """Two nodes that each supply the same agent-side question id must yield
    distinct, node-scoped Question ids — otherwise answer-commit collapses them
    (see docs/bug-question-id-collision-2026-07-06.md)."""
    enr = {
        "doc_type": "x", "description": "d", "confidence_interpretation": "medium",
        "report_sections": [], "related": [],
        "questions": [{"id": "q-0001", "question": "Which one?", "blocking": False}],
    }
    _, _, _, qs_a = build_node(enr, _doc("aaa"), known_node_ids={"aaa"})
    node_b, _, _, qs_b = build_node(enr, _doc("bbb"), known_node_ids={"bbb"})

    assert qs_a[0].id != qs_b[0].id                       # no collision across nodes
    assert qs_a[0].node_id == "aaa" and qs_b[0].node_id == "bbb"
    assert "aaa" in qs_a[0].id and "bbb" in qs_b[0].id    # id is self-disambiguating
    assert node_b.open_questions == [qs_b[0].id]          # node carries the scoped id
