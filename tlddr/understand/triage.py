from tlddr.models import Confidence, Triage, Question

_ORDER = {Confidence.LOW: 0, Confidence.MEDIUM: 1, Confidence.HIGH: 2}


def derive_triage(extraction: Confidence, interpretation: Confidence,
                  questions: list[Question]) -> Triage:
    if any(q.blocking for q in questions):
        return Triage.RED
    worst = min(extraction, interpretation, key=lambda c: _ORDER[c])
    if worst is Confidence.LOW:
        return Triage.RED
    if worst is Confidence.MEDIUM or questions:
        return Triage.AMBER
    return Triage.GREEN
