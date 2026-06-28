import yaml
from tlddr.models import Node


def render_node_markdown(node: Node) -> str:
    frontmatter = {
        "id": node.id,
        "extracted_id": node.extracted_id,
        "doc_type": node.doc_type,
        "report_sections": node.report_sections,
        "confidence_extraction": node.confidence_extraction.value,
        "confidence_interpretation": node.confidence_interpretation.value,
        "triage": node.triage.value,
        "open_questions": node.open_questions,
        "related": [
            {"target": e.target, "relation": e.relation.value, "rationale": e.rationale}
            for e in node.related
        ],
    }
    fm = yaml.safe_dump(frontmatter, sort_keys=False, allow_unicode=True)

    body = [f"# {node.title}", "", node.description, ""]
    if node.related:
        body.append("## Related")
        for e in node.related:
            body.append(f"- [[{e.target}]] — {e.relation.value}: {e.rationale}")
        body.append("")
    if node.open_questions:
        body.append("## Open questions")
        body.append(f"See `_triage.md` ({', '.join(node.open_questions)}).")
        body.append("")

    return f"---\n{fm}---\n\n" + "\n".join(body)
