from tlddr.models import ExtractedDoc
from tlddr.draft.pages import _page_index

WHOLE_DOC_MAX_CHARS = 20000   # whole/targeted cutover; tunable in proving
_OVERVIEW_SNIPPET = 120


def build_read(doc: ExtractedDoc, pages: list[int] | None = None,
               max_chars: int = WHOLE_DOC_MAX_CHARS) -> str:
    index = _page_index(doc)
    if pages:
        parts = [f"--- page {p} ---\n{index[p]}" for p in pages if p in index]
        return "\n\n".join(parts)
    if len(doc.content) <= max_chars:
        return doc.content
    lines = [
        f"# {doc.raw_title} (large: {len(doc.content)} chars, {len(index)} pages)",
        "Request specific pages via --pages. Available pages:",
    ]
    for p, text in sorted(index.items()):
        snippet = " ".join(text[:_OVERVIEW_SNIPPET].split())
        lines.append(f"- page {p} ({len(text)} chars): {snippet}")
    return "\n".join(lines)
