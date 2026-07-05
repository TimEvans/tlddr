from tlddr.models import DraftClaim, SupportLevel, Question

_RANK = {SupportLevel.UNSUPPORTED: 0, SupportLevel.PARTIALLY_SUPPORTED: 1,
         SupportLevel.FULLY_SUPPORTED: 2}


def ingest_verdicts(verdicts: list[dict], claims: list[DraftClaim],
                    suppress_ids: set[str] | None = None) -> list[Question]:
    """Turn judge verdicts (keyed on claim_id) into verify questions. A question's id is
    verify-{claim_id}-{reason}; that id is the dedup key — a candidate whose id is already
    resolved (in suppress_ids) or already emitted in this batch is skipped."""
    suppress_ids = suppress_ids or set()
    by_id = {c.id: c for c in claims}
    questions: list[Question] = []
    emitted: set[str] = set()
    for v in verdicts:
        claim = by_id.get(v.get("claim_id"))
        if claim is None:
            continue
        try:
            judged = SupportLevel(v["support_level"])
        except (KeyError, ValueError):
            continue
        contradiction = bool(v.get("contradiction"))
        downgrade = _RANK[judged] < _RANK[claim.support_level]
        if not (downgrade or contradiction):
            continue
        reason = "contradiction" if contradiction else "downgrade"
        qid = f"verify-{claim.id}-{reason}"
        if qid in suppress_ids or qid in emitted:
            continue
        detail = "contradiction" if contradiction else \
            f"judge:{judged.value} < drafter:{claim.support_level.value}"
        note = (v.get("note") or "").strip()
        questions.append(Question(
            id=qid, raised_by="verify", claim_id=claim.id, section_id=claim.section_id,
            question=f"[{detail}] '{claim.text[:80]}' — {note}".rstrip(" -")))
        emitted.add(qid)
    return questions
