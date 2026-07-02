# Single Output Base Directory Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give the tl-ddr pipeline one `--output` base directory so a run's work, vault, and report outputs stay bundled and isolated per source corpus.

**Architecture:** Add a `resolve_base()` resolver and a frozen `Paths` deriver to `tlddr/cli.py`. The resolver picks the base from `--output` > `TLDDR_OUTPUT` env > default `./.tlddr`; `Paths` derives every output root (`work/`, `vault/`, `report/`, and the files under them) from that base. Only the argparse/`main()` layer changes — the low-level functions keep their explicit-path signatures, so most existing tests are untouched. The four SKILL.md files are updated to reference base-relative paths.

**Tech Stack:** Python 3.11+, stdlib only (`argparse`, `pathlib`, `os`, `dataclasses`), pytest.

## Global Constraints

- No new dependencies — stdlib only (`os`, `dataclasses` added to `tlddr/cli.py`).
- Resolution precedence, exact: `--output` flag > `TLDDR_OUTPUT` env var > default `./.tlddr`.
- Layout under the base, exact: `base/work` (extracted, thumbnails, nodes, enrichment, `sections.json`, `questions.json`, `claims.json`, `extraction-report.md`), `base/vault`, `base/report`.
- The low-level functions (`run_extract`, `understand_slice`, `understand_commit`, `understand_render`, `draft_read`, `draft_commit`, `draft_verify_commit`, `draft_eval`, `assemble`) keep their current explicit-path signatures unchanged.
- `--benchmark` stays an independent, opt-in flag on `extract` / `draft-eval` / `assemble` and is NOT derived from `--output`. The `bench` subcommand is untouched.
- The standalone `sections` command keeps its own `--sections` argument (it validates an arbitrary spec and has no base context).
- No emojis in code, comments, or commit messages. Conventional-commit messages. TDD: failing test first, frequent commits.

---

### Task 1: `resolve_base()` and `Paths` deriver

Pure helpers with no I/O. Establishes the resolution precedence and the path layout that every later task consumes.

**Files:**
- Modify: `tlddr/cli.py` (add two imports; add helpers after the `from tlddr import bench` import on line 22)
- Test: `tests/test_cli_paths.py` (create)

**Interfaces:**
- Consumes: nothing.
- Produces:
  - `resolve_base(cli_output: Path | None) -> Path`
  - `Paths` frozen dataclass with `base: Path` and read-only properties: `work`, `extracted`, `thumbnails`, `nodes`, `enrichment`, `sections`, `questions`, `claims`, `vault`, `report` (all `-> Path`).

- [ ] **Step 1: Write the failing tests**

Create `tests/test_cli_paths.py`:

```python
from pathlib import Path
from tlddr.cli import resolve_base, Paths


def test_resolve_base_prefers_flag_over_env(monkeypatch):
    monkeypatch.setenv("TLDDR_OUTPUT", "env-dir")
    assert resolve_base(Path("flag-dir")) == Path("flag-dir")


def test_resolve_base_uses_env_when_no_flag(monkeypatch):
    monkeypatch.setenv("TLDDR_OUTPUT", "env-dir")
    assert resolve_base(None) == Path("env-dir")


def test_resolve_base_defaults_to_dot_tlddr(monkeypatch):
    monkeypatch.delenv("TLDDR_OUTPUT", raising=False)
    assert resolve_base(None) == Path(".tlddr")


def test_paths_derives_layout_from_base():
    p = Paths(Path("/out/run1"))
    assert p.work == Path("/out/run1/work")
    assert p.extracted == Path("/out/run1/work/extracted")
    assert p.thumbnails == Path("/out/run1/work/thumbnails")
    assert p.nodes == Path("/out/run1/work/nodes")
    assert p.enrichment == Path("/out/run1/work/enrichment")
    assert p.sections == Path("/out/run1/work/sections.json")
    assert p.questions == Path("/out/run1/work/questions.json")
    assert p.claims == Path("/out/run1/work/claims.json")
    assert p.vault == Path("/out/run1/vault")
    assert p.report == Path("/out/run1/report")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_cli_paths.py -v`
Expected: FAIL with `ImportError: cannot import name 'resolve_base'`.

- [ ] **Step 3: Add the imports**

In `tlddr/cli.py`, change the top imports so `os` and `dataclass` are available. The current file starts:

```python
import argparse
import json
import re
import sys
from collections.abc import Callable
from pathlib import Path
```

Add `import os` and `from dataclasses import dataclass`:

```python
import argparse
import json
import os
import re
import sys
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
```

- [ ] **Step 4: Add the helpers**

In `tlddr/cli.py`, immediately after the `from tlddr import bench` line (line 22), insert:

```python


def resolve_base(cli_output: Path | None) -> Path:
    """Resolve the output base dir: --output flag > TLDDR_OUTPUT env > ./.tlddr."""
    if cli_output is not None:
        return cli_output
    return Path(os.environ.get("TLDDR_OUTPUT") or ".tlddr")


@dataclass(frozen=True)
class Paths:
    """Derive every output root from a single base directory."""

    base: Path

    @property
    def work(self) -> Path:
        return self.base / "work"

    @property
    def extracted(self) -> Path:
        return self.work / "extracted"

    @property
    def thumbnails(self) -> Path:
        return self.work / "thumbnails"

    @property
    def nodes(self) -> Path:
        return self.work / "nodes"

    @property
    def enrichment(self) -> Path:
        return self.work / "enrichment"

    @property
    def sections(self) -> Path:
        return self.work / "sections.json"

    @property
    def questions(self) -> Path:
        return self.work / "questions.json"

    @property
    def claims(self) -> Path:
        return self.work / "claims.json"

    @property
    def vault(self) -> Path:
        return self.base / "vault"

    @property
    def report(self) -> Path:
        return self.base / "report"
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/test_cli_paths.py -v`
Expected: PASS (4 passed).

- [ ] **Step 6: Commit**

```bash
git add tlddr/cli.py tests/test_cli_paths.py
git commit -m "feat(cli): add resolve_base and Paths output-dir deriver"
```

---

### Task 2: Wire `--output` into extract + understand commands

Replace the per-root flags on the extract and understand subcommands with a single `--output`, deriving all paths via `Paths`. Update the extract main-level tests and `.gitignore`.

After this task, extract/understand use `--output` while the draft commands still use their old flags — both work; each subcommand is independent.

**Files:**
- Modify: `tlddr/cli.py` (argparse for `extract`, `understand-slice`, `understand-commit`, `understand-render`; their dispatch branches in `main()`)
- Modify: `tests/test_cli.py:24-31,129-152` (extract main-level tests)
- Modify: `.gitignore`

**Interfaces:**
- Consumes: `resolve_base`, `Paths` from Task 1.
- Produces: `extract`, `understand-slice`, `understand-commit`, `understand-render` accept `--output <dir>` (optional; resolves via precedence). `extract` writes to `base/work`; `understand-render` writes to `base/vault`. No new function signatures.

- [ ] **Step 1: Update the extract main-level tests (failing)**

In `tests/test_cli.py`, replace `test_main_extract_returns_zero` (lines 24-31) with:

```python
def test_main_extract_returns_zero(tmp_path, simple_docx):
    source = tmp_path / "src"
    source.mkdir()
    (source / simple_docx.name).write_bytes(simple_docx.read_bytes())
    base = tmp_path / "out"
    code = main(["extract", "--source", str(source), "--output", str(base)])
    assert code == 0
    assert (base / "work" / "extraction-report.md").exists()
```

In `test_extract_benchmark_flag_records_stage_row` (lines 129-143), change the two lines that build `out` and call `main`:

```python
    base = tmp_path / "out"
    bench_dir = tmp_path / "benchmark"
    rc = main(["extract", "--source", str(source), "--output", str(base),
               "--benchmark", str(bench_dir)])
```

In `test_extract_without_benchmark_flag_records_nothing` (lines 145-152), change:

```python
    base = tmp_path / "out"
    rc = main(["extract", "--source", str(source), "--output", str(base)])
```

(The `run_extract(source, out)` function-level tests — `test_run_extract_writes_json_and_report`, `test_run_extract_isolates_per_file_failure`, `test_run_extract_skips_boilerplate` — call the function directly and stay unchanged.)

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_cli.py -k "extract" -v`
Expected: FAIL — `--output` is unrecognized (`SystemExit: 2`) on the three edited tests.

- [ ] **Step 3: Update the argparse definitions**

In `tlddr/cli.py` `main()`, replace the `extract` parser block (currently lines 244-247):

```python
    extract_cmd = sub.add_parser("extract", help="extract source documents into node records")
    extract_cmd.add_argument("--source", required=True, type=Path)
    extract_cmd.add_argument("--output", type=Path, default=None)
    extract_cmd.add_argument("--benchmark", type=Path, default=None)
```

Replace the `understand-slice` block (lines 249-251):

```python
    slice_cmd = sub.add_parser("understand-slice", help="print the bounded slice for one document")
    slice_cmd.add_argument("--output", type=Path, default=None)
    slice_cmd.add_argument("--id", required=True)
```

Replace the `understand-commit` block (lines 256-260):

```python
    commit_cmd = sub.add_parser("understand-commit", help="assemble a validated node from agent enrichment")
    commit_cmd.add_argument("--enrichment", required=True, type=Path)
    commit_cmd.add_argument("--output", type=Path, default=None)
```

Replace the `understand-render` block (lines 262-265):

```python
    render_cmd = sub.add_parser("understand-render", help="render the vault, index, and triage")
    render_cmd.add_argument("--output", type=Path, default=None)
```

- [ ] **Step 4: Update the dispatch branches**

In `tlddr/cli.py` `main()`, replace the four dispatch branches for these commands (currently lines 313-327):

```python
    if args.command == "extract":
        paths = Paths(resolve_base(args.output))
        run_extract(args.source, paths.work, args.benchmark)
        return 0
    if args.command == "understand-slice":
        paths = Paths(resolve_base(args.output))
        print(understand_slice(paths.extracted, args.id))
        return 0
    if args.command == "understand-commit":
        paths = Paths(resolve_base(args.output))
        sections = paths.sections if paths.sections.exists() else None
        understand_commit(args.enrichment, paths.extracted, paths.work, sections)
        return 0
    if args.command == "understand-render":
        paths = Paths(resolve_base(args.output))
        sections = paths.sections if paths.sections.exists() else None
        understand_render(paths.work, paths.vault, sections)
        return 0
```

- [ ] **Step 5: Run the full test suite**

Run: `pytest -q`
Expected: PASS. The edited extract tests pass; `test_understand_cli.py` (function-level) and the draft tests (still on old flags) are unaffected.

- [ ] **Step 6: Update `.gitignore`**

The default base `.tlddr/` is already ignored (report and vault now nest inside it). Add the conventional non-default base used for the test-corpus runs. Append to `.gitignore`:

```
output/
```

- [ ] **Step 7: Commit**

```bash
git add tlddr/cli.py tests/test_cli.py .gitignore
git commit -m "feat(cli): derive extract+understand paths from --output base"
```

---

### Task 3: Wire `--output` into draft commands

Replace the per-root flags on the draft subcommands with `--output`, and rewrite `tests/test_draft_cli.py` to the new base layout.

**Files:**
- Modify: `tlddr/cli.py` (argparse for `draft-read`, `draft-commit`, `draft-verify-commit`, `draft-eval`, `assemble`; their dispatch branches)
- Modify: `tests/test_draft_cli.py` (rewrite `_setup`, `_commit_claims`, and all `main()` calls/assertions)

**Interfaces:**
- Consumes: `resolve_base`, `Paths` from Task 1.
- Produces: `draft-read`, `draft-commit`, `draft-verify-commit`, `draft-eval`, `assemble` accept `--output <dir>`; `assemble` writes report to `base/report` and triage to `base/vault`. `--claims` / `--verdicts` stay as explicit agent-input file flags. No new function signatures.

- [ ] **Step 1: Rewrite the draft CLI tests (failing)**

Replace the whole body of `tests/test_draft_cli.py` with:

```python
import json
from pathlib import Path
from tlddr.cli import main
from tlddr.models import ExtractedDoc, Node, PageProvenance, SignalType, ExtractMethod, Confidence, Triage


def _setup(tmp: Path) -> Path:
    base = tmp / "out"
    work = base / "work"
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
    (work / "sections.json").write_text(json.dumps([{"id": "s1", "title": "Overview"},
                                                    {"id": "s2", "title": "Gaps"}]))
    return base


def test_draft_commit_then_assemble_writes_report_and_sidecar(tmp_path):
    base = _setup(tmp_path)
    claims = tmp_path / "claims.json"
    claims.write_text(json.dumps([{
        "section_id": "s1", "text": "Design life is 25 years.",
        "support_level": "fully_supported", "evidence_relation": "quoted",
        "sources": [{"node_id": "r518", "page": 12}],
    }]))

    assert main(["draft-commit", "--claims", str(claims), "--output", str(base)]) == 0
    assert (base / "work" / "claims.json").exists()

    assert main(["assemble", "--output", str(base)]) == 0
    report = (base / "report" / "report.md").read_text()
    sidecar = (base / "report" / "report_comments.md").read_text()
    assert "Design life is 25 years." in report
    assert "[[r518]]" in sidecar
    assert "insufficient evidence" in sidecar.lower()      # s2 had no claims


def test_draft_read_prints_page(tmp_path, capsys):
    base = _setup(tmp_path)
    assert main(["draft-read", "--output", str(base), "--id", "r518", "--pages", "12"]) == 0
    assert "design life 25 years" in capsys.readouterr().out


def _commit_claims(tmp_path, base):
    claims_file = tmp_path / "claims.json"
    claims_file.write_text(json.dumps([{
        "section_id": "s1", "text": "Design life is 25 years.",
        "support_level": "fully_supported", "evidence_relation": "quoted",
        "sources": [{"node_id": "r518", "page": 12}],
    }]))
    main(["draft-commit", "--claims", str(claims_file), "--output", str(base)])
    return claims_file


def test_draft_verify_commit_is_idempotent(tmp_path):
    base = _setup(tmp_path)
    _commit_claims(tmp_path, base)

    verdicts_file = tmp_path / "verdicts.json"
    verdicts_file.write_text(json.dumps([{
        "index": 0, "support_level": "unsupported", "contradiction": False,
        "note": "not actually stated",
    }]))

    main(["draft-verify-commit", "--verdicts", str(verdicts_file), "--output", str(base)])
    main(["draft-verify-commit", "--verdicts", str(verdicts_file), "--output", str(base)])

    qs = json.loads((base / "work" / "questions.json").read_text())
    verify_qs = [q for q in qs if q.get("raised_by") == "verify"]
    assert len(verify_qs) == 1


def test_assemble_writes_triage_md(tmp_path):
    base = _setup(tmp_path)
    _commit_claims(tmp_path, base)

    assert main(["assemble", "--output", str(base)]) == 0
    triage_path = base / "vault" / "_triage.md"
    assert triage_path.exists()
    assert "# Triage" in triage_path.read_text()


def test_draft_commit_is_idempotent_with_unknown_sections(tmp_path):
    base = _setup(tmp_path)
    claims_file = tmp_path / "claims.json"
    claims_file.write_text(json.dumps([{
        "section_id": "s_unknown", "text": "Some claim.",
        "support_level": "fully_supported", "evidence_relation": "quoted",
        "sources": [{"node_id": "r518", "page": 12}],
    }]))

    main(["draft-commit", "--claims", str(claims_file), "--output", str(base)])
    main(["draft-commit", "--claims", str(claims_file), "--output", str(base)])

    qs = json.loads((base / "work" / "questions.json").read_text())
    draft_qs = [q for q in qs if q.get("raised_by") == "draft" and q.get("section_id") == "s_unknown"]
    assert len(draft_qs) == 1
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_draft_cli.py -v`
Expected: FAIL — `--output` is unrecognized (`SystemExit: 2`) on the draft subcommands.

- [ ] **Step 3: Update the argparse definitions**

In `tlddr/cli.py` `main()`, replace the `draft-read` block (currently lines 267-270):

```python
    dread = sub.add_parser("draft-read", help="serve a node's content/pages for drafting")
    dread.add_argument("--output", type=Path, default=None)
    dread.add_argument("--id", required=True)
    dread.add_argument("--pages", type=str, default=None, help="comma-separated page numbers")
```

Replace the `draft-commit` block (lines 272-276):

```python
    dcommit = sub.add_parser("draft-commit", help="validate agent draft claims for a section")
    dcommit.add_argument("--claims", required=True, type=Path)
    dcommit.add_argument("--output", type=Path, default=None)
```

Replace the `draft-verify-commit` block (lines 278-280):

```python
    dverify = sub.add_parser("draft-verify-commit", help="ingest C-lite judge verdicts")
    dverify.add_argument("--verdicts", required=True, type=Path)
    dverify.add_argument("--output", type=Path, default=None)
```

Replace the `draft-eval` block (lines 282-285):

```python
    deval = sub.add_parser("draft-eval", help="print the tier-B groundedness readout")
    deval.add_argument("--output", type=Path, default=None)
    deval.add_argument("--benchmark", type=Path, default=None)
```

Replace the `assemble` block (lines 287-292):

```python
    asm = sub.add_parser("assemble", help="assemble report.md + report_comments.md")
    asm.add_argument("--output", type=Path, default=None)
    asm.add_argument("--benchmark", type=Path, default=None)
```

- [ ] **Step 4: Update the dispatch branches**

In `tlddr/cli.py` `main()`, replace the five dispatch branches (currently lines 328-343):

```python
    if args.command == "draft-read":
        paths = Paths(resolve_base(args.output))
        pages = [int(p) for p in args.pages.split(",")] if args.pages else None
        print(draft_read(paths.extracted, args.id, pages))
        return 0
    if args.command == "draft-commit":
        paths = Paths(resolve_base(args.output))
        sections = paths.sections if paths.sections.exists() else None
        draft_commit(args.claims, paths.extracted, paths.work, sections)
        return 0
    if args.command == "draft-verify-commit":
        paths = Paths(resolve_base(args.output))
        draft_verify_commit(args.verdicts, paths.work)
        return 0
    if args.command == "draft-eval":
        paths = Paths(resolve_base(args.output))
        draft_eval(paths.work, paths.sections, args.benchmark)
        return 0
    if args.command == "assemble":
        paths = Paths(resolve_base(args.output))
        assemble(paths.work, paths.report, paths.sections, paths.vault, args.benchmark)
        return 0
```

(`draft-eval` and `assemble` require sections; they pass `paths.sections` directly. If the file is absent the pipeline prerequisite is unmet and `load_sections` raises — same behavior as the old required `--sections` pointing at a missing file.)

- [ ] **Step 5: Run the full test suite**

Run: `pytest -q`
Expected: PASS (all tests, including the rewritten `tests/test_draft_cli.py` and the unchanged `tests/test_understand_cli.py`).

- [ ] **Step 6: Commit**

```bash
git add tlddr/cli.py tests/test_draft_cli.py
git commit -m "feat(cli): derive draft+assemble paths from --output base"
```

---

### Task 4: Update the skills to base-relative paths

The four SKILL.md files hardcode `.tlddr`, `vault`, and `report`. Update them to reference the run's `$TLDDR_OUTPUT` base and the new `work/` layout, and add an "Output location" preamble to each.

**Files:**
- Modify: `skills/understand/SKILL.md`
- Modify: `skills/draft/SKILL.md`
- Modify: `skills/draft-verify/SKILL.md`
- Modify: `skills/generate-sections/SKILL.md`

**Interfaces:**
- Consumes: the `--output` / `TLDDR_OUTPUT` interface delivered by Tasks 2-3.
- Produces: skill instructions that resolve every path and every `tlddr` invocation under one output base.

- [ ] **Step 1: Find every path reference to change**

Run: `grep -rnE '\.tlddr|--out |--work |--vault |--extracted |vault/|report/' skills/`
This lists every store path and CLI flag that must move. Keep the output open while editing.

- [ ] **Step 2: Add the "Output location" preamble to each SKILL.md**

Insert this block near the top of each of the four SKILL.md files (immediately after the front-matter / first heading, before the first "Prerequisites"/"Preconditions" section), verbatim:

```markdown
## Output location

All paths below are relative to the run's output base, `$TLDDR_OUTPUT` (default
`.tlddr` when unset). Set it once at the start of the run so every `tlddr`
command and file reference resolves under the same directory:

    export TLDDR_OUTPUT=<your-output-dir>   # e.g. output/Chevron-10K

Work artifacts live under `$TLDDR_OUTPUT/work/`, the rendered vault under
`$TLDDR_OUTPUT/vault/`, and the report under `$TLDDR_OUTPUT/report/`.
```

- [ ] **Step 3: Apply the path mapping across the four files**

For every occurrence found in Step 1, apply this mapping (store paths and CLI flags):

| Old | New |
| --- | --- |
| `.tlddr/extracted` | `$TLDDR_OUTPUT/work/extracted` |
| `.tlddr/nodes` | `$TLDDR_OUTPUT/work/nodes` |
| `.tlddr/enrichment` | `$TLDDR_OUTPUT/work/enrichment` |
| `.tlddr/sections.json` | `$TLDDR_OUTPUT/work/sections.json` |
| `.tlddr/questions.json` | `$TLDDR_OUTPUT/work/questions.json` |
| `.tlddr/claims.json` | `$TLDDR_OUTPUT/work/claims.json` |
| `.tlddr/verdicts.json` | `$TLDDR_OUTPUT/work/verdicts.json` |
| `.tlddr/draft-<section_id>.json` | `$TLDDR_OUTPUT/work/draft-<section_id>.json` |
| `.tlddr/extraction-report.md` | `$TLDDR_OUTPUT/work/extraction-report.md` |
| `vault/` (store path) | `$TLDDR_OUTPUT/vault/` |
| `report/` (store path) | `$TLDDR_OUTPUT/report/` |

And for the `tlddr` invocations, collapse the old flags to `--output`:

| Old flags | New |
| --- | --- |
| `tlddr extract --source <dir> --out .tlddr` | `tlddr extract --source <dir> --output "$TLDDR_OUTPUT"` |
| `--extracted .tlddr/extracted` | `--output "$TLDDR_OUTPUT"` |
| `--out .tlddr` / `--work .tlddr` | `--output "$TLDDR_OUTPUT"` |
| `--out report` | `--output "$TLDDR_OUTPUT"` |
| `--vault vault` | (drop; derived from `--output`) |
| `--sections .tlddr/sections.json` (on `understand-commit`, `understand-render`, `draft-commit`, `draft-eval`, `assemble`) | (drop; derived from `--output`) |

Exception — the standalone validator `tlddr sections --sections <path>` KEEPS its flag; in `generate-sections/SKILL.md` point it at the derived location: `tlddr sections --sections "$TLDDR_OUTPUT/work/sections.json"`, and have that skill write the curated spec to `$TLDDR_OUTPUT/work/sections.json`.

Also update the `understand` skill's TurboVault registration step to register `$TLDDR_OUTPUT/vault/` (was `vault/`).

- [ ] **Step 4: Verify no stale store paths or flags remain**

Run: `grep -rnE '\-\-(out|work|vault|extracted) |\.tlddr/(extracted|nodes|claims|sections|questions|verdicts|enrichment)' skills/`
Expected: no matches. (A remaining `.tlddr` only as the "default `.tlddr` when unset" note inside each preamble is fine.)

Run: `grep -rln 'TLDDR_OUTPUT' skills/`
Expected: all four SKILL.md files listed (each has the preamble).

- [ ] **Step 5: Commit**

```bash
git add skills/
git commit -m "docs(skills): reference the --output base and work/ layout"
```

---

## Self-Review

**Spec coverage:**
- Interface (env var + `--output` + `.tlddr` default, precedence) → Task 1 (`resolve_base`) + Tasks 2-3 (flag wiring). Covered.
- Layout (`work/`, `vault/`, `report/`) → Task 1 (`Paths`), asserted in `test_paths_derives_layout_from_base` and the rewritten draft tests. Covered.
- Path derivation table + explicit agent-input flags kept (`--enrichment`, `--claims`, `--verdicts`) → Tasks 2-3 dispatch. Covered.
- Standalone `sections` keeps `--sections` → left untouched in Tasks 2-3; noted in Global Constraints and Task 4 exception. Covered.
- Implementation confined to CLI layer, low-level signatures unchanged → Tasks 2-3 pass derived paths into unchanged functions; `test_understand_cli.py` unchanged proves it. Covered.
- Ripple: 4 skills → Task 4; `.gitignore` → Task 2; tests → Tasks 1-3. Covered.
- Benchmark note: `--benchmark` intentionally left independent — recorded in Global Constraints (addition beyond the spec, which predated the benchmark merge).

**Placeholder scan:** No TBD/TODO; every code and test block is complete; Task 4 uses explicit mapping tables and a verbatim preamble rather than "similar to".

**Type consistency:** `resolve_base(cli_output: Path | None) -> Path` and the `Paths` property names (`work`, `extracted`, `thumbnails`, `nodes`, `enrichment`, `sections`, `questions`, `claims`, `vault`, `report`) are used identically in Task 1's definition and Tasks 2-3's dispatch. `run_extract(source, paths.work, args.benchmark)`, `understand_commit(args.enrichment, paths.extracted, paths.work, sections)`, `assemble(paths.work, paths.report, paths.sections, paths.vault, args.benchmark)` match the current function signatures in `tlddr/cli.py`.
