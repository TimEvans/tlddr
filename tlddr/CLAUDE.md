# tlddr - Module Index

**Last Updated:** 2026-07-03

Top-level package for tl-ddr — a **template-driven Due Diligence report generator**, i.e. a grounded/attributed report-generation system built on agentic RAG (the due-diligence report is one application; nothing here is specific to it). Holds the shared data contracts, id helpers, and the CLI. Stage code lives in `extract/`, `understand/`, and `draft/` (each has its own index). Extract and Understand are both merged and proven; Draft is in progress.

## Files Overview

### models.py
**Purpose:** All shared pydantic contracts. The `ExtractedDoc` (from extraction), `Node` (from understanding), and `DraftClaim` (from drafting) are the three central records.
**Key Classes/Types:**
- `SignalType(str, Enum)` - routing signal (born_digital_report, slide_deck, table_page, drawing, spreadsheet, image, geospatial, mixed, unknown)
- `ExtractMethod(str, Enum)` - per-page extraction method (pymupdf_text, openpyxl_xlsx, kmz_identity, vision, ocr)
- `PageProvenance` - page-level provenance (page, method, has_text_layer, char_count, thumbnail)
- `ExtractedDoc` - one per source file: full content + pages[] + warnings + identity (the content store record)
- `Confidence(str, Enum)` - HIGH/MEDIUM/LOW; `Triage(str, Enum)` - GREEN/AMBER/RED
- `RelationType(str, Enum)` - contradicts/supersedes/corroborates/references/same_subject/input_to
- `Edge` - target, relation, rationale (cross-doc edge)
- `Section` - id, title, parent, guidance (one entry of the user-provided section-spec / sections.json; guidance is drafting instruction)
- `SupportLevel(str, Enum)` - fully_supported/partially_supported/unsupported (drafter two-axis judgment)
- `EvidenceRelation(str, Enum)` - quoted/inferred (claim sourcing mode)
- `Citation` - node_id, page, source_confidence (one source of a DraftClaim)
- `DraftClaim` - section_id, text, sources[], support_level, evidence_relation (one atomic claim in the draft)
- `Disposition(str, Enum)` - revise/accept (answer-loop sign-off: revise routes to a re-pass, accept discloses as a caveat)
- `Question` - quarantine item (id, raised_by, node_id, section_id, question, blocks, blocking, answer, disposition, resolved)
- `Node` - understanding overlay + `extracted_id` pointer (NO content clone); carries report_sections + the two confidences + triage + related edges
**Dependencies:** enum, pydantic

### answer.py
**Purpose:** Answer-loop core (D6) — validates Reviewer answers against the question store and builds the deduped re-pass worklist. No model calls.
**Key Functions:**
- `_normalize(text) -> str` - fold case + collapse whitespace so trivial rephrasings compare equal
- `question_identity(q) -> tuple[str, str, str]` - stable `(raised_by, target, normalized question)` identity used for dedup/suppression
- `build_worklist(questions) -> dict` - groups revise-disposition questions by re-pass target (`sections`/`nodes`), joining guidance and dedup'd `from` ids
- `ingest_answers(records, questions) -> (list[Question], dict, list[str])` - validates answer records `{id, disposition, answer}` against the known question set; sets `answer`/`disposition`/`resolved=True`/`blocking=False` on matches; returns updated questions, the worklist built from this batch's revise targets, and dropped-record messages
- `parse_triage_answers(triage_md) -> (list[dict], list[str])` - parses filled `> answer:` slots in a rendered `_triage.md` (with a leading `[revise]`/`[accept]` tag) into answer records; filled-but-untagged slots are reported as skipped (machine-trust)
**Dependencies:** re, tlddr.models (Question, Disposition)

### ids.py
**Purpose:** Deterministic identity helpers.
**Key Functions:**
- `doc_id(path) -> str` - stable slug from filename stem
- `sha256_file(path) -> str` - hex digest of file bytes (chunked)

### cli.py
**Purpose:** The `tlddr` CLI. Extract-side + understand-side + draft-side commands; deterministic glue only (no model calls).
**Key Functions:**
- `run_extract(source, out) -> list[ExtractedDoc]` - walk source, route each file, write JSON + extraction-report.md
- `understand_slice(extracted_dir, node_id) -> str` - bounded slice for one doc (agent reads this)
- `understand_sections(sections_path) -> list[Section]` - load, validate, and print the canonical section structure (children indented)
- `understand_commit(enrichment_path, extracted_dir, out_dir, sections_path=None) -> Node` - validate agent enrichment (edges + section tags) into a node; idempotent per-node questions
- `understand_render(work_dir, vault_dir, sections_path=None)` - write vault/<id>.md + _index.md + _triage.md (incl. section coverage + isolated docs)
- `draft_read(extracted_dir, node_id, pages=None) -> str` - bounded read (whole doc or requested pages, or page list)
- `draft_commit(claims_path, extracted_dir, work_dir, sections_path=None) -> list[DraftClaim]` - validate agent claims into a claims queue (cites resolved + confidence looked up; zero-citation -> finding)
- `draft_verify_commit(verdicts_path, work_dir) -> None` - ingest C-lite judge verdicts; downgrades/contradictions -> verify questions; suppresses verdicts matching already-resolved question identities so a re-verify does not re-raise a settled question
- `_format_worklist(worklist) -> str` - human-readable "RE-PASS WORKLIST" printout (section/node re-passes with their guidance and source question ids)
- `_bump_repass_log(work_dir, worklist) -> None` - increments each re-pass target's cycle count in `work/repass_log.json` (answer-loop convergence tracking)
- `answer_commit(answers_path, triage_path, work_dir, sections_path=None, vault_dir=None) -> None` - ingest reviewer answer records (from `--answers` JSON or parsed from a filled `--triage` _triage.md), resolve matching questions, write `work/worklist.json`, bump the repass log, print the worklist, and re-render the vault triage
- `draft_eval(work_dir, sections_path) -> None` - print tier-B groundedness readout
- `assemble(work_dir, out_dir, sections_path) -> None` - render report.md (clean) + report_comments.md (sidecar: provenance, warnings, inferences, open questions); warns when a re-pass target has cycled 3+ times through the answer loop
- `main(argv)` - argparse entry; subcommands: extract, understand-slice, sections, understand-commit, understand-render, draft-read, draft-commit, draft-verify-commit, answer-commit, draft-eval, assemble
**Key Exports:** console script `tlddr` (pyproject `[project.scripts]`)
**Dependencies:** argparse, tlddr.extract, tlddr.understand, tlddr.draft, tlddr.answer, tlddr.models

### __init__.py
**Purpose:** Empty package marker.

---
*This file is auto-generated by `/sub-init`. Update with `/sub-init update`.*
