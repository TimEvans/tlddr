# Extraction Reconnaissance Findings (2026-06-28)

Proving step 1 of the tl-ddr POC. Ran `tlddr extract` over the 20-file test corpus
(`docs/test-reports/Engineering reports test/`). The generated artifacts live in `.tlddr/`
(gitignored): `extracted/*.json` (20 records), `extraction-report.md`, `thumbnails/`.

## Verdict: the signal is there

Every one of the 20 documents is identifiable from its extracted form alone. Extraction
completed in ~63s with no crashes. This was the make-or-break question for the whole
pipeline, and it passes.

## Routing outcome (signal_type)

- 16 born_digital_report, 1 spreadsheet, 2 geospatial (the KMZs), 1 mixed.
- `R972.pdf` (previously unknown) is identified cleanly as a University of Sydney civil
  engineering research report, "Fracture Investigation of Welded Cruciform Connections"
  (R972, Feb 2023) - the one genuinely engineering/technical document in the pile, and its
  title block extracted perfectly.
- `draft-2026-integrated-system-plan` -> mixed: page 1 (the full-bleed cover) is the only
  image-only page in the entire corpus. It was correctly isolated, flagged
  "would route to vision", and rasterised to `thumbnails/draft-2026-integrated-system-plan-p1.png`.
  Pages 2+ extracted as clean text.
- Both KMZs -> geospatial, identity only: name + placemark count (e.g. "AEMO: 2025
  Indicative REZ boundaries. 44 placemarks/boundaries. Geometry not interpreted."). The
  de-scoping insight works as intended.

## What worked well

- **Honesty channel is real.** The messy ISP workbook produced 71 warnings naming every
  merged-cell sheet and every 200-row truncation. The docx templates surfaced mammoth
  conversion messages (embedded images, unrecognised styles) as warnings rather than
  dropping them.
- **Identity-only de-scoping** (KMZ, image pages) behaves exactly as designed - no geometry,
  no CAD, no GIS comprehension, just existence + identity + thumbnail.
- **docx -> markdown** is clean and immediately recognisable (field labels, headings).
- **Text-layer probe** correctly separated the single image cover page from text body in a
  115-page PDF.

## Weak spots / notes for the Understand plan

- **Spreadsheet dump is noisy and capped.** The pipe-delimited cell dump carries many empty
  `| | |` runs from merged/sparse cells, and data sheets are truncated at 200 rows. Fine for
  reconnaissance and identity, but when a report section actually depends on the workbook,
  Understand will likely want smarter per-sheet table/units detection (or a higher/with-purpose
  row cap) rather than the raw dump.
- **openpyxl emits a `UserWarning` to stderr** on the real workbook ("Data Validation
  extension is not supported and will be removed"). Harmless and library-internal, but it
  means the real run's stderr is not perfectly pristine (the test suite uses clean fixtures
  so it never appears there). Consider capturing/suppressing openpyxl warnings in a later pass.
- **docx pages = 0.** Expected (docx has no fixed pagination), but it means page-level
  provenance for Word docs will need a different anchor than page number (heading/section
  offset) when we wire citations in Draft.

## Corpus limitation (confirms the design-doc caveat)

This corpus is thematically related public energy/sustainability material, not a single
client's adversarial document set. Only R972 is a true engineering report; there are no
spec/as-built pairs, no drawings, and exactly one image page total. So the headline
cross-document finding ("spec says X, drawing shows Y, nothing reconciles them") will be
thin on this set - the `contradicts`/`supersedes` edges have little to bite on here. A
genuinely-conflicting document pair would exercise that path far better than more reports.

## Implications for the next plan (Understand)

- The vision path's first real job is tiny and concrete: describe the single ISP cover
  thumbnail. Good, low-risk first use of the model seam.
- Spreadsheet comprehension is the main extraction follow-up if/when a section leans on the
  workbook.
- docx embedded-image warnings are the hook for future image extraction from Word documents.

## Fidelity audit (post-merge) and known limitations

A follow-up audit compared the *full* extracted content (not the report excerpt) against
ground truth: PDF pages rendered and read directly, docx cross-checked with python-docx.
The original "signal is there" claim held for document *identity* but overstated *content
completeness*. Findings, by format:

- **PDF (born-digital prose): high fidelity (verified).** Rendered page 10 of the
  cost-benefit appendix matched its extracted text exactly - prose, bullets, footnotes,
  order. Density across the 13 PDFs is healthy (~1,500-3,100 chars per text page).
- **KMZ: correct by design.** Identity only.

### Fixed (quick wins)

- **docx image bloat - FIXED.** mammoth was inlining embedded images as base64 data-URIs;
  the business-case template was 96% base64 (583k of 607k chars), brolga was 3.7M chars
  mostly base64. Images are now dropped and counted as provenance
  ("N embedded image(s) present, not extracted (identity only)"). Real effect:
  business-case 607k->23.6k, brolga 3.7M->47k, species 460k->21.6k.
- **report excerpt - FIXED.** The 800-char excerpt made every doc look incomplete; raised
  to 4,000 with an explicit truncation notice pointing at the full per-doc JSON.

### Fixed (follow-up, after the audit)

- **docx table content - FIXED.** mammoth was dropping table cells (business-case template:
  196/251 cells = 78% coverage). Replaced mammoth with a python-docx in-order body walk that
  renders paragraphs and tables in true document order, tables as markdown tables. Coverage
  is now 251/251 (100%); mammoth dropped as a dependency. (The earlier "Stakeholder absent"
  note was a false probe - the real text is lowercase "stakeholders" and was always present.)

### Deferred - known limitations (revisit when a drafted section needs the content)

- **xlsx dump is bloated and truncated.** The ISP workbook extracted to ~19 MB of text,
  mostly empty-cell pipe padding, and each sheet is capped at 200 rows (real data loss on
  large sheets). Needs smarter per-sheet table/units detection and a purpose-driven row
  policy. **Not yet done.**
- **PDF table / multi-column pages unverified.** Only a prose page was visually checked;
  pymupdf raw text can mis-order multi-column layouts or flatten tables. Spot-check pages
  with tables (e.g. in the cost-benefit appendix) before relying on PDF table data.
