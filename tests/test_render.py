from tlddr.understand.render import render_index, render_triage
from tlddr.models import Node, Question, Confidence, Triage


def _node(id, triage):
    return Node(
        id=id, extracted_id=id, title=id.upper(), doc_type="report",
        description="d", confidence_extraction=Confidence.HIGH,
        confidence_interpretation=Confidence.HIGH if triage is Triage.GREEN else Confidence.MEDIUM,
        triage=triage,
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
