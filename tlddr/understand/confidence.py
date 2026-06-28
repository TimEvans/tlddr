from tlddr.models import ExtractedDoc, SignalType, Confidence


def extraction_confidence(doc: ExtractedDoc) -> Confidence:
    # Identity-only datasets are complete for what they are.
    if doc.signal_type == SignalType.GEOSPATIAL:
        return Confidence.HIGH

    # Spreadsheets: truncation is the fidelity risk.
    if doc.signal_type == SignalType.SPREADSHEET:
        truncated = any("truncated" in w for w in doc.warnings)
        return Confidence.MEDIUM if truncated else Confidence.HIGH

    # Documents without pagination (docx) are extracted faithfully (prose + tables);
    # embedded-image warnings do not reduce text fidelity.
    if not doc.pages:
        return Confidence.HIGH

    # Paginated docs: proportion of text-bearing pages.
    text_fraction = sum(1 for p in doc.pages if p.has_text_layer) / len(doc.pages)
    if text_fraction >= 0.9:
        return Confidence.HIGH
    if text_fraction >= 0.5:
        return Confidence.MEDIUM
    return Confidence.LOW
