import json
from pathlib import Path

from tlddr import bench


def test_record_row_appends_jsonl_with_full_schema(tmp_path):
    row = bench.record_row(
        tmp_path, stage="understand-p1", unit="doc-a", tokens=41075,
        duration_ms=170046, unit_kind="doc", model="sonnet", tool_uses=17,
        source_chars=599356, source_pages=126, notes="n",
    )
    assert row["stage"] == "understand-p1"
    lines = (tmp_path / "metrics.jsonl").read_text().splitlines()
    assert len(lines) == 1
    stored = json.loads(lines[0])
    assert list(stored.keys()) == [
        "stage", "unit", "unit_kind", "model", "tokens",
        "tool_uses", "duration_ms", "source_chars", "source_pages", "notes",
    ]
    assert stored["tokens"] == 41075 and stored["source_pages"] == 126


def test_record_row_appends_not_overwrites(tmp_path):
    bench.record_row(tmp_path, stage="s", unit="a", tokens=1, duration_ms=1)
    bench.record_row(tmp_path, stage="s", unit="b", tokens=2, duration_ms=2)
    assert len(bench.load_rows(tmp_path)) == 2


def test_load_rows_empty_when_missing(tmp_path):
    assert bench.load_rows(tmp_path) == []


def test_source_size_reads_extracted_record(tmp_path):
    extracted = tmp_path / "extracted"
    extracted.mkdir()
    (extracted / "doc-a.json").write_text(json.dumps(
        {"content": "hello world", "pages": [{"page": 1}, {"page": 2}]}))
    assert bench.source_size(extracted, "doc-a") == (11, 2)


def test_source_size_missing_returns_none(tmp_path):
    assert bench.source_size(tmp_path / "nope", "doc-a") == (None, None)
    assert bench.source_size(None, "doc-a") == (None, None)


def test_timed_stage_records_zero_token_row(tmp_path):
    with bench.timed_stage(tmp_path, "extract", notes="55 records"):
        pass
    rows = bench.load_rows(tmp_path)
    assert len(rows) == 1
    assert rows[0]["stage"] == "extract" and rows[0]["tokens"] == 0
    assert rows[0]["unit_kind"] == "stage" and rows[0]["duration_ms"] >= 0


def test_timed_stage_noop_when_dir_none(tmp_path):
    with bench.timed_stage(None, "extract"):
        pass
    assert not (tmp_path / "metrics.jsonl").exists()
