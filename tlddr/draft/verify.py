from tlddr.models import DraftClaim, SupportLevel, Question

_RANK = {SupportLevel.UNSUPPORTED: 0, SupportLevel.PARTIALLY_SUPPORTED: 1,
         SupportLevel.FULLY_SUPPORTED: 2}


def ingest_verdicts(verdicts: list[dict], claims: list[DraftClaim]) -> list[Question]:
    questions: list[Question] = []
    for v in verdicts:
        index = v.get("index")
        if not isinstance(index, int) or index < 0 or index >= len(claims):
            continue
        try:
            judged = SupportLevel(v["support_level"])
        except (KeyError, ValueError):
            continue
        claim = claims[index]
        downgrade = _RANK[judged] < _RANK[claim.support_level]
        if not (downgrade or v.get("contradiction")):
            continue
        reason = "contradiction" if v.get("contradiction") else \
            f"judge:{judged.value} < drafter:{claim.support_level.value}"
        note = (v.get("note") or "").strip()
        questions.append(Question(
            id=f"verify-{index}", raised_by="verify", node_id=None,
            section_id=claim.section_id,
            question=f"[{reason}] '{claim.text[:80]}' — {note}".rstrip(" -"),
        ))
    return questions
