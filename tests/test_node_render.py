import yaml
from tlddr.understand.node_render import render_node_markdown
from tlddr.models import Node, Edge, RelationType, Confidence, Triage


def _node():
    return Node(
        id="a6", extracted_id="a6", title="A6 Cost-Benefit Analysis",
        doc_type="cost-benefit analysis", description="Walks through the CBA: net market benefits.",
        report_sections=[], confidence_extraction=Confidence.HIGH,
        confidence_interpretation=Confidence.MEDIUM, triage=Triage.AMBER,
        open_questions=["q-0007"],
        related=[Edge(target="a3-renewable-energy-zones", relation=RelationType.CORROBORATES,
                      rationale="shares REZ boundary data")],
    )


def test_frontmatter_is_parseable_and_carries_overlay():
    md = render_node_markdown(_node())
    assert md.startswith("---\n")
    fm = yaml.safe_load(md.split("---\n")[1])
    assert fm["extracted_id"] == "a6"
    assert fm["triage"] == "amber"
    assert fm["confidence_interpretation"] == "medium"
    assert fm["related"][0]["target"] == "a3-renewable-energy-zones"
    assert fm["related"][0]["relation"] == "corroborates"


def test_body_has_description_and_wikilink_and_question_pointer():
    md = render_node_markdown(_node())
    assert "net market benefits" in md
    assert "[[a3-renewable-energy-zones]]" in md
    assert "_triage.md" in md
    assert "q-0007" in md


def test_rationale_with_colon_survives_frontmatter():
    n = _node()
    n.related[0].rationale = "capacity figures: spec says 500MW"
    fm = yaml.safe_load(render_node_markdown(n).split("---\n")[1])
    assert fm["related"][0]["rationale"] == "capacity figures: spec says 500MW"
