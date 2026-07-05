# tlddr

[![tests](https://github.com/TimEvans/tlddr/actions/workflows/tests.yml/badge.svg)](https://github.com/TimEvans/tlddr/actions/workflows/tests.yml)

**Template-driven report generation, grounded in a source corpus.**

`tlddr` reads a pile of source documents and drafts a structured report against a
template you provide — so the reviewer's job shifts from "read everything and write from
scratch" to "review, correct, sign off." Every claim carries page-level attribution back
to the document it came from, and the tool **flags what it is unsure about instead of
guessing**: an honest gap is worth more than confident, unverifiable coverage.

In industry terms it is a grounded, attributed report-generation system built on agentic
RAG — claim-level attribution, agentic retrieval, faithfulness verification, and
abstention. Due diligence is the origin and one application; nothing in the machinery is
specific to it. The same pipeline grounds any template-driven report in a source corpus
with page-level citations.

> Status: proof-of-concept. Proven end-to-end on a real SEC filing (Chevron FY2025 10-K)
> drafted against a 42-section annual-report template.

## How it works

A four-stage pipeline over a shared vault, with quarantine as a cross-cutting channel for
anything the tool cannot understand or has no evidence for:

1. **Extract** — route each source document by *signal type* (does the meaning live in the
   text layer or the pixels?), not file extension, into extracted node stubs.
2. **Understand** — per node: describe it, tag it against the report's sections, set
   confidence, and propose cross-document edges. Produces a linked, triaged vault.
3. **Draft** — gather the nodes for each section and draft against it, emitting claims
   carrying `(node_id, page)` provenance. Thin or evidence-free sections become findings,
   not fabrications.
4. **Verify + Assemble** — an independent judge pass flags contradictions and unsupported
   claims, then a deterministic roll-up produces the attributed report plus a reviewer
   sidecar of provenance, inferences, and open questions.

A **review / answer loop** closes the cycle: a reviewer signs off the open questions and
`tlddr` re-runs only the affected nodes or sections.

The deterministic steps are `tlddr` CLI commands. The model-driven stages (Understand,
Draft, Verify, Review) are run by an agent following the procedures in `skills/`, so every
stage is separately runnable and inspectable.

## Install

Requires Python 3.11+. Managed with [uv](https://docs.astral.sh/uv/):

```bash
uv sync                # create .venv and install tlddr + dependencies
uv sync --extra dev    # include dev extras (pytest)
```

## Usage

Every command derives its paths from a single `--output` base directory (or the
`TLDDR_OUTPUT` environment variable), so a run's work, vault, and report stay bundled and a
second run never clobbers the first:

```bash
export TLDDR_OUTPUT=myrun                  # work/, vault/, report/ nest under ./myrun

uv run tlddr extract --source <docs-dir>
uv run tlddr --help                        # full command list
```

The model-driven stages are driven by the matching skill in `skills/` (`understand`,
`generate-sections`, `draft`, `draft-verify`, `review`), each of which documents the
command sequence for that stage.

## Output

A completed run produces, under your `--output` base:

- `report/report.md` — the attributed draft, claims cited to source page.
- `report/report_comments.md` — reviewer sidecar: provenance, inferences, no-evidence
  gaps, and the open questions to resolve.
- `vault/` — the linked, triaged understand vault (`_index.md`, `_triage.md`).
- `work/` — the claim, verdict, and question stores.

## License

MIT — see [LICENSE](LICENSE).
