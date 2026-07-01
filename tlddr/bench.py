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


def _per_1k(tokens: int, chars: int | None) -> str:
    if not chars:
        return "-"
    return f"{tokens / (chars / 1000):.0f}"


def _per_page(tokens: int, pages: int | None) -> str:
    if not pages:
        return "-"
    return f"{tokens / pages:.0f}"


def _fmt_ms(ms: float) -> str:
    return f"{ms / 1000:.1f}s"


def _stage_order(rows: list[dict]) -> list[str]:
    order, seen = [], set()
    for r in rows:
        if r["stage"] not in seen:
            seen.add(r["stage"])
            order.append(r["stage"])
    return order


def _stage_summary(rows: list[dict]) -> str:
    out = ["## Per-stage summary\n",
           "| stage | model | units | total tok | mean tok | median tok | total time | mean time | mean tok/1k |",
           "|---|---|---:|---:|---:|---:|---:|---:|---:|"]
    for stage in _stage_order(rows):
        srows = [r for r in rows if r["stage"] == stage]
        tokens = [r["tokens"] for r in srows]
        durations = [r["duration_ms"] for r in srows]
        densities = [r["tokens"] / (r["source_chars"] / 1000)
                     for r in srows if r.get("source_chars")]
        mean_density = f"{statistics.mean(densities):.0f}" if densities else "-"
        out.append(
            f"| {stage} | {srows[0].get('model') or 'det'} | {len(srows)} | {sum(tokens)} | "
            f"{statistics.mean(tokens):.0f} | {statistics.median(tokens):.0f} | "
            f"{_fmt_ms(sum(durations))} | {_fmt_ms(statistics.mean(durations))} | {mean_density} |")
    agentic = [r for r in rows if r["tokens"] > 0]
    if agentic:
        out.append("")
        out.append(f"**Totals (agentic):** {sum(r['tokens'] for r in agentic)} tokens across "
                   f"{len(agentic)} units; isolated work-time "
                   f"{_fmt_ms(sum(r['duration_ms'] for r in agentic))} "
                   f"(= stage wall-clock under sequential dispatch).")
    return "\n".join(out)


def _unit_detail(rows: list[dict]) -> str:
    out = ["## Per-unit detail\n"]
    for stage in _stage_order(rows):
        srows = [r for r in rows if r["stage"] == stage]
        out.append(f"### {stage}  (model: {srows[0].get('model') or 'deterministic'})\n")
        out.append("| unit | kind | tokens | tools | time | src chars | pages | tok/1k | tok/page |")
        out.append("|---|---|---:|---:|---:|---:|---:|---:|---:|")
        for r in srows:
            out.append(
                f"| {r['unit']} | {r['unit_kind']} | {r['tokens']} | {r['tool_uses']} | "
                f"{_fmt_ms(r['duration_ms'])} | "
                f"{r['source_chars'] if r['source_chars'] is not None else '-'} | "
                f"{r['source_pages'] if r['source_pages'] is not None else '-'} | "
                f"{_per_1k(r['tokens'], r['source_chars'])} | "
                f"{_per_page(r['tokens'], r['source_pages'])} |")
        out.append("")
    return "\n".join(out)


def render_report(rows: list[dict]) -> str:
    if not rows:
        return "no benchmark rows recorded yet"
    return _stage_summary(rows) + "\n\n" + _unit_detail(rows)
