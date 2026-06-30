import re
from tlddr.models import ExtractedDoc

_MARKER = re.compile(r"^--- (?:page (\d+)|sheet: .+) ---$", re.MULTILINE)


def _page_index(doc: ExtractedDoc) -> dict[int, str]:
    """Map each citable page number to its text. Page-less docs -> {1: whole content}."""
    if not doc.pages:
        return {1: doc.content} if doc.content.strip() else {}
    markers = list(_MARKER.finditer(doc.content))
    index: dict[int, str] = {}
    for i, m in enumerate(markers):
        start = m.end()
        end = markers[i + 1].start() if i + 1 < len(markers) else len(doc.content)
        text = doc.content[start:end].strip("\n").strip()
        page = int(m.group(1)) if m.group(1) else i + 1   # explicit page N, else sheet ordinal
        index[page] = text
    return index


def citable_pages(doc: ExtractedDoc) -> set[int]:
    return set(_page_index(doc).keys())


def page_text(doc: ExtractedDoc, page: int) -> str | None:
    return _page_index(doc).get(page)
