# Benchmark Tooling Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add corpus-agnostic, deterministic benchmark tooling to the `tlddr` CLI so any pipeline run can record per-unit speed/token metrics into its own benchmark directory and print normalized tables.

**Architecture:** A new deterministic module `tlddr/bench.py` owns recording (`record_row`/`load_rows`/`source_size`/`timed_stage`) and reporting (`render_report`). The CLI exposes it two ways: a `tlddr bench record` / `tlddr bench report` subcommand group for agentic units (fed the harness's own `tokens`/`tool_uses`/`duration_ms`), and a `--benchmark <dir>` flag on the deterministic stage commands (`extract`, `draft-eval`, `assemble`) that auto-records their wall-clock. No model calls anywhere; the tool is fed numbers, it never estimates them.

**Tech Stack:** Python 3.11+, stdlib only (json, statistics, time, argparse, contextlib), pytest.

## Design decisions (settled in brainstorming dialogue)

- **Location/interface:** integrated into the `tlddr` CLI (not a standalone script, not a separate package) — most discoverable, one command surface.
- **Output location:** an explicit `--benchmark <dir>` argument (e.g. `chevron/benchmark/`), its own directory, NOT derived from `--out`. Metrics live in `<dir>/metrics.jsonl`.
- **Test-agnostic:** the module knows nothing about any corpus; every value is passed in or looked up from a supplied `--extracted` store. Any run points it at its own `--benchmark` dir.
- **Two clocks kept distinct:** per-unit `duration_ms` is isolated work-time; the per-stage total equals wall-clock only under sequential dispatch (the report says so).
- **Normalization is the headline:** raw tokens/unit is misleading across a 126-page 10-K vs a 1-page exhibit, so the report shows tokens per 1k source chars and per page.
- **Deterministic recording path:** agentic token/duration numbers come from the harness's subagent-completion metering and are passed to `bench record`; the tool does not call any model.

## Global Constraints

- Python `>=3.11`. Run tests with `.venv/bin/pytest`.
- Stdlib only — no new dependencies.
- No emojis anywhere (code, comments, commits) — hard rule.
- Conventional commits (`type(scope): description`).
- The benchmark directory argument is `--benchmark <dir>` everywhere it appears; the metrics file is always `<dir>/metrics.jsonl`.
- Row schema (exact keys, in this order): `stage, unit, unit_kind, model, tokens, tool_uses, duration_ms, source_chars, source_pages, notes`.
- Deterministic rows use `tokens=0`; `source_chars`/`source_pages` are `None` unless a doc lookup supplies them.
- Follow the existing `tlddr/cli.py` pattern: thin top-level functions per command, argparse subparsers wired in `main`.
- Branch `benchmark-tooling` off `main` before Task 1; do not commit to `main`.

---

### Task 1: `bench.py` recording primitives

The append-only recorder, loader, source-size lookup, and the deterministic-stage timer.

**Files:**
- Create: `tlddr/bench.py`
- Test: `tests/test_bench.py` (new)

**Interfaces:**
- Produces:
  - `metrics_path(benchmark_dir: Path) -> Path`
  - `source_size(extracted_dir: Path | None, unit: str) -> tuple[int | None, int | None]`
  - `record_row(benchmark_dir: Path, *, stage: str, unit: str, tokens: int, duration_ms: int, unit_kind: str = "doc", model: str = "", tool_uses: int = 0, source_chars: int | None = None, source_pages: int | None = None, notes: str = "") -> dict`
  - `load_rows(benchmark_dir: Path) -> list[dict]`
  - `timed_stage(benchmark_dir: Path | None, stage: str, unit: str = "all", unit_kind: str = "stage", notes: str = "")` — context manager

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_bench.py
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/test_bench.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'tlddr.bench'`

- [ ] **Step 3: Write the module**

```python
# tlddr/bench.py
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/test_bench.py -v`
Expected: PASS (all 7 tests)

- [ ] **Step 5: Commit**

```bash
git add tlddr/bench.py tests/test_bench.py
git commit -m "feat(bench): deterministic benchmark recording primitives"
```

---

### Task 2: `bench.py` report rendering

Turn recorded rows into per-stage and per-unit markdown tables, normalized by source size.

**Files:**
- Modify: `tlddr/bench.py` (add `render_report` and its private helpers)
- Test: `tests/test_bench.py` (add render tests)

**Interfaces:**
- Consumes: rows shaped by `record_row` (Task 1).
- Produces: `render_report(rows: list[dict]) -> str`

- [ ] **Step 1: Write the failing tests**

```python
# add to tests/test_bench.py
def test_render_report_empty():
    assert bench.render_report([]) == "no benchmark rows recorded yet"


def test_render_report_has_stage_and_unit_tables_with_normalization():
    rows = [
        {"stage": "extract", "unit": "all", "unit_kind": "stage", "model": "",
         "tokens": 0, "tool_uses": 0, "duration_ms": 2656,
         "source_chars": None, "source_pages": None, "notes": ""},
        {"stage": "understand-p1", "unit": "cvx", "unit_kind": "doc", "model": "sonnet",
         "tokens": 41075, "tool_uses": 17, "duration_ms": 170046,
         "source_chars": 599356, "source_pages": 126, "notes": ""},
        {"stage": "understand-p1", "unit": "ex21", "unit_kind": "doc", "model": "sonnet",
         "tokens": 8000, "tool_uses": 4, "duration_ms": 20000,
         "source_chars": 2000, "source_pages": 1, "notes": ""},
    ]
    out = bench.render_report(rows)
    assert "## Per-stage summary" in out
    assert "## Per-unit detail" in out
    # stages appear in first-seen order
    assert out.index("extract") < out.index("understand-p1")
    # normalization present: 41075 / (599356/1000) ~= 69 tok/1k
    assert "69" in out
    # small doc has high density: 8000 / (2000/1000) = 4000 tok/1k
    assert "4000" in out
    # deterministic stage labeled, agentic totals reported
    assert "deterministic" in out
    assert "Totals (agentic)" in out
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/test_bench.py -k render -v`
Expected: FAIL with `AttributeError: module 'tlddr.bench' has no attribute 'render_report'`

- [ ] **Step 3: Add the report functions**

Append to `tlddr/bench.py`:

```python
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/test_bench.py -v`
Expected: PASS (all Task 1 + Task 2 tests)

- [ ] **Step 5: Commit**

```bash
git add tlddr/bench.py tests/test_bench.py
git commit -m "feat(bench): normalized per-stage and per-unit report rendering"
```

---

### Task 3: `tlddr bench record` / `tlddr bench report` subcommands

Expose recording and reporting through the CLI for agentic units (fed harness numbers).

**Files:**
- Modify: `tlddr/cli.py` (add `import`, two thin functions, a nested `bench` subparser, dispatch)
- Test: `tests/test_cli.py` (add subcommand tests)

**Interfaces:**
- Consumes: `bench.source_size`, `bench.record_row`, `bench.load_rows`, `bench.render_report` (Tasks 1-2).
- Produces:
  - `bench_record(benchmark_dir: Path, extracted_dir: Path | None, stage: str, unit: str, kind: str, model: str, tokens: int, tools: int, ms: int, notes: str) -> dict`
  - `bench_report(benchmark_dir: Path) -> str`

- [ ] **Step 1: Write the failing tests**

```python
# add to tests/test_cli.py
import json as _json
from tlddr.cli import bench_record, bench_report


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
    bench_dir = tmp_path / "b"
    rc = main(["bench", "record", "--benchmark", str(bench_dir), "--stage", "draft",
               "--unit", "sec-a", "--kind", "section", "--model", "sonnet",
               "--tokens", "9000", "--tools", "5", "--ms", "30000"])
    assert rc == 0
    rc = main(["bench", "report", "--benchmark", str(bench_dir)])
    assert rc == 0
    assert "Per-stage summary" in capsys.readouterr().out
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/test_cli.py -k bench -v`
Expected: FAIL with `ImportError: cannot import name 'bench_record' from 'tlddr.cli'`

- [ ] **Step 3: Add the CLI functions**

In `tlddr/cli.py`, add the import near the other `tlddr` imports:

```python
from tlddr import bench
```

Add these two functions (place them after `assemble`):

```python
def bench_record(benchmark_dir: Path, extracted_dir: Path | None, stage: str,
                 unit: str, kind: str, model: str, tokens: int, tools: int,
                 ms: int, notes: str) -> dict:
    source_chars, source_pages = (
        bench.source_size(extracted_dir, unit) if kind == "doc" else (None, None))
    row = bench.record_row(benchmark_dir, stage=stage, unit=unit, unit_kind=kind,
                           model=model, tokens=tokens, tool_uses=tools, duration_ms=ms,
                           source_chars=source_chars, source_pages=source_pages, notes=notes)
    print(f"recorded {stage}/{unit}: {tokens} tok, {tools} tools, {ms} ms"
          + (f", {source_chars} src chars / {source_pages} pages"
             if source_chars is not None else ""))
    return row


def bench_report(benchmark_dir: Path) -> str:
    return bench.render_report(bench.load_rows(benchmark_dir))
```

- [ ] **Step 4: Add the subparser and dispatch**

In `main`, after the `asm` subparser block, add the nested `bench` group:

```python
    bench_cmd = sub.add_parser("bench", help="record and report run benchmarks")
    bench_sub = bench_cmd.add_subparsers(dest="bench_command", required=True)

    brec = bench_sub.add_parser("record", help="append one benchmark row")
    brec.add_argument("--benchmark", required=True, type=Path)
    brec.add_argument("--stage", required=True)
    brec.add_argument("--unit", required=True)
    brec.add_argument("--kind", default="doc", choices=["doc", "section", "corpus", "stage"])
    brec.add_argument("--model", default="")
    brec.add_argument("--tokens", required=True, type=int)
    brec.add_argument("--tools", default=0, type=int)
    brec.add_argument("--ms", required=True, type=int)
    brec.add_argument("--extracted", type=Path, default=None)
    brec.add_argument("--notes", default="")

    brep = bench_sub.add_parser("report", help="print benchmark tables")
    brep.add_argument("--benchmark", required=True, type=Path)
```

In the dispatch chain in `main`, add before `return 1`:

```python
    if args.command == "bench":
        if args.bench_command == "record":
            bench_record(args.benchmark, args.extracted, args.stage, args.unit,
                         args.kind, args.model, args.tokens, args.tools, args.ms, args.notes)
        elif args.bench_command == "report":
            print(bench_report(args.benchmark))
        return 0
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/test_cli.py -k bench -v`
Expected: PASS (4 bench tests)

- [ ] **Step 6: Commit**

```bash
git add tlddr/cli.py tests/test_cli.py
git commit -m "feat(cli): tlddr bench record/report subcommands"
```

---

### Task 4: `--benchmark <dir>` flag on the deterministic stages

Let `extract`, `draft-eval`, and `assemble` self-record their wall-clock when a benchmark dir is given.

**Files:**
- Modify: `tlddr/cli.py` (`run_extract`, `draft_eval`, `assemble` signatures + `timed_stage` wrap; three `--benchmark` args; dispatch)
- Test: `tests/test_cli.py` (add flag tests)

**Interfaces:**
- Consumes: `bench.timed_stage` (Task 1).
- Produces: `run_extract(source, out, benchmark=None)`, `draft_eval(work_dir, sections_path, benchmark=None)`, `assemble(work_dir, out_dir, sections_path, vault_dir=Path("vault"), benchmark=None)`.

- [ ] **Step 1: Write the failing test**

```python
# add to tests/test_cli.py
def test_extract_benchmark_flag_records_stage_row(tmp_path, simple_docx):
    source = tmp_path / "src"
    source.mkdir()
    (source / simple_docx.name).write_bytes(simple_docx.read_bytes())
    out = tmp_path / "out"
    bench_dir = tmp_path / "benchmark"
    rc = main(["extract", "--source", str(source), "--out", str(out),
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
    out = tmp_path / "out"
    rc = main(["extract", "--source", str(source), "--out", str(out)])
    assert rc == 0
    assert not (tmp_path / "benchmark" / "metrics.jsonl").exists()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_cli.py -k "benchmark_flag or without_benchmark" -v`
Expected: FAIL — `main` rejects the unknown `--benchmark` argument for `extract` (SystemExit 2)

- [ ] **Step 3: Thread `benchmark` through the three stage functions**

Change `run_extract` signature and wrap its body:

```python
def run_extract(source: Path, out: Path, benchmark: Path | None = None) -> list[ExtractedDoc]:
    with bench.timed_stage(benchmark, "extract"):
        extracted_dir = out / "extracted"
        asset_dir = out / "thumbnails"
        extracted_dir.mkdir(parents=True, exist_ok=True)
        asset_dir.mkdir(parents=True, exist_ok=True)
        ctx = ExtractContext(asset_dir=asset_dir)

        files = sorted(
            p for p in source.rglob("*")
            if p.is_file() and not _is_sec_boilerplate(p)
        )
        docs: list[ExtractedDoc] = []
        for path in files:
            try:
                doc = route(path, ctx)
            except Exception as exc:
                doc = ExtractedDoc(
                    id=doc_id(path),
                    source_path=str(path),
                    source_sha256=sha256_file(path) if path.exists() else "",
                    signal_type=SignalType.UNKNOWN,
                    raw_title=path.stem,
                    content="",
                    warnings=[f"extraction failed: {type(exc).__name__}: {exc}"],
                    extractor="error",
                )
            json_path = extracted_dir / f"{doc.id}.json"
            if json_path.exists():
                print(f"warning: id collision on '{doc.id}', overwriting {json_path}")
            json_path.write_text(doc.model_dump_json(indent=2))
            docs.append(doc)
            print(f"extracted {doc.id} [{doc.signal_type.value}] ({len(doc.warnings)} warnings)")

        (out / "extraction-report.md").write_text(render_report(docs))
        print(f"\nwrote {len(docs)} records and extraction-report.md to {out}")
    return docs
```

Change `draft_eval`:

```python
def draft_eval(work_dir: Path, sections_path: Path, benchmark: Path | None = None) -> None:
    with bench.timed_stage(benchmark, "draft-eval"):
        print(groundedness_readout(_load_claims(work_dir), load_sections(sections_path)))
```

Change `assemble` (add the param, wrap the body):

```python
def assemble(work_dir: Path, out_dir: Path, sections_path: Path,
             vault_dir: Path = Path("vault"), benchmark: Path | None = None) -> None:
    with bench.timed_stage(benchmark, "assemble"):
        claims = _load_claims(work_dir)
        sections = load_sections(sections_path)
        questions_path = work_dir / "questions.json"
        questions = ([Question.model_validate(q) for q in json.loads(questions_path.read_text())]
                     if questions_path.exists() else [])
        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / "report.md").write_text(render_published(sections, claims))
        (out_dir / "report_comments.md").write_text(render_sidecar(sections, claims, questions))
        nodes = [Node.model_validate_json(p.read_text())
                 for p in sorted((work_dir / "nodes").glob("*.json"))]
        vault_dir.mkdir(parents=True, exist_ok=True)
        (vault_dir / "_triage.md").write_text(render_triage(nodes, questions, sections))
        print(f"assembled {len(claims)} claims into report.md + report_comments.md")
```

Note: `render_report` (the extraction report) and `bench` are both imported already; no name clash because the extraction report is `render_report(docs)` from `tlddr.extract.report` and bench's is `bench.render_report`.

- [ ] **Step 4: Add the `--benchmark` args and update dispatch**

Add to the three subparsers in `main`:

```python
    extract_cmd.add_argument("--benchmark", type=Path, default=None)
```
```python
    deval.add_argument("--benchmark", type=Path, default=None)
```
```python
    asm.add_argument("--benchmark", type=Path, default=None)
```

Update the three dispatch lines in `main`:

```python
    if args.command == "extract":
        run_extract(args.source, args.out, args.benchmark)
        return 0
```
```python
    if args.command == "draft-eval":
        draft_eval(args.work, args.sections, args.benchmark)
        return 0
```
```python
    if args.command == "assemble":
        assemble(args.work, args.out, args.sections, args.vault, args.benchmark)
        return 0
```

- [ ] **Step 5: Run the full suite**

Run: `.venv/bin/pytest -q`
Expected: PASS — the two new flag tests plus all prior tests (121 from main + the new bench/cli tests), output pristine.

- [ ] **Step 6: Commit**

```bash
git add tlddr/cli.py tests/test_cli.py
git commit -m "feat(cli): --benchmark flag self-records extract/draft-eval/assemble timing"
```

---

## Self-review

**Spec coverage:**
- Location = `tlddr` CLI subcommands -> Task 3. Covered.
- Output = explicit `--benchmark <dir>`, own directory, `<dir>/metrics.jsonl` -> Tasks 1, 3, 4. Covered.
- Test-agnostic (values passed / looked up from supplied `--extracted`) -> `source_size` Task 1, `bench_record` Task 3. Covered.
- Two clocks distinct (report says "= stage wall-clock under sequential dispatch") -> Task 2 `_stage_summary`. Covered.
- Normalization (tok/1k chars, tok/page) -> Task 2. Covered.
- Deterministic (no model calls, numbers fed in) -> whole module stdlib-only; `bench record` takes `--tokens`/`--ms`. Covered.
- `--benchmark` flag auto-records deterministic stages -> Task 4 (`extract`, `draft-eval`, `assemble`). Covered.
- Row schema exact keys/order -> Task 1 `record_row` + Task 1 test asserting `list(stored.keys())`. Covered.

**Placeholder scan:** No TBD/TODO; every code step shows complete code; every test step shows the test body.

**Type consistency:** `record_row` keyword signature is identical in Task 1 definition and Task 3 `bench_record` call. `render_report(rows)` defined Task 2, called Task 3 `bench_report`. `timed_stage(benchmark_dir, stage, ...)` defined Task 1, used Task 4. `bench_record(benchmark_dir, extracted_dir, stage, unit, kind, model, tokens, tools, ms, notes)` defined Task 3, called with matching positional order in the Task 3 tests and the `main` dispatch. `run_extract(source, out, benchmark=None)` matches the Task 4 dispatch. Consistent.
