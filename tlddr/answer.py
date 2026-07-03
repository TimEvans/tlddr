from tlddr.models import Question, Disposition


def _normalize(text: str) -> str:
    """Fold case and collapse all whitespace so trivial rephrasings compare equal."""
    return " ".join(text.lower().split())


def question_identity(q: Question) -> tuple[str, str, str]:
    """Stable identity for dedup: same stage + same target + same (normalized) text."""
    target = q.section_id or q.node_id or ""
    return (q.raised_by, target, _normalize(q.question))


def build_worklist(questions: list[Question]) -> dict:
    """Group revise-questions by their re-pass target (dedup), joining guidance."""
    sections: dict[str, dict] = {}
    nodes: dict[str, dict] = {}
    for q in questions:
        if q.raised_by == "understand" and q.node_id:
            bucket = nodes.setdefault(q.node_id, {"guidance": [], "from": []})
        elif q.section_id:
            bucket = sections.setdefault(q.section_id, {"guidance": [], "from": []})
        else:
            continue
        if q.answer:
            bucket["guidance"].append(q.answer)
        bucket["from"].append(q.id)
    return {
        "sections": [{"section_id": k, "guidance": " ".join(v["guidance"]), "from": v["from"]}
                     for k, v in sorted(sections.items())],
        "nodes": [{"node_id": k, "guidance": " ".join(v["guidance"]), "from": v["from"]}
                  for k, v in sorted(nodes.items())],
    }


def ingest_answers(records: list[dict],
                   questions: list[Question]) -> tuple[list[Question], dict, list[str]]:
    """Validate answer records against the known question set, resolve matches, and
    build the deduped re-pass worklist from this batch's revise targets."""
    by_id = {q.id: q for q in questions}
    dropped: list[str] = []
    revised: list[Question] = []
    for r in records:
        qid = r.get("id")
        q = by_id.get(qid)
        if q is None:
            dropped.append(f"unknown question id '{qid}'")
            continue
        try:
            disposition = Disposition(r.get("disposition"))
        except ValueError:
            dropped.append(f"'{qid}': invalid disposition '{r.get('disposition')}'")
            continue
        q.answer = r.get("answer")
        q.disposition = disposition
        q.resolved = True
        q.blocking = False
        if disposition is Disposition.REVISE:
            revised.append(q)
    return questions, build_worklist(revised), dropped
