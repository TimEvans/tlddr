import json
from pathlib import Path
from tlddr.cli import main
from tlddr.models import ExtractedDoc, Node, PageProvenance, SignalType, ExtractMethod, Confidence, Triage


def _setup(tmp: Path):
    work = tmp / ".tlddr"
    extracted = work / "extracted"
    nodes = work / "nodes"
    extracted.mkdir(parents=True); nodes.mkdir(parents=True)
    doc = ExtractedDoc(
        id="r518", source_path="/x/r518.pdf", source_sha256="a", signal_type=SignalType.MIXED,
        raw_title="R518", content="--- page 12 ---\ndesign life 25 years",
        pages=[PageProvenance(page=12, method=ExtractMethod.PYMUPDF_TEXT, has_text_layer=True)],
        extractor="pdf")
    (extracted / "r518.json").write_text(doc.model_dump_json())
    node = Node(id="r518", extracted_id="r518", title="R518", doc_type="report", description="d",
                confidence_extraction=Confidence.HIGH, confidence_interpretation=Confidence.HIGH,
                triage=Triage.GREEN, report_sections=["s1"])
    (nodes / "r518.json").write_text(node.model_dump_json())
    sections = tmp / "sections.json"
    sections.write_text(json.dumps([{"id": "s1", "title": "Overview"},
                                    {"id": "s2", "title": "Gaps"}]))
    return work, extracted, sections


def test_draft_commit_then_assemble_writes_report_and_sidecar(tmp_path):
    work, extracted, sections = _setup(tmp_path)
    claims = tmp_path / "claims.json"
    claims.write_text(json.dumps([{
        "section_id": "s1", "text": "Design life is 25 years.",
        "support_level": "fully_supported", "evidence_relation": "quoted",
        "sources": [{"node_id": "r518", "page": 12}],
    }]))

    assert main(["draft-commit", "--claims", str(claims), "--extracted", str(extracted),
                 "--work", str(work), "--sections", str(sections)]) == 0
    assert (work / "claims.json").exists()

    out = tmp_path / "out"
    assert main(["assemble", "--work", str(work), "--out", str(out),
                 "--sections", str(sections)]) == 0
    report = (out / "report.md").read_text()
    sidecar = (out / "report_comments.md").read_text()
    assert "Design life is 25 years." in report
    assert "[[r518]]" in sidecar
    assert "insufficient evidence" in sidecar.lower()      # s2 had no claims


def test_draft_read_prints_page(tmp_path, capsys):
    work, extracted, sections = _setup(tmp_path)
    assert main(["draft-read", "--extracted", str(extracted), "--id", "r518",
                 "--pages", "12"]) == 0
    assert "design life 25 years" in capsys.readouterr().out


def _commit_claims(tmp_path, work, extracted, sections):
    claims_file = tmp_path / "claims.json"
    claims_file.write_text(json.dumps([{
        "section_id": "s1", "text": "Design life is 25 years.",
        "support_level": "fully_supported", "evidence_relation": "quoted",
        "sources": [{"node_id": "r518", "page": 12}],
    }]))
    main(["draft-commit", "--claims", str(claims_file), "--extracted", str(extracted),
          "--work", str(work), "--sections", str(sections)])
    return claims_file


def test_draft_verify_commit_is_idempotent(tmp_path):
    work, extracted, sections = _setup(tmp_path)
    _commit_claims(tmp_path, work, extracted, sections)

    verdicts_file = tmp_path / "verdicts.json"
    verdicts_file.write_text(json.dumps([{
        "index": 0, "support_level": "unsupported", "contradiction": False,
        "note": "not actually stated",
    }]))

    main(["draft-verify-commit", "--verdicts", str(verdicts_file), "--work", str(work)])
    main(["draft-verify-commit", "--verdicts", str(verdicts_file), "--work", str(work)])

    qs = json.loads((work / "questions.json").read_text())
    verify_qs = [q for q in qs if q.get("raised_by") == "verify"]
    assert len(verify_qs) == 1


def test_assemble_writes_triage_md(tmp_path):
    work, extracted, sections = _setup(tmp_path)
    _commit_claims(tmp_path, work, extracted, sections)

    vault = tmp_path / "vault"
    out = tmp_path / "out"
    assert main(["assemble", "--work", str(work), "--out", str(out),
                 "--sections", str(sections), "--vault", str(vault)]) == 0
    assert (vault / "_triage.md").exists()
    triage_text = (vault / "_triage.md").read_text()
    assert "# Triage" in triage_text
