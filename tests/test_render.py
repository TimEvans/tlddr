from tlddr.understand.render import (
    render_index, render_triage, section_coverage, isolated_nodes,
)
from tlddr.models import Node, Question, Confidence, Triage, Section, Edge, RelationType


def _node(id, triage):
    return Node(
        id=id, extracted_id=id, title=id.upper(), doc_type="report",
        description="d", confidence_extraction=Confidence.HIGH,
        confidence_interpretation=Confidence.HIGH if triage is Triage.GREEN else Confidence.MEDIUM,
        triage=triage,
    )


def _node_tagged(id, triage, sections=(), related=()):
    return Node(
        id=id, extracted_id=id, title=id.upper(), doc_type="report",
        description="d", report_sections=list(sections),
        confidence_extraction=Confidence.HIGH,
        confidence_interpretation=Confidence.HIGH if triage is Triage.GREEN else Confidence.MEDIUM,
        triage=triage, related=list(related),
    )


def test_index_lists_all_nodes_with_triage():
    md = render_index([_node("b", Triage.GREEN), _node("a", Triage.AMBER)])
    assert "[[a]]" in md and "[[b]]" in md
    assert "amber" in md and "green" in md
    # sorted by id: a before b
    assert md.index("[[a]]") < md.index("[[b]]")


def test_triage_groups_by_colour_and_lists_questions():
    nodes = [_node("a", Triage.RED), _node("b", Triage.GREEN)]
    questions = [Question(id="q-1", raised_by="understand", node_id="a",
                          question="Which pump is this curve for?")]
    md = render_triage(nodes, questions)
    assert "## Red" in md and "## Green" in md
    assert "## Amber" in md   # empty groups are still emitted
    assert "[[a]]" in md
    assert "Which pump" in md
    assert "> answer:" in md


def test_triage_marks_blocking_question_and_handles_no_questions():
    nodes = [_node("a", Triage.RED)]
    blocking_q = Question(id="q-b", raised_by="understand", node_id="a",
                          question="Is this blocked?", blocking=True)
    md = render_triage(nodes, [blocking_q])
    # the blocking flag is shown
    assert "[blocking]" in md
    # the question heading (after the Open questions section) carries the node wikilink
    questions_section = md.split("## Open questions")[1]
    assert "[[a]]" in questions_section
    # the no-questions case renders the fallback
    assert "None." in render_triage(nodes, [])


def test_section_coverage_maps_sections_to_nodes():
    sections = [Section(id="fin", title="Financial Model"),
                Section(id="oem", title="Operation and Maintenance")]
    nodes = [_node_tagged("a", Triage.GREEN, sections=["fin"]),
             _node_tagged("b", Triage.GREEN, sections=["fin"])]
    cov = section_coverage(nodes, sections)
    assert cov == {"fin": ["a", "b"], "oem": []}


def test_isolated_nodes_finds_unconnected():
    edge = Edge(target="b", relation=RelationType.CORROBORATES, rationale="x")
    nodes = [_node_tagged("a", Triage.GREEN, related=[edge]),   # -> b
             _node_tagged("b", Triage.GREEN),                    # target of a
             _node_tagged("c", Triage.GREEN)]                    # isolated
    assert isolated_nodes(nodes) == ["c"]


def test_triage_renders_section_coverage_and_no_evidence():
    sections = [Section(id="fin", title="Financial Model"),
                Section(id="oem", title="Operation and Maintenance")]
    nodes = [_node_tagged("a", Triage.GREEN, sections=["fin"])]
    md = render_triage(nodes, [], sections)
    assert "## Section coverage" in md
    assert "Financial Model" in md and "[[a]]" in md
    assert "Operation and Maintenance" in md and "no evidence" in md.lower()
    # Open questions stays the final section
    assert md.index("## Section coverage") < md.index("## Open questions")
