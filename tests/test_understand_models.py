from tlddr.models import (
    Confidence, Triage, RelationType, Edge, Question, Node,
)


def test_enums_serialise_to_strings():
    assert Confidence.HIGH.value == "high"
    assert Triage.AMBER.value == "amber"
    assert RelationType.CONTRADICTS.value == "contradicts"


def test_node_round_trips_json_with_edges():
    node = Node(
        id="a6", extracted_id="a6", title="A6", doc_type="cba",
        description="A cost benefit analysis.",
        confidence_extraction=Confidence.HIGH,
        confidence_interpretation=Confidence.MEDIUM,
        triage=Triage.AMBER,
        open_questions=["q-0001"],
        related=[Edge(target="a3", relation=RelationType.CORROBORATES, rationale="same REZ data")],
    )
    restored = Node.model_validate_json(node.model_dump_json())
    assert restored.triage is Triage.AMBER
    assert restored.related[0].relation is RelationType.CORROBORATES
    assert restored.report_sections == []


def test_question_defaults():
    q = Question(id="q-1", raised_by="understand", question="Which pump?")
    assert q.blocking is False
    assert q.blocks == []
    assert q.answer is None
