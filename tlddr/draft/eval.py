from tlddr.models import DraftClaim, Section, SupportLevel, EvidenceRelation

_SUPPORT_ORDER = [SupportLevel.FULLY_SUPPORTED, SupportLevel.PARTIALLY_SUPPORTED,
                  SupportLevel.UNSUPPORTED]


def no_evidence_sections(claims: list[DraftClaim], sections: list[Section]) -> list[Section]:
    covered = {c.section_id for c in claims}
    return [s for s in sections if s.id not in covered]


def groundedness_readout(claims: list[DraftClaim], sections: list[Section]) -> str:
    total = len(claims)
    lines = ["# Draft groundedness readout", "", f"{total} claims across "
             f"{len({c.section_id for c in claims})} sections.", "", "## Support level"]
    for level in _SUPPORT_ORDER:
        lines.append(f"- {level.value}: {sum(1 for c in claims if c.support_level is level)}")
    inferred = sum(1 for c in claims if c.evidence_relation is EvidenceRelation.INFERRED)
    lines += ["", "## Evidence relation",
              f"- inferred: {inferred}",
              f"- quoted: {total - inferred}", "", "## Sections with no evidence"]
    empty = no_evidence_sections(claims, sections)
    lines += [f"- {s.title} (`{s.id}`)" for s in empty] if empty else ["- none"]
    return "\n".join(lines) + "\n"
