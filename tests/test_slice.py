from tlddr.understand.slice import build_slice
from tlddr.models import ExtractedDoc, PageProvenance, SignalType, ExtractMethod


def _doc(content, **kw):
    base = dict(
        id="d", source_path="/x/d.pdf", source_sha256="abc",
        signal_type=SignalType.BORN_DIGITAL_REPORT, raw_title="Big Report",
        content=content, pages=[], warnings=[], extractor="pdf",
    )
    base.update(kw)
    return ExtractedDoc(**base)


def test_slice_includes_title_structure_and_warnings():
    content = "--- page 1 ---\n# Executive Summary\nbody text\n--- page 2 ---\n## Risks\nmore"
    doc = _doc(content, warnings=["page 3 image-only"])
    s = build_slice(doc)
    assert "Big Report" in s
    assert "born_digital_report" in s
    assert "Executive Summary" in s        # heading surfaced as structure
    assert "page 3 image-only" in s         # warning surfaced
    assert "body text" in s                 # head sample present


def test_slice_is_bounded():
    doc = _doc("x" * 50000)
    s = build_slice(doc, max_chars=2000)
    # the content sample is capped; total stays in a sane bound
    assert len(s) < 4000
