from pathlib import Path
from tlddr.cli import run_extract, main


def test_run_extract_writes_json_and_report(tmp_path, born_digital_pdf, simple_docx, simple_kmz):
    source = tmp_path / "src"
    source.mkdir()
    for f in (born_digital_pdf, simple_docx, simple_kmz):
        (source / f.name).write_bytes(f.read_bytes())
    out = tmp_path / "out"

    docs = run_extract(source, out)

    assert len(docs) == 3
    assert (out / "extraction-report.md").exists()
    json_files = list((out / "extracted").glob("*.json"))
    assert len(json_files) == 3
    report = (out / "extraction-report.md").read_text()
    assert "born" in report


def test_main_extract_returns_zero(tmp_path, simple_docx):
    source = tmp_path / "src"
    source.mkdir()
    (source / simple_docx.name).write_bytes(simple_docx.read_bytes())
    out = tmp_path / "out"
    code = main(["extract", "--source", str(source), "--out", str(out)])
    assert code == 0
    assert (out / "extraction-report.md").exists()
