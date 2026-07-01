from pathlib import Path
from tlddr.cli import run_extract, main, _is_sec_boilerplate
from tlddr.models import SignalType


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


def test_run_extract_isolates_per_file_failure(tmp_path, simple_docx):
    source = tmp_path / "src"
    source.mkdir()
    # one good file
    (source / simple_docx.name).write_bytes(simple_docx.read_bytes())
    # one malformed PDF (valid suffix, invalid content) - would raise in fitz.open
    (source / "broken.pdf").write_bytes(b"%PDF-1.4 not actually a pdf")
    out = tmp_path / "out"

    docs = run_extract(source, out)

    # run completed for BOTH files, report written despite the bad one
    assert len(docs) == 2
    assert (out / "extraction-report.md").exists()
    broken = next(d for d in docs if d.source_path.endswith("broken.pdf"))
    assert broken.extractor == "error"
    assert broken.signal_type is SignalType.UNKNOWN
    assert broken.warnings and "fail" in broken.warnings[0].lower()


def test_is_sec_boilerplate_matches_machine_generated_artifacts():
    for name in (
        "R12.htm", "R1.htm", "R133.htm",
        "0000093410-26-000078-index.html",
        "0000093410-26-000078-index-headers.html",
        "FilingSummary.xml",
        "cvx-20251231_cal.xml", "cvx-20251231_def.xml",
        "cvx-20251231_lab.xml", "cvx-20251231_pre.xml",
        "cvx-20251231.xsd",
        "0000093410-26-000078-xbrl.zip",
    ):
        assert _is_sec_boilerplate(Path("/x") / name), name


def test_is_sec_boilerplate_keeps_real_content():
    for name in ("cvx-20251231.htm", "a12312025ex19.htm", "report.pdf", "notes.docx"):
        assert not _is_sec_boilerplate(Path("/x") / name), name


def test_is_sec_boilerplate_keeps_non_xbrl_zip():
    from tlddr.cli import _is_sec_boilerplate
    from pathlib import Path
    assert not _is_sec_boilerplate(Path("/x/supplemental-data.zip"))
    assert _is_sec_boilerplate(Path("/x/0000093410-26-000078-xbrl.zip"))


def test_run_extract_skips_boilerplate(tmp_path):
    source = tmp_path / "src"
    source.mkdir()
    (source / "cvx-20251231.htm").write_bytes(b"<html><body><p>Real filing content</p></body></html>")
    (source / "R12.htm").write_bytes(b"<html><body><p>Duplicate XBRL fragment</p></body></html>")
    (source / "FilingSummary.xml").write_bytes(b"<xml/>")
    out = tmp_path / "out"
    docs = run_extract(source, out)
    titles = {d.source_path for d in docs}
    assert any("cvx-20251231.htm" in t for t in titles)
    assert not any("R12.htm" in t for t in titles)
    assert not any("FilingSummary.xml" in t for t in titles)
