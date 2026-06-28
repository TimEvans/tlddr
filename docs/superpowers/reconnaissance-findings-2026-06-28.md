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
