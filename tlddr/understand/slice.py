import re
from tlddr.models import ExtractedDoc

_MARKER = re.compile(r"^(--- (?:page \d+|sheet: .+) ---|#{1,6} .+)$", re.MULTILINE)
_MAX_STRUCTURE_LINES = 60
_MAX_WARNINGS = 20


def build_slice(doc: ExtractedDoc, max_chars: int = 8000) -> str:
    lines = [
        f"# {doc.raw_title}",
        f"signal_type: {doc.signal_type.value}",
        f"extractor: {doc.extractor}",
    ]

    structure = _MARKER.findall(doc.content)
    if structure:
        lines.append("\n## structure")
        lines.extend(structure[:_MAX_STRUCTURE_LINES])

    if doc.warnings:
        lines.append("\n## warnings")
        lines.extend(f"- {w}" for w in doc.warnings[:_MAX_WARNINGS])

    lines.append("\n## content sample")
    lines.append(doc.content[:max_chars])

    return "\n".join(lines)
