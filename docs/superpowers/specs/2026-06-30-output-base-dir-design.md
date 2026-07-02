# Single output base directory

**Date:** 2026-06-30
**Status:** Approved

## Problem

The tl-ddr pipeline writes to three separate output roots, each configured by its
own flag and each defaulting to a different location in the current directory:

- `.tlddr/` — work / intermediate artifacts (`--out` / `--work` / `--extracted`)
- `vault/` — rendered notes, index, triage (`--vault`)
- `report/` — final `report.md` + `report_comments.md` (`--out` on `assemble`)

When running the pipeline across multiple source corpora (the SEC filings and
engineering-report test sets), the outputs collide: every run writes to the same
`.tlddr` / `vault` / `report` at the repo root, so a second run clobbers the first.
There is no way to say "put everything this run produces over here."

## Goal

One **output base directory** per run that contains everything the run produces —
work artifacts, vault, and report together. Running against a different source
corpus is then just a different base dir, and the outputs stay isolated and
bundled per corpus.

## Interface

The output base is resolved once, per command invocation, with this precedence:

1. `--output <dir>` flag — explicit override, highest priority
2. `TLDDR_OUTPUT` environment variable — set once per run; the normal mechanism
   for batch / multi-folder runs
3. Default `./.tlddr` — a plain single run bundles everything under the
   already-gitignored `.tlddr` dir

Every pipeline subcommand accepts `--output`. Inputs stay as their own flags:
`--source` (extract input corpus), `--id`, `--pages`. The agent-authored transient
inputs keep explicit file flags — see "Path derivation" below.

Rationale for env-var-primary: the pipeline is not a single command. It is ~8
separate `tlddr` invocations driven by the skills. An env var set once at the start
of a run threads through all of them without repeating a flag on every call; the
`--output` flag remains available for one-off overrides.

## Layout

Under the resolved base:

```
<base>/
  work/
    extracted/            one <id>.json per source file (content store)
    thumbnails/           page thumbnails produced during extraction
    nodes/                one <id>.json per committed understanding node
    enrichment/           agent-authored enrichment inputs (understand stage)
    sections.json         curated section spec
    questions.json        quarantine / open-questions queue
    claims.json           committed draft claims store
    extraction-report.md  extraction summary
  vault/
    <id>.md               one rendered note per node
    _index.md             summary table
    _triage.md            Red/Amber/Green grouping + open questions
  report/
    report.md             attributed published draft
    report_comments.md    provenance / findings / open-questions sidecar
```

The hidden `.tlddr` name is retained only as the *default base*. Once a base is
given, the visible `work/` holds what `.tlddr/` used to hold at the repo root.

## Path derivation

All roots currently passed as `--out` / `--work` / `--vault` / `--extracted`
derive deterministically from the base:

| Derived path | Value |
| --- | --- |
| work | `base/work` |
| extracted | `base/work/extracted` |
| thumbnails | `base/work/thumbnails` |
| nodes | `base/work/nodes` |
| enrichment | `base/work/enrichment` |
| sections | `base/work/sections.json` |
| questions | `base/work/questions.json` |
| claims | `base/work/claims.json` |
| vault | `base/vault` |
| report | `base/report` |

**Transient agent inputs keep explicit file flags.** The enrichment JSON
(`--enrichment`), per-section draft claims (`--claims`), and verify verdicts
(`--verdicts`) are produced by the agent and handed to the CLI. The agent writes
them under `base/work/` and passes the path. This keeps a clean separation:
paths the CLI *persists* are derived from the base; files the agent *hands in* are
explicit. (Note: `--claims` is the agent's per-section input file; the committed
`claims.json` store is the derived path above — distinct things.)

The standalone `sections` command (a pure validator/printer for an arbitrary
section spec) keeps its required `--sections` argument — it has no base context.

## Implementation

Confined to the CLI layer (`tlddr/cli.py`). No new module.

A resolver and a frozen path-deriver:

```python
def resolve_base(cli_output: Path | None) -> Path:
    return cli_output or Path(os.environ.get("TLDDR_OUTPUT") or ".tlddr")

@dataclass(frozen=True)
class Paths:
    base: Path
    @property
    def work(self) -> Path:      return self.base / "work"
    @property
    def extracted(self) -> Path: return self.work / "extracted"
    @property
    def nodes(self) -> Path:     return self.work / "nodes"
    @property
    def enrichment(self) -> Path: return self.work / "enrichment"
    @property
    def thumbnails(self) -> Path: return self.work / "thumbnails"
    @property
    def sections(self) -> Path:  return self.work / "sections.json"
    @property
    def questions(self) -> Path: return self.work / "questions.json"
    @property
    def claims(self) -> Path:    return self.work / "claims.json"
    @property
    def vault(self) -> Path:     return self.base / "vault"
    @property
    def report(self) -> Path:    return self.base / "report"
```

The **low-level functions keep their explicit-path signatures unchanged**
(`run_extract(source, out)`, `understand_render(work, vault)`, `assemble(...)`,
etc.). They remain the composition-friendly, directly-testable API. Only `main()`
changes: each subcommand handler resolves the base, constructs `Paths`, and passes
the derived paths into the existing functions.

Consequence: the tests that call the low-level functions directly need no edits.
Only the handful of `main([...])` tests that pass `--out` / `--work` / `--vault`
switch to `--output`.

## Ripple

### Skills (4 SKILL.md files)

`understand`, `draft`, `draft-verify`, `generate-sections` currently reference the
literal paths `.tlddr`, `vault`, `report`. Update each to base-relative paths:

- Add a preamble: *"All paths below are relative to `$TLDDR_OUTPUT` (default
  `.tlddr`). Set it once at the start of the run."*
- Intermediate stores move under `work/`:
  `.tlddr/extracted` → `$TLDDR_OUTPUT/work/extracted`,
  `.tlddr/nodes` → `$TLDDR_OUTPUT/work/nodes`,
  `.tlddr/sections.json` → `$TLDDR_OUTPUT/work/sections.json`,
  `.tlddr/claims.json` → `$TLDDR_OUTPUT/work/claims.json`, etc.
- CLI invocations pass `--output "$TLDDR_OUTPUT"` (or rely on the env var).

### .gitignore

- `.tlddr/` already covers the default base (report and vault now nest inside it).
- The separate `vault/` entry becomes redundant for default runs; leave it (it is
  harmless and still guards a stray repo-root `vault/`).
- Add `output/` as the conventional non-default base used for the test-corpus runs
  so those outputs are not accidentally committed.

### Tests

- Update the `main([...])` flag tests in `test_cli.py` and `test_draft_cli.py`
  to use `--output`.
- Add a test for resolution precedence: flag > `TLDDR_OUTPUT` > default `.tlddr`.
- Add a test asserting the derived layout (`work/`, `vault/`, `report/` under a
  given base) after an extract + render + assemble sequence.

## Out of scope (YAGNI)

- Per-path overrides beyond `--output` (e.g. a separate `--vault-dir`).
- A config-file format for the base.
- Parallel-run locking / contention handling.
- Auto-deriving the output dir name from the source folder.
