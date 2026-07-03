import hashlib

from tlddr.models import (
    ExtractedDoc, Node, DraftClaim, Citation, SupportLevel, EvidenceRelation, Question,
)
from tlddr.draft.pages import citable_pages


def _claim_id(section_id: str, text: str) -> str:
    """Durable surrogate id, minted once from initial content; stored and frozen thereafter."""
    digest = hashlib.sha1(f"{section_id}\0{text}".encode()).hexdigest()[:8]
    return f"claim-{digest}"


def validate_claims(raw_claims: list[dict],
                    docs: dict[str, ExtractedDoc],
                    nodes: dict[str, Node],
                    known_section_ids: set[str] | None = None,
                    ) -> tuple[list[DraftClaim], list[Question]]:
    valid: list[DraftClaim] = []
    findings: list[Question] = []
    for i, raw in enumerate(raw_claims):
        section_id = raw["section_id"]
        if known_section_ids is not None and section_id not in known_section_ids:
            findings.append(Question(
                id=f"draft-{section_id}-{i}", raised_by="draft", node_id=None,
                section_id=section_id,
                question=f"Claim '{raw['text'][:80]}' tagged to unknown section '{section_id}' and was dropped.",
            ))
            continue
        citations: list[Citation] = []
        for src in raw.get("sources", []):
            node_id, page = src["node_id"], src["page"]
            doc = docs.get(node_id)
            if doc is None or page not in citable_pages(doc):
                continue                                    # drop unresolvable citation
            node = nodes.get(node_id)
            conf = node.confidence_interpretation if node is not None else None
            citations.append(Citation(node_id=node_id, page=page, source_confidence=conf))
        if not citations:
            findings.append(Question(
                id=f"draft-{section_id}-{i}", raised_by="draft", node_id=None,
                section_id=section_id,
                question=f"Claim '{raw['text'][:80]}' had no resolvable source and was dropped.",
            ))
            continue
        valid.append(DraftClaim(
            id=raw.get("id") or _claim_id(section_id, raw["text"]),
            section_id=section_id, text=raw["text"], sources=citations,
            support_level=SupportLevel(raw["support_level"]),
            evidence_relation=EvidenceRelation(raw["evidence_relation"]),
        ))
    return valid, findings
