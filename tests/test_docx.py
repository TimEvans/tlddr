from tlddr.extract.base import ExtractContext
from tlddr.extract.docx import extract
from tlddr.models import SignalType


def test_docx_extracts_markdown(tmp_path, simple_docx):
    ctx = ExtractContext(asset_dir=tmp_path / "assets")
    doc = extract(simple_docx, ctx)
    assert doc.signal_type is SignalType.BORN_DIGITAL_REPORT
    assert doc.extractor == "docx"
    assert "Business Case" in doc.content
    assert "value" in doc.content
    assert doc.pages == []
