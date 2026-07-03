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
| **Reviewer session (apex)** | **PENDING — tooling ready, not yet run** | 19 verify questions sit in `_triage.md` / `report_comments.md` with `> answer:` slots |

## The open item: the Reviewer session (the proving gate)

Per `skills/draft-verify`, the run stops here for a Reviewer to decide, per question: **accept as an acknowledged finding** (stays in the sidecar as a disclosed caveat) **or re-draft** the affected section. The 19 questions are all legitimate precision-nits, **not errors** (0 contradictions across 547 claims): causal/editorial embellishment not on the cited page (esp. "…due to the Hess acquisition"), citation off-by-one (figure correct, adjacent uncited page), and glossary phrasing drift. See the full list in `chevron/report/report_comments.md` (search `[judge:`).

### Human-review tooling status (verified 2026-07-03)
- **BUILT — the answer loop (D6) is complete.** `tlddr answer-commit (--answers <f> | --triage <f>) --output <base>` (new `tlddr/answer.py`) validates Reviewer answer records `{id, disposition, answer}` against the question store, resolves matches, clears `blocking`, and writes a deduped `work/worklist.json` routed by `raised_by` (a `verify`/`draft` question routes to a section re-pass; an `understand` question routes to a node re-pass). Re-verify suppresses verdicts matching an already-resolved question's identity, so a re-pass never re-raises a settled question; `render_triage` splits Open vs Resolved; `render_sidecar` shows accepted findings as disclosed caveats; `assemble` warns if a target has cycled 3+ times.
- **The interactive procedure is `skills/review`:** one open question at a time — states the question, links the `[[node_id]]`/cited pages, offers a grounded probable answer (ranked interpretations where genuinely ambiguous), and only commits on the Reviewer's explicit sign-off. It then walks the resulting worklist (re-drafts each named section via `skills/draft`'s new "Re-pass mode" note, re-runs `draft-verify`, or re-understands a node via `skills/understand`'s note) and re-`assemble`s to check convergence.
- **How to resolve these 19 questions:** run `skills/review` with `export TLDDR_OUTPUT=chevron` (the existing `chevron/{work,vault,report,benchmark}` layout already matches the `<base>/work|vault|report` convention). Sign off each question, commit with `tlddr answer-commit --answers <answers.json> --output chevron` (or fill `> answer:` slots in `chevron/vault/_triage.md` with a leading `[revise]`/`[accept]` tag and run `tlddr answer-commit --triage chevron/vault/_triage.md --output chevron` instead), then walk the printed worklist and re-run `tlddr assemble --output chevron`.
- **Not yet run:** nobody has walked these 19 questions through the loop yet — this Chevron run remains the live, un-exercised proving case for `skills/review`.

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
