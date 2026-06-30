# tl-ddr — Design

**Status:** approved design, pre-implementation
**Date:** 2026-06-28
**Type:** proof-of-concept

`tl-ddr` is a **template-driven Due Diligence report generator**. It reads a pile of a
client's source documents and drafts a structured report against a template, so the
engineer's job shifts from "read everything and write from scratch" to "review, correct,
sign off." Crucially, it **flags what it is unsure about instead of guessing** — for due
diligence, an honest gap is worth more than confident coverage.

In industry terms it is a **grounded, attributed report-generation system built on agentic
RAG** (retrieval-augmented generation): claim-level attribution (AIS/ALCE), agentic
retrieval (Self-RAG), faithfulness evaluation (RAGAS), and abstention. The due-diligence
report is one application — nothing in the machinery is specific to it; the same pipeline
grounds any template-driven report in a source corpus with page-level citations. (The name
is retained from the project's origin; it is no longer scoped to *technical* due diligence.)

This is a POC. The bar is: a senior engineer looks at the output and says *"this genuinely
saved me time, and I trust how it got there."*

## Success criteria

Pointed at one worked example (a finished report + the source documents it came from), the
POC works if it can:

1. Produce a coherent draft of a meaningful subset of the report's sections.
2. Cite which source document(s) each part of the draft came from (page-level).
3. Honestly surface what it could not understand or had no evidence for, rather than
   papering over the gaps.

Point 3 is not a consolation prize. A tool that confidently hallucinates coverage is a
liability; one that says "here are the things you need to look at yourself" is doing due
diligence.

## Why this is harder than "summarise some PDFs"

- **Inputs are heterogeneous and messy.** Word, Excel, and PDFs — where "PDF" spans
  born-digital reports, slide decks, table pages, and engineering drawings, sometimes
  mixed in one file. Documents are routed by their **signal type, not their file
  extension**: the driving question is "where does the meaning live here — in the text
  layer or in the pixels?"
- **Findings are cross-document by nature.** A real finding is rarely "document X says Y."
  It is "the spec says X, the as-built shows Y, and nothing reconciles them." The
  **relationships between documents are the value**, and they are built deliberately — not
  rediscovered at the last second.

A de-scoping insight that shapes the design: for drawings (and geospatial data), the
*existence and identity* usually matters more than interpreting the geometry. "A P&ID rev 3
for the cooling system exists" is often the point; reading every valve off it is not.

---

## Architecture

A four-stage pipeline over a shared vault, with **quarantine as a cross-cutting channel**
that two of the stages emit into. Each stage boundary is a **seam**, defined by contract,
not implementation, so external dependencies can be swapped with no downstream change.

```
                  +-------------- quarantine queue (one surface) --------------+
                  |                                                            |
  source docs     v                                                            |
  -----------> EXTRACT ---nodes---> UNDERSTAND ---graph---> DRAFT ---> ASSEMBLE ---> report
               [extract seam]        (model)               (model)    [assembly seam]
                    |                    |                     |
                    +------ VAULT SEAM: TurboVault over an Obsidian vault ------+
```

The deterministic/model boundary *is* the seam boundary: Extract and Assemble are script;
Understand and Draft are model. The one place they interleave — the visual path inside
extraction — composes the model seam internally rather than getting its own seam.

### The four seams (contracts, not implementations)

| Seam | Contract (the fixed point) | POC implementation | Swap target |
|------|----------------------------|--------------------|-------------|
| **Extraction** | `extract(file) -> Node` — every extractor emits the *same* node shape; nothing downstream knows which tool read the file | `pymupdf` / `mammoth` / `openpyxl` / vision-router, chosen per *signal type* | Azure AI Document Intelligence |
| **Model** | `complete(messages, [images]) -> text/structured` — one interface for all language + vision calls | Anthropic (text + vision) | isolated in-house Copilot endpoint |
| **Vault** | node write / link / graph-ops / render over the vault | **TurboVault MCP** over an Obsidian vault, with a pydantic-validated write path in front | (already the intended production tool; behind a seam so it stays swappable) |
| **Assembly** | `assemble(sections, provenance) -> document` | markdown concatenation | house-style docx / PDF |

### Vision/OCR is not its own seam

The visual path satisfies the same `extract -> Node` contract; it just *composes* the model
seam internally to describe an image-only page. OCR (`pytesseract`) is one more extractor
behind the extraction seam, added only when a document demands it.

### The vault: TurboVault over a generated Obsidian vault

The intermediate representation is a real Obsidian vault, managed by **TurboVault** (a local
Rust MCP server, `~/.cargo/bin/turbovault`, v1.2.6, 44 tools). It is registered for this
project in `.mcp.json` and is vault-agnostic (vaults are created/registered at runtime via
its `create_vault` / `add_vault` tools).

A thin **pydantic-validated write path** sits in front of TurboVault: pydantic is the schema
+ validator on the write path, it serialises to Obsidian **frontmatter**, and TurboVault's
`query_metadata` then makes that frontmatter a queryable store. The same node shape is
mirrored by a TurboVault template.

Because we generate the entire vault from a closed corpus end-to-end, **link rot is not a
real risk** — there is no human editing, renaming, or external reference. We do *not* build
transactional writes or treat broken-links as a gate. The one failure mode that survives in
a vault we fully control is the model proposing an **edge to a document that is not in the
corpus** (a hallucinated relationship). That is prevented by a one-line check at write time:
`Edge.target` must be a member of the known node-id set. If it fails, drop the edge.

TurboVault's graph-health tools are therefore repurposed from *integrity defense* to
**coverage signal for triage**:

- `get_isolated_clusters` — docs that relate to nothing found (a coverage gap, maybe a finding)
- `get_dead_end_notes`, `get_centrality_ranking` — which docs are load-bearing
- `get_broken_links`, `full_health_analysis` — a once-at-the-end sanity readout, not a gate

Its relationship tools (`suggest_links`, `recommend_related`, `get_related_notes`,
`get_link_strength`) seed *structural/similarity* link candidates cheaply; the model adds
the *semantic* links similarity cannot see — especially `contradicts` / `supersedes`.

---

## Data contracts

Four contracts. The **Node** is the centre of gravity; the others key off it. Pydantic is
the validation gate; the node serialises to Obsidian frontmatter, and the markdown body is
the human / TurboVault projection.

### 1. Node — one per source document

```python
class PageProvenance(BaseModel):
    page: int
    has_text_layer: bool            # drove text-path vs visual-path routing
    method: ExtractMethod           # pymupdf_text | pdfplumber_table | vision | ocr | ...
    thumbnail: Path | None = None   # for drawings/visual pages: existence + identity

class Edge(BaseModel):
    target: NodeId                  # MUST be a member of the known node-id set (validated)
    relation: RelationType          # contradicts | supersedes | corroborates |
                                    #   references | same_subject | input_to
    rationale: str                  # why the model drew this link (one line)
    confidence: float

class Node(BaseModel):
    id: NodeId                              # stable slug, deterministic from path
    source_path: Path
    source_sha256: str                      # change detection + provenance
    signal_type: SignalType                 # born_digital_report | slide_deck | table_page |
                                            #   drawing | spreadsheet | image | geospatial | mixed
    title: str
    doc_type: str
    description: str                        # human-readable: what it is + contains
    pages: list[PageProvenance]
    report_sections: list[SectionId]        # tagged in Understand against the active profile
    related: list[Edge]                     # model-proposed, script-validated edges
    confidence_extraction: Confidence       # "did I read it right?"   (legibility)
    confidence_interpretation: Confidence   # "do I understand what it means?" (interpretation)
    triage: Triage                          # green|amber|red — DERIVED, never hand-set
    open_questions: list[QuestionId] = []   # refs into the quarantine queue
    extractor: str                          # which extractor/seam produced this
```

Three deliberate choices:

- **Two confidence signals, traffic-light derived.** `triage` is computed from the two
  confidences plus "any open questions?" — never hand-set. A scanned drawing can be
  `extraction=high, interpretation=low` -> amber with a specific question. That is the
  "perfectly legible yet ambiguous" case, encoded.
- **The machine-trusted link guarantee, mechanically.** The model never writes a raw
  `[[wikilink]]` that anything trusts. It proposes an `Edge` (target node-id + type +
  rationale). A **script** validates `target` is in the node set, then writes *both* the
  frontmatter `related:` entry *and* the body `[[Title]]` wikilink from that one validated
  edge — so they cannot diverge. `relation: contradicts` is the edge type that *is* a
  due-diligence finding.
- **Document = unit of identity, page = unit of provenance.** One node per doc; `pages[]`
  carries per-page method + text-layer flag + optional thumbnail. Claims cite `(node_id, page)`.

### 2. Section Spec — the spine (a runtime "report profile")

The set of sections is a **runtime artifact, not code**: a report profile file the run is
pointed at (`profiles/tdd.yaml`, `profiles/business-case.yaml`, ...). Default ships derived
from the template; a new project supplies a different profile. Selected at runtime
(`--profile`), and a subset can be drafted (`--sections`).

```python
class SectionSpec(BaseModel):
    id: SectionId
    title: str
    purpose: str                    # what this section is for (junior-engineer guidance)
    expected_inputs: list[str]      # signal types / doc kinds that should feed it
    depth: Depth                    # one-liner | paragraph | full-treatment
    example: str | None             # a gold example to ground per-section drafting
```

**Report scope is known at the start of a run, and coupling to it is the point.** Understand
tags `report_sections` against the active profile so it can surface *"section X has no
evidence behind it"* at triage time — early, where it is most useful. The only genuinely
profile-agnostic thing is the **doc-to-doc edge set**: if the same corpus is ever re-run
under a different profile, those edges are reusable and only the section tags recompute. That
is a minor efficiency note, not a reason to defer the coupling.

### 3. Quarantine Item — emitted by both Understand and Draft

```python
class Question(BaseModel):
    id: QuestionId
    raised_by: Stage                # understand | draft
    node_id: NodeId | None          # None for "section has no evidence" findings
    section_id: SectionId | None
    question: str                   # self-contained: answerable without reopening the doc
    blocks: list[SectionId]         # what stays blocked until answered
    answer: str | None = None       # human fills this; presence triggers a re-pass
```

### 4. Draft fragment — provenance carried inline

```python
class DraftClaim(BaseModel):
    text: str
    sources: list[Citation]         # (node_id, page) — no orphan assertions
```

**Relation vocabulary (starting set):**
`contradicts | supersedes | corroborates | references | same_subject | input_to`.

---

## Stage behaviour and the script/model line

**EXTRACT — script, with one model-composed sub-path.**
Router classifies each file by signal type, then dispatches:

- Born-digital PDF / docx -> text + structure (`pymupdf`, `mammoth`); per-page text-layer
  probe decides text-path vs visual-path.
- Table-heavy page -> `pdfplumber` (add `camelot` only if a real doc demands it).
- Spreadsheet -> `openpyxl` / `pandas`, tolerant of messy sheets (multi-table, headers not
  in row 1, merged cells, scattered units).
- Drawing / image-only page / KMZ -> **identity only**: title-block fields + a rasterised
  thumbnail; here the router calls the model seam (vision) to describe the page. No
  geometry, no CAD, no GIS comprehension.
- Output: a validated `Node` stub (minus cross-doc edges, which need other nodes to exist).

**UNDERSTAND — model proposes, script validates and writes.**

- Model reads each node's extracted content + a running index of the others -> writes
  `description`, `doc_type`, tags `report_sections` (against the active profile), assigns
  the two confidences, and proposes `Edge`s with rationale.
- TurboVault `suggest_links` / `recommend_related` seed structural/similarity candidates;
  the model adds semantic ones (especially `contradicts` / `supersedes`).
- Script validates each edge `target` is in the node set, derives `triage`, writes
  nodes + links via the vault seam, emits Understand-stage quarantine questions, and
  renders `_index.md` and `_triage.md`.
- Coverage readout (the repurposed TurboVault tools) flags isolated/dead-end docs.

**DRAFT — model, per section, script-orchestrated.**

- For each `SectionSpec`: gather nodes tagged to it, draft against `purpose` / `depth` /
  `example`, emit `DraftClaim`s with `(node_id, page)` citations.
- Two gaps become findings, not failures: a section with no inbound nodes -> a "no evidence"
  quarantine item; a section that comes back thin -> flagged for review.
- One section at a time: better grounding, visible gaps, per-section examples.

**ASSEMBLE — script, pure.**

- Deterministic roll-up of drafted sections + provenance into the output (plain markdown
  first; house-style docx/PDF is the swappable back end). Prove content first, make it
  pretty last.

The entire model surface is two stages (Understand, Draft) behind one model seam; everything
else is deterministic.

### Where the model seam physically sits (decision: A)

- **Vision calls inside `extract`** are unavoidably programmatic and go through a model-seam
  `LLMClient` (Anthropic now -> Copilot/Azure later = a config change).
- **Understand and Draft reasoning** is done by **the in-session Claude Code agent** (the
  skill reasons directly and emits the structured `Node` / `DraftClaim` shapes). The seam
  stays honest because the *handoff is the structured contract*; production lifts the
  reasoning into a Copilot-backed script emitting the same shapes. Chosen for fastest,
  most flexible, most demoable POC.

---

## Quarantine and the human loop

A cross-cutting channel and a headline feature, not an error path.

**One queue, two producers.** Both Understand and Draft emit `Question` items into one
surface:

- *Understand-stage:* "I can't read/disambiguate this" (`raised_by=understand`, has
  `node_id`).
- *Draft-stage:* "I read everything, but this section has no evidence" (`raised_by=draft`,
  has `section_id`, `node_id=None`) — itself a due-diligence finding.

**File-based interaction.** A generated `_triage.md` in the vault, grouped traffic-light:
red (blocks a section), amber (degrades confidence), green (FYI). Each item is
self-contained — written so it can be answered from the question alone, without reopening the
document — with an `> answer:` line filled inline. Reviewed in an editor or Obsidian; no
bespoke UI. TurboVault coverage tools feed the amber/green entries.

**Questions live only in `_triage.md`**, not rendered into the document notes themselves.
`_triage.md` is the single surface to both read and answer them, so resume parses one file.
A doc node's frontmatter still carries `open_questions: list[QuestionId]` as a machine-only
back-reference (used by `_index.md` and resume), but the question *text* is never projected
into the doc body.

**Resume consumes answers.** A re-pass reads `_triage.md`, matches answers back to
`Question.id`, and re-runs only the affected nodes/sections (`blocks` says what was held).
An answered Understand question re-runs that node's understanding (and anything downstream);
an answered Draft question re-drafts that section. Unanswered items stay quarantined and
surface in the final output as explicit "needs your attention," with the page reference.

**Triage stands alone.** Understand + the queue produce value with zero drafting ("point it
at a vault, get a triaged map of what's there, what relates to what, what's ambiguous"), so
understand-only is a first-class stop.

---

## CLI and skill surface (staged execution)

Two layers: **SKILL.md = procedure + judgment**; **scripts = deterministic muscle**,
presented as a `tlddr` CLI so every stage is separately runnable and inspectable.

| Command | Owner | Does | Staged run |
|---------|-------|------|------------|
| `tlddr extract --source <dir> --vault <dir>` | script | Route by signal type -> extracted node stubs (identity, content, page provenance, thumbnails). Visual path calls the model seam. | Proving step 1 |
| `tlddr understand --profile <p>` | model + script | Per node: describe, tag sections, set 2 confidences, propose edges. Script validates, writes vault, builds graph, renders `_index.md` / `_triage.md`. | understand-only stop |
| `tlddr triage status` | script | Print red/amber/green counts; review = read `_triage.md`. | review |
| `tlddr draft --sections <ids\|all> --profile <p>` | model + script | Gather nodes per section -> draft against purpose/depth/example -> `DraftClaim`s with `(node_id, page)`. Empty/thin section -> finding. | single-section draft |
| `tlddr resume` | script + model | Parse answered `_triage.md`, re-run only affected nodes/sections. | resume-after-quarantine |
| `tlddr assemble --profile <p> --out <f>` | script | Deterministic roll-up of section drafts + provenance -> markdown. | assemble |
| `tlddr status` | script | Where the pipeline is. | — |

`SKILL.md` is the conductor: it knows the stage order, drives Draft section-by-section,
decides when to quarantine vs proceed, and runs the human loop. The scripts own extraction,
edge-validation + vault writes (via the vault seam -> TurboVault), the triage render/parse,
and assembly.

---

## Build principles

- **Honesty over coverage.** A flagged gap beats a confident fabrication, every time. The
  posture is appropriately cautious — correct for due diligence and what reads as
  trustworthy.
- **Everything traceable.** Claims cite sources; sources have page-level provenance. No
  orphan assertions.
- **Cross-document relationships are the value.** Built deliberately, not deferred.
- **The template is the spine.** Sections are the unit of work throughout.
- **Swappable seams.** Every external dependency sits behind a contract so the
  Microsoft-native swaps (Azure DI, Copilot) are localized changes.
- **Demo the safety rails, don't hide them.** "I drafted 8 of 10 sections; here are 3 things
  I need you to confirm, with the page each refers to" beats a black box.

---

## First proving step

**Extraction reconnaissance** — look at the output and judge the signal, *not* build the
pipeline. Deliberately **no model calls yet**: confirm the text/structure signal before
spending on reasoning.

1. **Env:** project venv + minimal deps only — `pymupdf`, `mammoth`, `openpyxl` / `pandas`.
   KMZ needs nothing new (zipped XML -> stdlib `zipfile`). Hold `pdfplumber` / `camelot` /
   `pytesseract` until a specific document demands them.
2. **The extraction seam, for real:** the router + per-signal extractors, all emitting the
   same `Node` stub (identity, content, `pages[]` with text-layer flag + method, thumbnail
   path for visual pages). This contract is what everything keys off.
3. **Run over all 20 files and eyeball:** Can you tell what each doc is and what it is about
   from the extracted form alone? Per page, real text layer or pixels? Interrogate the
   awkward ones: the xlsx workbook (messy multi-sheet/merged cells), the two KMZ
   (identity-only: name + region), `R972.pdf` (unknown), and any image-only/slide-deck PDFs
   (flag as "would route to vision," do not process yet).
4. **Output:** a quick extraction report read against the source pile, so the gap tells us
   where to invest.

Then, in order: stand up understand + the traffic-light triage (eyeball the vault); draft
three or four sections spanning the difficulty range (one prose-synthesis, one table-driven,
one figure/drawing-leaning); then wire polished assembly last.

## Open dependencies and provisional items

- **No finished worked-example report yet.** The draft-vs-handwritten gap analysis — the
  core evaluation signal — cannot run until it is provided. Does not block steps 1–2; gates
  proving-step-3 evaluation. Until then the report profile is derived from
  `Business-Case-Template-v11.docx` as a stand-in (acknowledged not to be a true
  due-diligence report).
- **TurboVault activates on next session reload** (MCP cannot hot-load). Steps 1–2 do not
  need it live; the vault-write stage does.
- **The test corpus is thematic, not adversarial.** It is a grab-bag of public energy /
  sustainability reports with no spec-vs-as-built pair and no engineering drawings, so
  `contradicts` / `supersedes` edges will be sparse and the headline "spec says X, drawing
  shows Y" finding is under-demonstrated. One genuinely-conflicting document pair would do
  more for the story than ten more reports.

## Open questions deferred to implementation planning

- Exact `SignalType`, `ExtractMethod`, `Confidence`, `Triage`, and `Depth` enum members
  (settle against real extracted output from proving step 1).
- The `triage` derivation function (how the two confidences + open-questions map to
  red/amber/green).
- Node-id slug derivation and collision handling.
- The exact TurboVault tool sequence for the vault-write stage (settle once it is live).
