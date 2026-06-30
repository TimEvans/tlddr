# HTML extractor — design spec

**Date:** 2026-07-01
**Status:** approved (brainstorm)
**Slice:** Direction B prerequisite — build the HTML extractor before running any SEC filing through the pipeline.

## Problem

The extraction router handles only `.pdf`/`.docx`/`.xlsx`/`.kmz`. The new SEC-filing corpora (Chevron 10-K, CONSOL S-4, Microsoft 10-K) are HTML-native: the Chevron folder is 159 `.htm` + 2 `.html` + 24 `.jpg` + XBRL sidecars. Without an HTML extractor, `extract` routes every `.htm` to `UNKNOWN`. The main document `cvx-20251231.htm` (6 MB) is a Workiva inline-XBRL (iXBRL) 10-K: an XHTML tree with the financial facts wrapped in `ix:*` tags, a hidden `ix:header` metadata block, and 125 `page-break-after` CSS markers carrying the filing's own pagination.

This slice adds `tlddr/extract/html.py` (and supporting changes) so `.htm`/`.html` files extract to the same faithful `ExtractedDoc` the rest of the pipeline reads. It is its own brainstorm -> plan -> TDD build, branched off `main`, before any understand/draft over a filing.

## Scope

In scope: a faithful HTML -> text + structure + page provenance extractor, wired into the router; a shared table-rendering helper; one new `ExtractMethod`; a documented source-walk skip predicate for SEC machine-generated boilerplate.

Out of scope (deferred, unchanged): the vision path for the 24 `.jpg` exhibits (image-only, no text layer — stays `UNKNOWN`/flagged); XBRL *fact* extraction (we capture readable text + tables, not structured XBRL contexts/units); heading inference from visual styling.

## Decisions (issue -> options x criteria -> recommendation)

### D1 — Parser foundation: BeautifulSoup on an lxml backend

Research confirms the settled best practice for iXBRL-HTML -> text is BeautifulSoup with lxml as the backend (the foundation under `ixbrlparse`/`py-xbrl`). Dedicated XBRL libraries extract structured *facts* and are the wrong tool here — our job is faithful text + structure + provenance. `lxml` is already installed (transitively); `beautifulsoup4` is the one lightweight, pure-Python addition, and its traversal API reads far cleaner than raw lxml tree-walking (readability is a hard global preference). Runner-up was `lxml.html` directly (zero new declared dep); rejected stdlib `html.parser` (hand-rolled, less robust on a 6 MB Workiva file).

**Chosen:** add `beautifulsoup4`, parse with the lxml backend.

### D2 — Page provenance: synthesize from `page-break-after`

The grounding contract is page-numbered (`Citation.page: int`; `--- page N ---` markers read by `draft/pages.py:citable_pages`), and the proving run established the invariant **emit page markers iff `pages[]` is populated**. The main 10-K carries real pagination via 125 `page-break-after` markers. Synthesizing page numbers from them makes a citation resolve to the filing's actual page — strong DD provenance and consistent with the PDF per-page model. The alternative (whole doc = one page, like DOCX `pages=[]`) is trivial but makes every claim cite "page 1" of a 6 MB document — weak provenance. Section-anchor provenance is off the table: `Citation.page` is an `int` and changing it ripples through the whole pipeline.

**Chosen:** walk the body in document order; close a numbered page each time an element carries `page-break-after`/`break-after` with a value other than `avoid`/`auto`. Emit `--- page N ---` markers + one `PageProvenance` per synthesized page (new `ExtractMethod.HTML_TEXT`). When a file has no break markers, fall back to a single page 1 holding the whole content.

### D3 — Structure fidelity: faithful blocks + markdown tables, no heading inference

iXBRL handling: drop `<script>`/`<style>` and the hidden `ix:header`/`display:none` metadata block; `unwrap()` inline `ix:*` tags so the visible figures inside them survive in the text. HTML 10-Ks almost never use semantic `<h1>`-`<h6>` (headings are styled `<div>`/`<font>`), so heading inference is fragile guesswork and is omitted (YAGNI). Tables carry a 10-K's substance, so each `<table>` renders to a markdown table inline at its document position. This mirrors the proven DOCX extractor philosophy (faithful prose + markdown tables in document order). A raw `get_text()` dump was rejected because it destroys table structure.

**Chosen:** strip script/style/hidden `ix:header`, unwrap inline `ix:` tags, emit block-level text with blank-line separation, render every `<table>` to markdown via a shared helper. No heading inference.

### D4 — File scope: documented skip predicate in the source walk

The Chevron folder is 197 files but only ~25 are content. `R1.htm`-`R133.htm` (133 files) are the SEC viewer's re-render of XBRL facts already inline in the main 10-K — exact financial-statement duplicates; `*-index.html`, `*-index-headers.html`, `FilingSummary.xml` are filing-manifest pages. Feeding all 133 R-fragments would create duplicate-table nodes that swamp understand/draft and make the same figure citable from two sources, undermining the grounding posture. The skip predicate lives in `run_extract`'s walk (the layer that decides what to feed); `html.py` stays pure (extracts any `.htm` faithfully). This is right-sized to a real, observed failure mode — not over-armoring. Making `html.py` itself detect R-fragments was rejected as coupling scoping into the extractor.

**Chosen:** a documented `_is_sec_boilerplate(path)` predicate in `run_extract` skipping `R\d+\.htm`, `*-index.html`, `*-index-headers.html`, `FilingSummary.xml`, the XBRL linkbase sidecars (`*_cal.xml`/`*_def.xml`/`*_lab.xml`/`*_pre.xml`), `.xsd`, and the xbrl `.zip`.

Consequence (folds in the would-be signal-type decision): everything `html.py` actually extracts is prose+tables, so `signal_type` is uniformly `BORN_DIGITAL_REPORT` (`UNKNOWN` only if no text at all) — no separate signal-type decision needed.

## Components and contracts

- **`tlddr/extract/html.py`** — `extract(path: Path, ctx: ExtractContext) -> ExtractedDoc`.
  - Parse `path.read_bytes()` with `BeautifulSoup(data, "lxml")` (let lxml detect encoding).
  - Decompose `<script>`, `<style>`, and the hidden iXBRL header (`ix:header`); `unwrap()` every tag whose name starts with `ix:`.
  - Walk the body in document order producing ordered segments (block text runs and rendered tables), tracking `page-break-after` boundaries.
  - Build `content` as `\n\n`.join of `--- page N ---\n<page text>` blocks (mirrors `pdf.py`).
  - `pages` = one `PageProvenance(page=N, method=ExtractMethod.HTML_TEXT, has_text_layer=True, char_count=len(page_text))` per synthesized page.
  - `raw_title` = `<title>` text if present else `path.stem`.
  - `signal_type` = `BORN_DIGITAL_REPORT` if any text, else `UNKNOWN`.
  - `warnings`: count of embedded `<img>` (identity only, vision deferred), like DOCX; an empty-body note when `UNKNOWN`.
  - `extractor` = `"html"`. `id`/`source_sha256` via the existing `doc_id`/`sha256_file`.
  - Defensive: empty/garbage body yields `UNKNOWN` + warning, never raises.

- **`tlddr/extract/tables.py`** — shared `clean_cell(text) -> str` and `table_markdown(rows: list[list[str]]) -> str`, lifted verbatim from `docx.py`. `docx.py` refactored to import them; HTML uses them on `<table>` rows (`[[clean_cell(td.get_text()) for td in tr cells] for tr in rows]`). Existing DOCX tests are the regression gate.

- **`tlddr/models.py`** — add `ExtractMethod.HTML_TEXT = "html_text"`.

- **`tlddr/extract/router.py`** — `EXTRACTORS[".htm"] = EXTRACTORS[".html"] = _html.extract`.

- **`tlddr/cli.py`** — `run_extract` applies `_is_sec_boilerplate(path)` in the walk; skipped files are not extracted (optionally logged). Predicate is documented with why each pattern is boilerplate.

- **`pyproject.toml`** — add `beautifulsoup4>=4.12`, `lxml>=5.0` to `dependencies`.

## Page synthesis semantics (precise)

- A "page boundary" is an element whose inline `style` contains `page-break-after` or `break-after` with a value that is not `avoid` or `auto` (i.e. `always`/`page`/`left`/`right`/`recto`/`verso`).
- Text/tables accumulate into the current page; on hitting a boundary element, that element's own content is included in the current page, then the page is closed and a new page begins.
- Page numbers are 1-based and contiguous. A trailing non-empty buffer after the last boundary becomes the final page.
- Zero boundaries -> one page (page 1) containing all content.
- Empty pages (a boundary with no accumulated text) are not emitted as numbered pages.

## Testing (TDD, synthetic fixtures)

Unit tests use small inline HTML strings (the 6 MB filing is gitignored, so tests never depend on it):

1. iXBRL: hidden `ix:header` dropped; `ix:nonNumeric`/`ix:nonFraction` unwrapped (inner value retained in text).
2. Page synthesis: 2 `page-break-after` boundaries -> 3 pages; correct `--- page N ---` markers; `pages` length and per-page `char_count`.
3. No boundaries -> single page 1 = whole content; `pages` length 1.
4. `page-break-after:avoid` does NOT split.
5. Table -> markdown table via shared helper; pipes escaped; newlines collapsed.
6. Block separation: adjacent `<div>`/`<p>` blocks do not run together (blank-line separated).
7. `raw_title` from `<title>`; fallback to stem when absent.
8. `signal_type` `BORN_DIGITAL_REPORT` with text; `UNKNOWN` + warning on empty body.
9. Router: `.htm` and `.html` dispatch to `html.extract`.
10. `_is_sec_boilerplate`: matches `R12.htm`, `*-index.html`, `*-index-headers.html`, `FilingSummary.xml`, `cvx-20251231_cal.xml`; does NOT match `cvx-20251231.htm` or `a12312025ex19.htm`.
11. DOCX regression: existing DOCX tests still pass after the shared `tables.py` refactor.

Real-file validation (the actual Chevron 10-K) happens in the downstream proving run, not unit tests.

## Error handling

`html.py` never raises on malformed input — it degrades to `UNKNOWN` with a warning. `run_extract`'s existing per-file try/except remains the backstop for unexpected exceptions (emits an `error` doc, continues the walk).

## Out of scope / deferred (unchanged)

Vision for `.jpg` exhibits; XBRL fact extraction; heading inference; the other filings (CONSOL/Microsoft) reuse this extractor as-is.
