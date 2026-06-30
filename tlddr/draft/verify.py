from tlddr.models import DraftClaim, SupportLevel, Question

_RANK = {SupportLevel.UNSUPPORTED: 0, SupportLevel.PARTIALLY_SUPPORTED: 1,
         SupportLevel.FULLY_SUPPORTED: 2}


def ingest_verdicts(verdicts: list[dict], claims: list[DraftClaim]) -> list[Question]:
    questions: list[Question] = []
    for v in verdicts:
        claim = claims[v["index"]]
        judged = SupportLevel(v["support_level"])
        downgrade = _RANK[judged] < _RANK[claim.support_level]
        if not (downgrade or v.get("contradiction")):
            continue
        reason = "contradiction" if v.get("contradiction") else \
            f"judge:{judged.value} < drafter:{claim.support_level.value}"
        note = (v.get("note") or "").strip()
        questions.append(Question(
            id=f"verify-{v['index']}", raised_by="verify", node_id=None,
            section_id=claim.section_id,
            question=f"[{reason}] '{claim.text[:80]}' — {note}".rstrip(" -"),
        ))
    return questions
