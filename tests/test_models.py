from tlddr.models import SignalType, ExtractMethod, PageProvenance, ExtractedDoc


def test_signal_type_serialises_to_string():
    assert SignalType.BORN_DIGITAL_REPORT.value == "born_digital_report"


def test_extracted_doc_round_trips_json():
    doc = ExtractedDoc(
        id="d1",
        source_path="/x/d1.pdf",
        source_sha256="abc",
        signal_type=SignalType.MIXED,
        raw_title="D1",
        content="body",
        pages=[PageProvenance(page=1, method=ExtractMethod.PYMUPDF_TEXT,
                              has_text_layer=True, char_count=4)],
        warnings=["page 2 image-only"],
        extractor="pdf",
    )
    restored = ExtractedDoc.model_validate_json(doc.model_dump_json())
    assert restored.signal_type is SignalType.MIXED
    assert restored.pages[0].method is ExtractMethod.PYMUPDF_TEXT
    assert restored.warnings == ["page 2 image-only"]
