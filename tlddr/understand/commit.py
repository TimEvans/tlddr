from tlddr.models import (
    ExtractedDoc, Node, Edge, Question, RelationType, Confidence,
)
from tlddr.understand.confidence import extraction_confidence
from tlddr.understand.edges import validate_edges
from tlddr.understand.sections import validate_section_tags
from tlddr.understand.triage import derive_triage


def build_node(enrichment: dict, doc: ExtractedDoc,
               known_node_ids: set[str],
               known_section_ids: frozenset[str] | set[str] = frozenset(),
               ) -> tuple[Node, list[Edge], list[str], list[Question]]:
    proposed = [
        Edge(target=r["target"], relation=RelationType(r["relation"]), rationale=r["rationale"])
        for r in enrichment.get("related", [])
    ]
    valid_edges, dropped_edges = validate_edges(proposed, known_node_ids, source_id=doc.id)

    valid_sections, dropped_sections = validate_section_tags(
        enrichment.get("report_sections", []), set(known_section_ids))

    questions = [
        Question(
            id=q["id"], raised_by="understand", node_id=doc.id,
            section_id=q.get("section_id"), question=q["question"],
            blocking=q.get("blocking", False),
        )
        for q in enrichment.get("questions", [])
    ]

    ext_conf = extraction_confidence(doc)
    interp_conf = Confidence(enrichment["confidence_interpretation"])
    triage = derive_triage(ext_conf, interp_conf, questions)

    node = Node(
        id=doc.id,
        extracted_id=doc.id,
        title=doc.raw_title,
        doc_type=enrichment["doc_type"],
        description=enrichment["description"],
        report_sections=valid_sections,
        confidence_extraction=ext_conf,
        confidence_interpretation=interp_conf,
        triage=triage,
        open_questions=[q.id for q in questions],
        related=valid_edges,
    )
    return node, dropped_edges, dropped_sections, questions
