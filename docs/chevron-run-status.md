# Chevron 10-K test run — status & resume runbook

**Last updated:** 2026-07-03 · **State:** pipeline complete through draft-verify + assemble; **paused at the draft-verify proving gate** (19 open verify questions awaiting a human accept/re-draft decision).

This is the focused status for the Chevron full-pipeline test. High-level summary is also in `docs/HANDOFF.md` ("Full-pipeline proving run on Chevron"); benchmark analysis in `chevron/benchmark/CONCLUSIONS.md`.

## What this run is

The whole tl-ddr pipeline exercised end-to-end on a real SEC filing: **Chevron FY2025 10-K + exhibits**, drafted against a **real 42-section annual-report template** (from `/home/tim/Downloads/annual_report_template(2).md`, materialized to `chevron/work/sections.json`). Model for all agentic stages: **Sonnet 4.6**. Isolated output dirs (all gitignored): `chevron/{work,vault,report,benchmark}`.

## Stage-by-stage state

| Stage | State | Key output |
|---|---|---|
| extract | done | 197 files → **55 records** (133 XBRL `R*.htm` + linkbases skipped); 26 text-bearing docs. `chevron/work/extracted/` |
| understand P1 (comprehend) | done | 26 enrichments; flat ~22K tok/doc |
| understand P2 (edges) | done | 46 edges across 25/26 |
| generate-sections | done | 42-section annual-report template → `chevron/work/sections.json` |
| understand-retag | done | 26 nodes re-tagged to the 42 sections (honest: 7 authored front/back-matter sections left empty) |
| commit + render | done | 26 nodes, `chevron/vault/` (`_index.md`, `_triage.md`) |
| **draft** | done | **547 grounded claims / 30 sections**; `chevron/work/claims.json` |
| draft-eval | done | 544 fully / 2 partial / 1 unsupported; 478 quoted / 69 inferred |
| **draft-verify (C-lite judge)** | done | 30 independent judges; **528 confirmed, 19 downgraded, 0 contradictions**; `chevron/work/verdicts.json` |
| assemble | done | `chevron/report/report.md` + `report_comments.md` (incl. the 19 verify questions) |
| **human review (apex)** | **NOT DONE — the pause point** | 19 verify questions sit in `_triage.md` / `report_comments.md` with `> answer:` slots |

## The open item: human review (the proving gate)

Per `skills/draft-verify`, the run stops here for a human to decide, per question: **accept as an acknowledged finding** (stays in the sidecar) **or re-draft** the affected section. The 19 questions are all legitimate precision-nits, **not errors** (0 contradictions across 547 claims): causal/editorial embellishment not on the cited page (esp. "…due to the Hess acquisition"), citation off-by-one (figure correct, adjacent uncited page), and glossary phrasing drift. See the full list in `chevron/report/report_comments.md` (search `[judge:`).

### Human-review tooling status (verified 2026-07-03)
- **Built:** the review *surface* — `Question.answer` field; questions render into `_triage.md` + `report_comments.md` with `> answer:` slots.
- **NOT built:** the answer *loop* — no CLI ingests answers or triggers a re-pass (design D6 is designed-not-implemented). Answering is a manual edit; acting on an answer = manually re-running the affected `draft` section. So "human review" today = read the 19 questions and decide accept/re-draft by hand.

## PRESERVATION WARNING

The entire run output is under **gitignored `chevron/`** — `git clean -fdx` would delete it, and it cost ~**3.3M Sonnet tokens / ~2.5 hr** to produce. This doc + HANDOFF + `chevron/benchmark/CONCLUSIONS.md` (also gitignored) capture the *analysis*, but the artifacts (report, claims, verdicts, vault) are local-only. To preserve: back up `chevron/` outside the repo, or selectively un-gitignore `chevron/report/` + `chevron/work/{claims,verdicts,questions}.json` + `chevron/benchmark/`.

## Deliverables (all local, gitignored)
- `chevron/report/report.md` — attributed 42-section draft (547 claims)
- `chevron/report/report_comments.md` — reviewer sidecar: provenance, inferences, no-evidence gaps, **19 verify questions**
- `chevron/work/{claims,verdicts,questions}.json` — the claim/verdict/question stores
- `chevron/vault/` — 26-node understand vault (`_index.md`, `_triage.md` with answer slots)
- `chevron/benchmark/metrics.jsonl` + `CONCLUSIONS.md` + `run-log.md` — the full benchmark

## Resume commands

Re-print the current state without re-running anything:
```
.venv/bin/python -m tlddr.cli draft-eval  --work chevron/work --sections chevron/work/sections.json
.venv/bin/python -m tlddr.cli bench report --benchmark chevron/benchmark
sed -n '/raised_by.*verify/,+1p' chevron/work/questions.json   # or read report_comments.md
```
Re-assemble after any change (verify questions re-surface):
```
.venv/bin/python -m tlddr.cli assemble --work chevron/work --out chevron/report --sections chevron/work/sections.json --vault chevron/vault --benchmark chevron/benchmark
```
To re-draft a contested section: re-run its `skills/draft` drafter (see `chevron/benchmark/run-log.md` for the per-section node lists), then `draft-commit` (section-scoped, replaces cleanly), then re-`assemble`.
