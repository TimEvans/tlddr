from tlddr.draft.read import build_read, WHOLE_DOC_MAX_CHARS
from tlddr.models import ExtractedDoc, PageProvenance, SignalType, ExtractMethod


def _pages_doc(n_pages, chars_each):
    content = "\n\n".join(f"--- page {i} ---\n" + ("x" * chars_each) for i in range(1, n_pages + 1))
    return ExtractedDoc(
        id="d", source_path="/x/d.pdf", source_sha256="a", signal_type=SignalType.MIXED,
        raw_title="D", content=content,
        pages=[PageProvenance(page=i, method=ExtractMethod.PYMUPDF_TEXT, has_text_layer=True)
               for i in range(1, n_pages + 1)],
        extractor="pdf",
    )


def test_short_doc_served_whole():
    doc = _pages_doc(2, 10)
    out = build_read(doc)
    assert "--- page 1 ---" in out and "--- page 2 ---" in out


def test_requested_pages_served_targeted():
    doc = _pages_doc(5, 10)
    out = build_read(doc, pages=[2, 4])
    assert "--- page 2 ---" in out and "--- page 4 ---" in out
    assert "--- page 1 ---" not in out and "--- page 3 ---" not in out


def test_large_doc_without_pages_returns_overview():
    doc = _pages_doc(40, 1000)                       # ~40k chars > threshold
    assert len(doc.content) > WHOLE_DOC_MAX_CHARS
    out = build_read(doc)
    assert "Request specific pages" in out
    assert "page 1" in out and "page 40" in out       # page list present
    assert "xxxxxxxxxx" not in out or len(out) < len(doc.content)   # not the whole body
