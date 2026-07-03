from tlddr.models import DraftClaim, SupportLevel, Question
from tlddr.answer import question_identity

_RANK = {SupportLevel.UNSUPPORTED: 0, SupportLevel.PARTIALLY_SUPPORTED: 1,
         SupportLevel.FULLY_SUPPORTED: 2}


def ingest_verdicts(verdicts: list[dict], claims: list[DraftClaim],
                    suppress: set | None = None) -> list[Question]:
    suppress = suppress or set()
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
        candidate = Question(
            id=f"verify-{index}", raised_by="verify", node_id=None,
            section_id=claim.section_id,
            question=f"[{reason}] '{claim.text[:80]}' — {note}".rstrip(" -"),
        )
        if question_identity(candidate) in suppress:
            continue
        questions.append(candidate)
    return questions
