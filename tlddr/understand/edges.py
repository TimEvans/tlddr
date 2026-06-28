from tlddr.models import Edge


def validate_edges(proposed: list[Edge], known_node_ids: set[str],
                   source_id: str) -> tuple[list[Edge], list[Edge]]:
    valid: list[Edge] = []
    dropped: list[Edge] = []
    seen: set[tuple[str, str]] = set()
    for edge in proposed:
        if edge.target == source_id or edge.target not in known_node_ids:
            dropped.append(edge)
            continue
        key = (edge.target, edge.relation)
        if key in seen:
            continue
        seen.add(key)
        valid.append(edge)
    return valid, dropped
