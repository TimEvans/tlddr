from tlddr.extract.report import render_report
from tlddr.models import ExtractedDoc, PageProvenance, SignalType, ExtractMethod


def _doc():
    return ExtractedDoc(
        id="a6-cost-benefit-analysis",
        source_path="/x/a6.pdf",
        source_sha256="deadbeefcafe",
        signal_type=SignalType.MIXED,
        raw_title="A6 Cost Benefit Analysis",
        content="Executive summary of the cost benefit analysis.",
        pages=[
            PageProvenance(page=1, method=ExtractMethod.PYMUPDF_TEXT, has_text_layer=True, char_count=40),
            PageProvenance(page=2, method=ExtractMethod.VISION, has_text_layer=False, thumbnail="/x/t.png"),
        ],
        warnings=["page 2 image-only; would route to vision (not run in reconnaissance)"],
        extractor="pdf",
    )


def test_report_has_summary_and_detail():
    md = render_report([_doc()])
    assert "a6-cost-benefit-analysis" in md
    assert "mixed" in md
    assert "Executive summary" in md
    assert "image-only" in md
    assert "deadbeef" in md  # short sha shown


def test_report_handles_empty_list():
    md = render_report([])
    assert "0 documents" in md
