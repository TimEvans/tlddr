import re

from tlddr.models import Question, Disposition, QuestionStatus


def _normalize(text: str) -> str:
    """Fold case and collapse all whitespace so trivial rephrasings compare equal."""
    return " ".join(text.lower().split())


def question_identity(q: Question) -> tuple[str, str, str]:
    """Stable identity for dedup: same stage + same target + same (normalized) text."""
    # Identity target intentionally differs from worklist routing target (node_id first).
    # raised_by is part of the tuple, so cross-stage identities remain unambiguous.
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
        q.status = (QuestionStatus.ACCEPTED if disposition is Disposition.ACCEPT
                    else QuestionStatus.REVISE_PENDING)
        if disposition is Disposition.REVISE:
            revised.append(q)
    return questions, build_worklist(revised), dropped


_HEADING = re.compile(r"^###\s+(\S+)")
_SECTION = re.compile(r"^##\s+(.+)$")
_ANSWER = re.compile(r"^>\s*answer:\s*(.*)$")
_TAG = re.compile(r"^\[(revise|accept)\]\s*(.*)$", re.IGNORECASE)


def parse_triage_answers(triage_md: str) -> tuple[list[dict], list[str]]:
    """Parse filled `> answer:` slots (with a leading [revise]/[accept] tag) into
    answer records. Untagged-but-filled slots are reported as skipped.
    Only parses questions under the ## Open questions section; stops at ## Resolved questions."""
    records: list[dict] = []
    skipped: list[str] = []
    current_id: str | None = None
    for line in triage_md.splitlines():
        section = _SECTION.match(line)
        if section:
            # Stop parsing when we reach the Resolved questions section
            if "Resolved" in section.group(1):
                break
            continue
        heading = _HEADING.match(line)
        if heading:
            current_id = heading.group(1).strip()
            continue
        answer = _ANSWER.match(line)
        if answer and current_id:
            body = answer.group(1).strip()
            if not body:
                continue                       # unfilled slot
            tag = _TAG.match(body)
            if not tag:
                skipped.append(current_id)     # filled but no tag -> machine-trust skip
                continue
            records.append({"id": current_id, "disposition": tag.group(1).lower(),
                            "answer": tag.group(2).strip()})
    return records, skipped
