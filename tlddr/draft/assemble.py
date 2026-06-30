from tlddr.models import (
    DraftClaim, Section, Question, Node, SupportLevel, EvidenceRelation, Confidence,
)
from tlddr.draft.eval import no_evidence_sections

_WEAK_SUPPORT = {SupportLevel.PARTIALLY_SUPPORTED, SupportLevel.UNSUPPORTED}


def _by_section(claims: list[DraftClaim], section_id: str) -> list[DraftClaim]:
    return [c for c in claims if c.section_id == section_id]


def render_published(sections: list[Section], claims: list[DraftClaim]) -> str:
    lines: list[str] = ["# Draft report", ""]
    for s in sections:
        lines.append(f"## {s.title}")
        text = " ".join(c.text for c in _by_section(claims, s.id))
        lines.append(text if text else "_(no content drafted)_")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def render_sidecar(sections: list[Section], claims: list[DraftClaim],
                   questions: list[Question], nodes: dict[str, Node]) -> str:
    no_evidence = {s.id for s in no_evidence_sections(claims, sections)}
    lines: list[str] = ["# Reviewer comments", ""]
    for s in sections:
        lines.append(f"## {s.title}")
        if s.id in no_evidence:
            lines.append("- **insufficient evidence**: no source document fed this section.")
            lines.append("")
            continue
        section_claims = _by_section(claims, s.id)

        provenance = sorted({c.node_id for cl in section_claims for c in cl.sources})
        lines.append("**Provenance:** " + ", ".join(f"[[{n}]]" for n in provenance))

        warnings: list[str] = []
        for cl in section_claims:
            if cl.support_level in _WEAK_SUPPORT:
                warnings.append(f"{cl.support_level.value}: '{cl.text[:60]}'")
            for c in cl.sources:
                if c.source_confidence is Confidence.LOW:
                    warnings.append(f"low-confidence source [[{c.node_id}]] used for "
                                    f"'{cl.text[:60]}'")
        if warnings:
            lines.append("**Warnings:**")
            lines += [f"- {w}" for w in warnings]

        inferences = [cl for cl in section_claims
                      if cl.evidence_relation is EvidenceRelation.INFERRED]
        if inferences:
            lines.append("**Inferences (not stated verbatim in the sources):**")
            for cl in inferences:
                srcs = ", ".join(f"[[{c.node_id}]] p{c.page}" for c in cl.sources)
                lines.append(f"- '{cl.text[:80]}' (from {srcs})")

        section_qs = [q for q in questions if q.section_id == s.id]
        if section_qs:
            lines.append("**Open questions:**")
            lines += [f"- ({q.raised_by}) {q.question}" for q in section_qs]
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"
