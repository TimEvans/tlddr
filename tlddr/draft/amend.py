from tlddr.models import DraftClaim, ExtractedDoc, Node, SupportLevel, EvidenceRelation
from tlddr.draft.claims import validate_claims


def apply_amendments(records: list[dict], claims: list[DraftClaim],
                     docs: dict[str, ExtractedDoc], nodes: dict[str, Node],
                     known_section_ids: set[str] | None = None,
                     ) -> tuple[list[DraftClaim], set[str], list[str]]:
    """Apply claim-level edits in place and re-validate each amended claim through the same
    grounding checks as draft-commit. Returns (updated_claims, amended_ids, drop_messages).
    Drop-and-report: an unknown claim_id is reported; an amendment that fails validation is
    reported and the claim is left as-is."""
    by_id = {c.id: c for c in claims}
    dropped: list[str] = []
    raw_amended: list[dict] = []

    # Pre-validate axis values to isolate invalid amendments
    support_values = {m.value for m in SupportLevel}
    evidence_values = {m.value for m in EvidenceRelation}

    for r in records:
        cid = r.get("claim_id")
        claim = by_id.get(cid)
        if claim is None:
            dropped.append(f"unknown claim_id '{cid}'")
            continue

        # Pre-validate axis values before building raw dict
        if "set_support" in r:
            if r["set_support"] not in support_values:
                dropped.append(f"'{cid}': invalid set_support '{r['set_support']}'")
                continue
        if "set_evidence" in r:
            if r["set_evidence"] not in evidence_values:
                dropped.append(f"'{cid}': invalid set_evidence '{r['set_evidence']}'")
                continue

        raw = claim.model_dump(mode="json")
        if "set_text" in r:
            raw["text"] = r["set_text"]
        if "set_support" in r:
            raw["support_level"] = r["set_support"]
        if "set_evidence" in r:
            raw["evidence_relation"] = r["set_evidence"]
        for p in r.get("add_pages", []):
            raw["sources"].append({"node_id": p["node_id"], "page": p["page"]})
        raw_amended.append(raw)

    valid, findings = validate_claims(raw_amended, docs, nodes, known_section_ids)
    revalidated = {c.id: c for c in valid}
    for f in findings:
        dropped.append(f.question)
    updated = [revalidated.get(c.id, c) for c in claims]
    amended = set(revalidated)
    return updated, amended, dropped
