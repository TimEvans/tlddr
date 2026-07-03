from tlddr.models import Node, Question, QuestionStatus, Triage, Section
from tlddr.understand.triage import derive_triage

_GROUP_ORDER = [Triage.RED, Triage.AMBER, Triage.GREEN]
_GROUP_TITLE = {Triage.RED: "Red", Triage.AMBER: "Amber", Triage.GREEN: "Green"}


def render_index(nodes: list[Node]) -> str:
    lines = ["# Vault index", "", "| document | doc_type | triage |", "|----|----|----|"]
    for n in sorted(nodes, key=lambda n: n.id):
        lines.append(f"| [[{n.id}]] | {n.doc_type} | {n.triage.value} |")
    return "\n".join(lines) + "\n"


def section_coverage(nodes: list[Node], sections: list[Section]) -> dict[str, list[str]]:
    coverage: dict[str, list[str]] = {s.id: [] for s in sections}
    for n in sorted(nodes, key=lambda n: n.id):
        for sid in n.report_sections:
            if sid in coverage:
                coverage[sid].append(n.id)
    return coverage


def isolated_nodes(nodes: list[Node]) -> list[str]:
    targets = {e.target for n in nodes for e in n.related}
    return sorted(n.id for n in nodes if not n.related and n.id not in targets)


def _display_triage(node: Node, questions: list[Question]) -> Triage:
    """Triage as it stands now: re-derive from the node's still-open questions so a
    resolved blocking question visibly de-escalates the node (never mutates stored state)."""
    node_qs = [q for q in questions
              if q.node_id == node.id and q.status is QuestionStatus.OPEN]
    return derive_triage(node.confidence_extraction, node.confidence_interpretation, node_qs)


def render_triage(nodes: list[Node], questions: list[Question],
                  sections: list[Section] | None = None) -> str:
    lines = ["# Triage", ""]
    by_triage = {t: [n for n in nodes if _display_triage(n, questions) is t]
                 for t in _GROUP_ORDER}
    for t in _GROUP_ORDER:
        group = sorted(by_triage[t], key=lambda n: n.id)
        lines.append(f"## {_GROUP_TITLE[t]} ({len(group)})")
        for n in group:
            lines.append(f"- [[{n.id}]] — {n.doc_type}")
        lines.append("")

    if sections is not None:
        coverage = section_coverage(nodes, sections)
        lines.append("## Section coverage")
        for s in sections:
            tagged = coverage[s.id]
            refs = ", ".join(f"[[{i}]]" for i in tagged) if tagged else "no evidence"
            lines.append(f"- {s.title} (`{s.id}`): {refs}")
        lines.append("")

    iso = isolated_nodes(nodes)
    lines.append("## Isolated documents")
    if iso:
        for i in iso:
            lines.append(f"- [[{i}]]")
    else:
        lines.append("None.")
    lines.append("")

    open_qs = [q for q in questions if q.status is QuestionStatus.OPEN]
    resolved_qs = [q for q in questions if q.status is not QuestionStatus.OPEN]

    lines.append("## Open questions")
    if not open_qs:
        lines.append("None.")
    for q in open_qs:
        target = f" ([[{q.node_id}]])" if q.node_id else ""
        flag = " [blocking]" if q.blocking else ""
        lines.append(f"### {q.id}{flag}{target}")
        lines.append(q.question)
        lines.append("> answer:")
        lines.append("")

    if resolved_qs:
        lines.append("## Resolved questions")
        for q in resolved_qs:
            target = f" ([[{q.node_id}]])" if q.node_id else ""
            lines.append(f"### {q.id} ({q.status.value}){target}")
            lines.append(q.question)
            lines.append(f"> answer: {q.answer or ''}")
            lines.append("")
    return "\n".join(lines) + "\n"
