from tlddr.models import (
    ExtractedDoc, Node, Edge, Question, RelationType, Confidence,
)
from tlddr.understand.confidence import extraction_confidence
from tlddr.understand.edges import validate_edges
from tlddr.understand.triage import derive_triage


def build_node(enrichment: dict, doc: ExtractedDoc,
               known_node_ids: set[str]) -> tuple[Node, list[Edge], list[Question]]:
    proposed = [
        Edge(target=r["target"], relation=RelationType(r["relation"]), rationale=r["rationale"])
        for r in enrichment.get("related", [])
    ]
    valid, dropped = validate_edges(proposed, known_node_ids, source_id=doc.id)

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
        confidence_extraction=ext_conf,
        confidence_interpretation=interp_conf,
        triage=triage,
        open_questions=[q.id for q in questions],
        related=valid,
    )
    return node, dropped, questions
