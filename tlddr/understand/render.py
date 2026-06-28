from tlddr.models import Node, Question, Triage

_GROUP_ORDER = [Triage.RED, Triage.AMBER, Triage.GREEN]
_GROUP_TITLE = {Triage.RED: "Red", Triage.AMBER: "Amber", Triage.GREEN: "Green"}


def render_index(nodes: list[Node]) -> str:
    lines = ["# Vault index", "", "| document | doc_type | triage |", "|----|----|----|"]
    for n in sorted(nodes, key=lambda n: n.id):
        lines.append(f"| [[{n.id}]] | {n.doc_type} | {n.triage.value} |")
    return "\n".join(lines) + "\n"


def render_triage(nodes: list[Node], questions: list[Question]) -> str:
    lines = ["# Triage", ""]
    by_triage = {t: [n for n in nodes if n.triage is t] for t in _GROUP_ORDER}
    for t in _GROUP_ORDER:
        group = sorted(by_triage[t], key=lambda n: n.id)
        lines.append(f"## {_GROUP_TITLE[t]} ({len(group)})")
        for n in group:
            lines.append(f"- [[{n.id}]] — {n.doc_type}")
        lines.append("")

    lines.append("## Open questions")
    if not questions:
        lines.append("None.")
    for q in questions:
        target = f" ([[{q.node_id}]])" if q.node_id else ""
        flag = " [blocking]" if q.blocking else ""
        lines.append(f"### {q.id}{flag}{target}")
        lines.append(q.question)
        lines.append("> answer:")
        lines.append("")
    return "\n".join(lines) + "\n"
