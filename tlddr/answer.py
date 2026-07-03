from tlddr.models import Question


def _normalize(text: str) -> str:
    """Fold case and collapse all whitespace so trivial rephrasings compare equal."""
    return " ".join(text.lower().split())


def question_identity(q: Question) -> tuple[str, str, str]:
    """Stable identity for dedup: same stage + same target + same (normalized) text."""
    target = q.section_id or q.node_id or ""
    return (q.raised_by, target, _normalize(q.question))
