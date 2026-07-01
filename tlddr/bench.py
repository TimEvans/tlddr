"""Deterministic benchmark recording and reporting for pipeline runs.

Records one row per measured unit of work to <benchmark_dir>/metrics.jsonl and
renders per-stage / per-unit tables. Corpus-agnostic: every value is passed in
or looked up from a supplied extracted store, so any run points it at its own
benchmark directory. No model calls; for agentic stages the token/duration
numbers come from the harness's subagent metering and are passed to record_row.
"""
import json
import statistics
import time
from contextlib import contextmanager
from pathlib import Path

METRICS_FILE = "metrics.jsonl"


def metrics_path(benchmark_dir: Path) -> Path:
    return benchmark_dir / METRICS_FILE


def source_size(extracted_dir: Path | None, unit: str) -> tuple[int | None, int | None]:
    """Return (source_chars, source_pages) for a doc unit, or (None, None)."""
    if extracted_dir is None:
        return None, None
    record = extracted_dir / f"{unit}.json"
    if not record.exists():
        return None, None
    doc = json.loads(record.read_text())
    return len(doc.get("content", "")), len(doc.get("pages", []))


def record_row(benchmark_dir: Path, *, stage: str, unit: str, tokens: int,
               duration_ms: int, unit_kind: str = "doc", model: str = "",
               tool_uses: int = 0, source_chars: int | None = None,
               source_pages: int | None = None, notes: str = "") -> dict:
    """Append one benchmark row and return it."""
    row = {
        "stage": stage, "unit": unit, "unit_kind": unit_kind, "model": model,
        "tokens": tokens, "tool_uses": tool_uses, "duration_ms": duration_ms,
        "source_chars": source_chars, "source_pages": source_pages, "notes": notes,
    }
    benchmark_dir.mkdir(parents=True, exist_ok=True)
    with metrics_path(benchmark_dir).open("a") as f:
        f.write(json.dumps(row) + "\n")
    return row


def load_rows(benchmark_dir: Path) -> list[dict]:
    path = metrics_path(benchmark_dir)
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


@contextmanager
def timed_stage(benchmark_dir: Path | None, stage: str, unit: str = "all",
                unit_kind: str = "stage", notes: str = ""):
    """Time a deterministic stage; record a zero-token row when enabled."""
    if benchmark_dir is None:
        yield
        return
    start = time.monotonic()
    try:
        yield
    finally:
        ms = int((time.monotonic() - start) * 1000)
        record_row(benchmark_dir, stage=stage, unit=unit, unit_kind=unit_kind,
                   tokens=0, duration_ms=ms, notes=notes)
