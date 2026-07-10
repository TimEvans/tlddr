import json as _json
from pathlib import Path
from tlddr.cli import run_extract, main, _is_sec_boilerplate, bench_record, bench_report
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
    base = tmp_path / "out"
    code = main(["extract", "--source", str(source), "--output", str(base)])
    assert code == 0
    assert (base / ".tlddr" / "extraction-report.md").exists()


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


def test_bench_record_looks_up_source_size_for_doc(tmp_path):
    extracted = tmp_path / "extracted"
    extracted.mkdir()
    (extracted / "cvx.json").write_text(_json.dumps({"content": "x" * 500, "pages": [{"page": 1}]}))
    bench_dir = tmp_path / "benchmark"
    row = bench_record(bench_dir, extracted, "understand-p1", "cvx", "doc",
                       "sonnet", 8000, 4, 20000, "")
    assert row["source_chars"] == 500 and row["source_pages"] == 1
    assert (bench_dir / "metrics.jsonl").exists()


def test_bench_record_non_doc_kind_skips_lookup(tmp_path):
    row = bench_record(tmp_path / "b", None, "understand-p2", "corpus", "corpus",
                       "sonnet", 5000, 3, 12000, "edges")
    assert row["source_chars"] is None and row["unit_kind"] == "corpus"


def test_bench_report_renders_recorded_rows(tmp_path):
    bench_dir = tmp_path / "b"
    bench_record(bench_dir, None, "draft", "sec-a", "section", "sonnet", 9000, 5, 30000, "")
    out = bench_report(bench_dir)
    assert "## Per-stage summary" in out and "sec-a" in out


def test_main_bench_record_and_report(tmp_path, capsys):
    from tlddr.cli import Paths
    base = tmp_path / "run"
    rc = main(["bench", "record", "--output", str(base), "--stage", "draft",
               "--unit", "sec-a", "--kind", "section", "--model", "sonnet",
               "--tokens", "9000", "--tools", "5", "--ms", "30000"])
    assert rc == 0
    rc = main(["bench", "report", "--benchmark", str(Paths(base).benchmark)])
    assert rc == 0
    assert "Per-stage summary" in capsys.readouterr().out


def test_bench_record_derives_benchmark_dir_from_output_base(tmp_path):
    base = tmp_path / "run"
    rc = main(["bench", "record", "--output", str(base), "--stage", "understand",
               "--unit", "doc1", "--tokens", "500", "--ms", "1200"])
    assert rc == 0
    from tlddr import bench
    from tlddr.cli import Paths
    rows = bench.load_rows(Paths(base).benchmark)
    assert len(rows) == 1
    assert rows[0]["stage"] == "understand" and rows[0]["tokens"] == 500


def test_extract_benchmark_flag_records_stage_row(tmp_path, simple_docx):
    source = tmp_path / "src"
    source.mkdir()
    (source / simple_docx.name).write_bytes(simple_docx.read_bytes())
    base = tmp_path / "out"
    bench_dir = tmp_path / "benchmark"
    rc = main(["extract", "--source", str(source), "--output", str(base),
               "--benchmark", str(bench_dir)])
    assert rc == 0
    from tlddr import bench
    rows = bench.load_rows(bench_dir)
    assert len(rows) == 1
    assert rows[0]["stage"] == "extract" and rows[0]["tokens"] == 0
    assert rows[0]["unit_kind"] == "stage"


def test_extract_without_benchmark_flag_records_nothing(tmp_path, simple_docx):
    source = tmp_path / "src"
    source.mkdir()
    (source / simple_docx.name).write_bytes(simple_docx.read_bytes())
    base = tmp_path / "out"
    rc = main(["extract", "--source", str(source), "--output", str(base)])
    assert rc == 0
    assert not (tmp_path / "benchmark" / "metrics.jsonl").exists()
