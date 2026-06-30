# Draft Stage Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the Draft stage — turn the understood vault into a grounded report, section by section, with claim-level citations, a deterministic groundedness readout, an independent judge pass, and a deterministically-assembled published draft + reviewer sidecar.

**Architecture:** A new `tlddr/draft/` package mirroring `tlddr/understand/`: small focused deterministic modules (page-addressing, tiered read, claim validation, groundedness eval, verdict ingestion, assemble), driven by the host agent through new `tlddr` CLI subcommands and two `SKILL.md` procedures. The model drafts and judges; tested Python validates citations, derives confidence, aggregates groundedness, and renders. No new pip dependencies.

**Tech Stack:** Python 3.11+, pydantic, pyyaml (existing). Tests via `.venv/bin/pytest`.

## Global Constraints

- **Python floor:** `>=3.11` (pyproject). Use `X | None` unions, `list[...]` generics.
- **No new dependencies.** C-full (NLI ensemble) is deferred; this slice adds no pip deps.
- **No emojis** anywhere (code, comments, commits) — hard user rule.
- **Machine-trust at the seam:** the model never writes a citation, section tag, or support label the CLI hasn't validated against a known set. Unknown node-ids / out-of-range pages are dropped; a claim left with zero valid citations becomes a finding.
- **No content clone:** the `Node` is an overlay over the `ExtractedDoc` store; faithful content lives once in `.tlddr/extracted/<id>.json`. Draft reads source content from there.
- **Grounding guardrail:** citations resolve to `(node_id, page)` in the source store via `citable_pages`/`page_text`, never to overlay/description text.
- **Page-addressing (decision A):** `citable_pages(doc) = set(_page_index(doc).keys())`; page-less docs (docx) get the single synthetic page `1` = whole content.
- **Deterministic/model line:** model drafts + judges (via skills); tested Python validates + renders. Assemble is pure deterministic roll-up.
- **Confidence is looked up, never self-graded:** `Citation.source_confidence` is set by the script from the cited node's `confidence_interpretation`.
- **Git:** already on branch `draft-stage-design`; conventional commits; commit after each task.
- **Test command:** `.venv/bin/pytest`.

---

## File Structure

| File | Responsibility |
|---|---|
| `tlddr/models.py` (modify) | Add `SupportLevel`, `EvidenceRelation`, `Citation`, `DraftClaim`; add `guidance` to `Section`. |
| `tlddr/draft/__init__.py` (create) | Empty package marker. |
| `tlddr/draft/pages.py` (create) | Page-addressing: `_page_index`, `citable_pages`, `page_text`. |
| `tlddr/draft/read.py` (create) | Tiered read: `build_read` (whole if short, targeted pages, large-doc overview). |
| `tlddr/draft/claims.py` (create) | `validate_claims` — machine-trust validation of agent claims → valid claims + findings. |
| `tlddr/draft/eval.py` (create) | Tier-B groundedness: `groundedness_readout`, `no_evidence_sections`. |
| `tlddr/draft/verify.py` (create) | C-lite: `ingest_verdicts` → `raised_by=verify` questions on disagreement. |
| `tlddr/draft/assemble.py` (create) | `render_published`, `render_sidecar` (report_comments.md). |
| `tlddr/cli.py` (modify) | `draft-read`, `draft-commit`, `draft-verify-commit`, `draft-eval`, `assemble` subcommands. |
| `skills/generate-sections/SKILL.md` (modify) | Preserve each section's body content into `Section.guidance`. |
| `skills/draft/SKILL.md` (create) | Per-section drafting procedure. |
| `skills/draft-verify/SKILL.md` (create) | The C-lite independent judge procedure. |
| `tlddr/draft/CLAUDE.md` (create), `tlddr/CLAUDE.md` (modify) | Module index + CLI surface docs. |
| `tests/test_draft_*.py` (create) | One test file per module + CLI. |

---

### Task 1: Data contracts

**Files:**
- Modify: `tlddr/models.py` (after `Section`, line ~75; and `Section` itself)
- Test: `tests/test_draft_models.py`

**Interfaces:**
- Produces: `Section.guidance: str | None`; `SupportLevel` (`fully_supported`/`partially_supported`/`unsupported`); `EvidenceRelation` (`quoted`/`inferred`); `Citation(node_id: str, page: int, source_confidence: Confidence | None)`; `DraftClaim(section_id: str, text: str, sources: list[Citation], support_level: SupportLevel, evidence_relation: EvidenceRelation)`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_draft_models.py
from tlddr.models import (
    Section, SupportLevel, EvidenceRelation, Citation, DraftClaim, Confidence,
)


def test_section_guidance_defaults_none():
    assert Section(id="s1", title="Intro").guidance is None
    assert Section(id="s1", title="Intro", guidance="cover X").guidance == "cover X"


def test_draftclaim_round_trips_with_two_axes():
    claim = DraftClaim(
        section_id="s1",
        text="The plant has a 25-year design life.",
        sources=[Citation(node_id="r518", page=12, source_confidence=Confidence.HIGH)],
        support_level=SupportLevel.FULLY_SUPPORTED,
        evidence_relation=EvidenceRelation.QUOTED,
    )
    restored = DraftClaim.model_validate_json(claim.model_dump_json())
    assert restored.support_level is SupportLevel.FULLY_SUPPORTED
    assert restored.evidence_relation is EvidenceRelation.QUOTED
    assert restored.sources[0].page == 12
    assert restored.sources[0].source_confidence is Confidence.HIGH


def test_citation_source_confidence_optional():
    assert Citation(node_id="a", page=1).source_confidence is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_draft_models.py -v`
Expected: FAIL with `ImportError` (cannot import `SupportLevel` etc.)

- [ ] **Step 3: Write minimal implementation**

In `tlddr/models.py`, change `Section` to add `guidance`, and append the new types after `Section`:

```python
class Section(BaseModel):
    id: str
    title: str
    parent: str | None = None
    guidance: str | None = None


class SupportLevel(str, Enum):
    FULLY_SUPPORTED = "fully_supported"
    PARTIALLY_SUPPORTED = "partially_supported"
    UNSUPPORTED = "unsupported"


class EvidenceRelation(str, Enum):
    QUOTED = "quoted"
    INFERRED = "inferred"


class Citation(BaseModel):
    node_id: str
    page: int
    source_confidence: Confidence | None = None


class DraftClaim(BaseModel):
    section_id: str
    text: str
    sources: list[Citation] = Field(default_factory=list)
    support_level: SupportLevel
    evidence_relation: EvidenceRelation
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/test_draft_models.py -v`
Expected: PASS (3 tests). Also run `.venv/bin/pytest tests/test_sections.py tests/test_models.py -v` — Expected: PASS (Section's new optional field is backward-compatible).

- [ ] **Step 5: Commit**

```bash
git add tlddr/models.py tests/test_draft_models.py
git commit -m "feat(draft): add DraftClaim/Citation contracts and Section.guidance"
```

---

### Task 2: Page addressing

**Files:**
- Create: `tlddr/draft/__init__.py` (empty), `tlddr/draft/pages.py`
- Test: `tests/test_draft_pages.py`

**Interfaces:**
- Consumes: `ExtractedDoc` (Task 0/existing — `content`, `pages: list[PageProvenance]`).
- Produces: `citable_pages(doc: ExtractedDoc) -> set[int]`; `page_text(doc: ExtractedDoc, page: int) -> str | None`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_draft_pages.py
from tlddr.draft.pages import citable_pages, page_text
from tlddr.models import ExtractedDoc, PageProvenance, SignalType, ExtractMethod


def _pdf():
    return ExtractedDoc(
        id="p1", source_path="/x/p1.pdf", source_sha256="a",
        signal_type=SignalType.MIXED, raw_title="P1",
        content="--- page 1 ---\nalpha text\n\n--- page 3 ---\ngamma text",
        pages=[
            PageProvenance(page=1, method=ExtractMethod.PYMUPDF_TEXT, has_text_layer=True),
            PageProvenance(page=2, method=ExtractMethod.VISION, has_text_layer=False),
            PageProvenance(page=3, method=ExtractMethod.PYMUPDF_TEXT, has_text_layer=True),
        ],
        extractor="pdf",
    )


def _xlsx():
    return ExtractedDoc(
        id="x1", source_path="/x/x1.xlsx", source_sha256="a",
        signal_type=SignalType.SPREADSHEET, raw_title="X1",
        content="--- sheet: Costs ---\na | b\n\n--- sheet: Yield ---\nc | d",
        pages=[
            PageProvenance(page=1, method=ExtractMethod.OPENPYXL_XLSX, has_text_layer=True),
            PageProvenance(page=2, method=ExtractMethod.OPENPYXL_XLSX, has_text_layer=True),
        ],
        extractor="xlsx",
    )


def _docx():
    return ExtractedDoc(
        id="d1", source_path="/x/d1.docx", source_sha256="a",
        signal_type=SignalType.BORN_DIGITAL_REPORT, raw_title="D1",
        content="whole docx body, no page markers", pages=[], extractor="docx",
    )


def test_pdf_citable_pages_are_text_bearing_only():
    assert citable_pages(_pdf()) == {1, 3}            # page 2 is image-only, not citable
    assert page_text(_pdf(), 1) == "alpha text"
    assert page_text(_pdf(), 3) == "gamma text"
    assert page_text(_pdf(), 2) is None               # image-only
    assert page_text(_pdf(), 9) is None               # out of range


def test_xlsx_pages_are_sheet_ordinals():
    assert citable_pages(_xlsx()) == {1, 2}
    assert page_text(_xlsx(), 1) == "a | b"
    assert page_text(_xlsx(), 2) == "c | d"


def test_docx_has_single_synthetic_page():
    assert citable_pages(_docx()) == {1}
    assert page_text(_docx(), 1) == "whole docx body, no page markers"
    assert page_text(_docx(), 2) is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_draft_pages.py -v`
Expected: FAIL with `ModuleNotFoundError: tlddr.draft.pages`

- [ ] **Step 3: Write minimal implementation**

Create `tlddr/draft/__init__.py` (empty), then `tlddr/draft/pages.py`:

```python
import re
from tlddr.models import ExtractedDoc

_MARKER = re.compile(r"^--- (?:page (\d+)|sheet: .+) ---$", re.MULTILINE)


def _page_index(doc: ExtractedDoc) -> dict[int, str]:
    """Map each citable page number to its text. Page-less docs -> {1: whole content}."""
    if not doc.pages:
        return {1: doc.content} if doc.content.strip() else {}
    markers = list(_MARKER.finditer(doc.content))
    index: dict[int, str] = {}
    for i, m in enumerate(markers):
        start = m.end()
        end = markers[i + 1].start() if i + 1 < len(markers) else len(doc.content)
        text = doc.content[start:end].strip("\n").strip()
        page = int(m.group(1)) if m.group(1) else i + 1   # explicit page N, else sheet ordinal
        index[page] = text
    return index


def citable_pages(doc: ExtractedDoc) -> set[int]:
    return set(_page_index(doc).keys())


def page_text(doc: ExtractedDoc, page: int) -> str | None:
    return _page_index(doc).get(page)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/test_draft_pages.py -v`
Expected: PASS (3 tests).

- [ ] **Step 5: Commit**

```bash
git add tlddr/draft/__init__.py tlddr/draft/pages.py tests/test_draft_pages.py
git commit -m "feat(draft): page-addressing across signal types (citable_pages, page_text)"
```

---

### Task 3: Tiered read

**Files:**
- Create: `tlddr/draft/read.py`
- Test: `tests/test_draft_read.py`

**Interfaces:**
- Consumes: `ExtractedDoc`; `tlddr.draft.pages._page_index` (Task 2).
- Produces: `build_read(doc: ExtractedDoc, pages: list[int] | None = None, max_chars: int = WHOLE_DOC_MAX_CHARS) -> str`; constant `WHOLE_DOC_MAX_CHARS = 20000`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_draft_read.py
from tlddr.draft.read import build_read, WHOLE_DOC_MAX_CHARS
from tlddr.models import ExtractedDoc, PageProvenance, SignalType, ExtractMethod


def _pages_doc(n_pages, chars_each):
    content = "\n\n".join(f"--- page {i} ---\n" + ("x" * chars_each) for i in range(1, n_pages + 1))
    return ExtractedDoc(
        id="d", source_path="/x/d.pdf", source_sha256="a", signal_type=SignalType.MIXED,
        raw_title="D", content=content,
        pages=[PageProvenance(page=i, method=ExtractMethod.PYMUPDF_TEXT, has_text_layer=True)
               for i in range(1, n_pages + 1)],
        extractor="pdf",
    )


def test_short_doc_served_whole():
    doc = _pages_doc(2, 10)
    out = build_read(doc)
    assert "--- page 1 ---" in out and "--- page 2 ---" in out


def test_requested_pages_served_targeted():
    doc = _pages_doc(5, 10)
    out = build_read(doc, pages=[2, 4])
    assert "--- page 2 ---" in out and "--- page 4 ---" in out
    assert "--- page 1 ---" not in out and "--- page 3 ---" not in out


def test_large_doc_without_pages_returns_overview():
    doc = _pages_doc(40, 1000)                       # ~40k chars > threshold
    assert len(doc.content) > WHOLE_DOC_MAX_CHARS
    out = build_read(doc)
    assert "Request specific pages" in out
    assert "page 1" in out and "page 40" in out       # page list present
    assert "xxxxxxxxxx" not in out or len(out) < len(doc.content)   # not the whole body
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_draft_read.py -v`
Expected: FAIL with `ModuleNotFoundError: tlddr.draft.read`

- [ ] **Step 3: Write minimal implementation**

```python
# tlddr/draft/read.py
from tlddr.models import ExtractedDoc
from tlddr.draft.pages import _page_index

WHOLE_DOC_MAX_CHARS = 20000   # whole/targeted cutover; tunable in proving
_OVERVIEW_SNIPPET = 120


def build_read(doc: ExtractedDoc, pages: list[int] | None = None,
               max_chars: int = WHOLE_DOC_MAX_CHARS) -> str:
    index = _page_index(doc)
    if pages:
        parts = [f"--- page {p} ---\n{index[p]}" for p in pages if p in index]
        return "\n\n".join(parts)
    if len(doc.content) <= max_chars:
        return doc.content
    lines = [
        f"# {doc.raw_title} (large: {len(doc.content)} chars, {len(index)} pages)",
        "Request specific pages via --pages. Available pages:",
    ]
    for p, text in sorted(index.items()):
        snippet = " ".join(text[:_OVERVIEW_SNIPPET].split())
        lines.append(f"- page {p} ({len(text)} chars): {snippet}")
    return "\n".join(lines)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/test_draft_read.py -v`
Expected: PASS (3 tests).

- [ ] **Step 5: Commit**

```bash
git add tlddr/draft/read.py tests/test_draft_read.py
git commit -m "feat(draft): tiered read (whole/short, targeted pages, large-doc overview)"
```

---

### Task 4: Claim validation (machine-trust)

**Files:**
- Create: `tlddr/draft/claims.py`
- Test: `tests/test_draft_claims.py`

**Interfaces:**
- Consumes: `ExtractedDoc`, `Node`, `DraftClaim`, `Citation`, `SupportLevel`, `EvidenceRelation`, `Question`; `citable_pages` (Task 2).
- Produces: `validate_claims(raw_claims: list[dict], docs: dict[str, ExtractedDoc], nodes: dict[str, Node]) -> tuple[list[DraftClaim], list[Question]]`. Each raw claim is a dict `{section_id, text, support_level, evidence_relation, sources: [{node_id, page}]}`. Invalid citations are dropped; a claim with zero valid citations is dropped and yields a finding `Question(raised_by="draft", node_id=None, section_id=..., question=...)`. Valid citations get `source_confidence` from `nodes[node_id].confidence_interpretation`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_draft_claims.py
from tlddr.draft.claims import validate_claims
from tlddr.models import (
    ExtractedDoc, Node, PageProvenance, SignalType, ExtractMethod, Confidence, Triage,
    SupportLevel, EvidenceRelation,
)


def _doc(id="r518"):
    return ExtractedDoc(
        id=id, source_path=f"/x/{id}.pdf", source_sha256="a", signal_type=SignalType.MIXED,
        raw_title=id, content="--- page 12 ---\ndesign life 25 years",
        pages=[PageProvenance(page=12, method=ExtractMethod.PYMUPDF_TEXT, has_text_layer=True)],
        extractor="pdf",
    )


def _node(id="r518", interp=Confidence.HIGH):
    return Node(id=id, extracted_id=id, title=id, doc_type="report", description="d",
                confidence_extraction=Confidence.HIGH, confidence_interpretation=interp,
                triage=Triage.GREEN)


def _raw(section="s1", node="r518", page=12):
    return {
        "section_id": section, "text": "25-year design life.",
        "support_level": "fully_supported", "evidence_relation": "quoted",
        "sources": [{"node_id": node, "page": page}],
    }


def test_valid_claim_keeps_citation_and_attaches_confidence():
    claims, findings = validate_claims(
        [_raw()], docs={"r518": _doc()}, nodes={"r518": _node(interp=Confidence.MEDIUM)})
    assert findings == []
    assert len(claims) == 1
    assert claims[0].support_level is SupportLevel.FULLY_SUPPORTED
    assert claims[0].evidence_relation is EvidenceRelation.QUOTED
    assert claims[0].sources[0].source_confidence is Confidence.MEDIUM   # looked up, not self-graded


def test_bad_page_dropped_unknown_node_dropped_then_zero_citation_is_a_finding():
    raw = _raw()
    raw["sources"] = [{"node_id": "r518", "page": 99},     # page out of range
                      {"node_id": "ghost", "page": 1}]      # unknown node
    claims, findings = validate_claims(
        [raw], docs={"r518": _doc()}, nodes={"r518": _node()})
    assert claims == []                                     # no valid citation -> dropped
    assert len(findings) == 1
    assert findings[0].raised_by == "draft"
    assert findings[0].node_id is None
    assert findings[0].section_id == "s1"


def test_partially_valid_claim_keeps_only_resolvable_citations():
    raw = _raw()
    raw["sources"] = [{"node_id": "r518", "page": 12}, {"node_id": "r518", "page": 99}]
    claims, findings = validate_claims([raw], docs={"r518": _doc()}, nodes={"r518": _node()})
    assert findings == []
    assert [(c.node_id, c.page) for c in claims[0].sources] == [("r518", 12)]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_draft_claims.py -v`
Expected: FAIL with `ModuleNotFoundError: tlddr.draft.claims`

- [ ] **Step 3: Write minimal implementation**

```python
# tlddr/draft/claims.py
from tlddr.models import (
    ExtractedDoc, Node, DraftClaim, Citation, SupportLevel, EvidenceRelation, Question,
)
from tlddr.draft.pages import citable_pages


def validate_claims(raw_claims: list[dict],
                    docs: dict[str, ExtractedDoc],
                    nodes: dict[str, Node],
                    ) -> tuple[list[DraftClaim], list[Question]]:
    valid: list[DraftClaim] = []
    findings: list[Question] = []
    for i, raw in enumerate(raw_claims):
        section_id = raw["section_id"]
        citations: list[Citation] = []
        for src in raw.get("sources", []):
            node_id, page = src["node_id"], src["page"]
            doc = docs.get(node_id)
            if doc is None or page not in citable_pages(doc):
                continue                                    # drop unresolvable citation
            node = nodes.get(node_id)
            conf = node.confidence_interpretation if node is not None else None
            citations.append(Citation(node_id=node_id, page=page, source_confidence=conf))
        if not citations:
            findings.append(Question(
                id=f"draft-{section_id}-{i}", raised_by="draft", node_id=None,
                section_id=section_id,
                question=f"Claim '{raw['text'][:80]}' had no resolvable source and was dropped.",
            ))
            continue
        valid.append(DraftClaim(
            section_id=section_id, text=raw["text"], sources=citations,
            support_level=SupportLevel(raw["support_level"]),
            evidence_relation=EvidenceRelation(raw["evidence_relation"]),
        ))
    return valid, findings
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/test_draft_claims.py -v`
Expected: PASS (3 tests).

- [ ] **Step 5: Commit**

```bash
git add tlddr/draft/claims.py tests/test_draft_claims.py
git commit -m "feat(draft): machine-trust claim validation (citations, confidence, findings)"
```

---

### Task 5: Tier-B groundedness readout

**Files:**
- Create: `tlddr/draft/eval.py`
- Test: `tests/test_draft_eval.py`

**Interfaces:**
- Consumes: `DraftClaim`, `Section`, `SupportLevel`, `EvidenceRelation` (Task 1).
- Produces: `no_evidence_sections(claims: list[DraftClaim], sections: list[Section]) -> list[Section]`; `groundedness_readout(claims: list[DraftClaim], sections: list[Section]) -> str`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_draft_eval.py
from tlddr.draft.eval import groundedness_readout, no_evidence_sections
from tlddr.models import (
    Section, DraftClaim, Citation, SupportLevel, EvidenceRelation, Confidence,
)


def _claim(section, support, relation):
    return DraftClaim(
        section_id=section, text="t",
        sources=[Citation(node_id="n", page=1, source_confidence=Confidence.HIGH)],
        support_level=support, evidence_relation=relation,
    )


def _sections():
    return [Section(id="s1", title="Intro"), Section(id="s2", title="Empty Section")]


def test_no_evidence_sections_flags_uncovered():
    claims = [_claim("s1", SupportLevel.FULLY_SUPPORTED, EvidenceRelation.QUOTED)]
    assert [s.id for s in no_evidence_sections(claims, _sections())] == ["s2"]


def test_readout_counts_support_and_inference():
    claims = [
        _claim("s1", SupportLevel.FULLY_SUPPORTED, EvidenceRelation.QUOTED),
        _claim("s1", SupportLevel.PARTIALLY_SUPPORTED, EvidenceRelation.INFERRED),
    ]
    out = groundedness_readout(claims, _sections())
    assert "2 claims" in out
    assert "fully_supported: 1" in out
    assert "partially_supported: 1" in out
    assert "inferred: 1" in out
    assert "Empty Section" in out                # the no-evidence section is named
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_draft_eval.py -v`
Expected: FAIL with `ModuleNotFoundError: tlddr.draft.eval`

- [ ] **Step 3: Write minimal implementation**

```python
# tlddr/draft/eval.py
from tlddr.models import DraftClaim, Section, SupportLevel, EvidenceRelation

_SUPPORT_ORDER = [SupportLevel.FULLY_SUPPORTED, SupportLevel.PARTIALLY_SUPPORTED,
                  SupportLevel.UNSUPPORTED]


def no_evidence_sections(claims: list[DraftClaim], sections: list[Section]) -> list[Section]:
    covered = {c.section_id for c in claims}
    return [s for s in sections if s.id not in covered]


def groundedness_readout(claims: list[DraftClaim], sections: list[Section]) -> str:
    total = len(claims)
    lines = ["# Draft groundedness readout", "", f"{total} claims across "
             f"{len({c.section_id for c in claims})} sections.", "", "## Support level"]
    for level in _SUPPORT_ORDER:
        lines.append(f"- {level.value}: {sum(1 for c in claims if c.support_level is level)}")
    inferred = sum(1 for c in claims if c.evidence_relation is EvidenceRelation.INFERRED)
    lines += ["", "## Evidence relation",
              f"- inferred: {inferred}",
              f"- quoted: {total - inferred}", "", "## Sections with no evidence"]
    empty = no_evidence_sections(claims, sections)
    lines += [f"- {s.title} (`{s.id}`)" for s in empty] if empty else ["- none"]
    return "\n".join(lines) + "\n"
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/test_draft_eval.py -v`
Expected: PASS (2 tests).

- [ ] **Step 5: Commit**

```bash
git add tlddr/draft/eval.py tests/test_draft_eval.py
git commit -m "feat(draft): tier-B deterministic groundedness readout"
```

---

### Task 6: C-lite verdict ingestion

**Files:**
- Create: `tlddr/draft/verify.py`
- Test: `tests/test_draft_verify.py`

**Interfaces:**
- Consumes: `DraftClaim`, `SupportLevel`, `Question` (Task 1).
- Produces: `ingest_verdicts(verdicts: list[dict], claims: list[DraftClaim]) -> list[Question]`. Each verdict is `{index: int, support_level: str, contradiction: bool, note: str}` referencing `claims[index]`. A `raised_by="verify"` question is raised when the judge's support level is *lower* than the drafter's (overclaim) or `contradiction` is true.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_draft_verify.py
from tlddr.draft.verify import ingest_verdicts
from tlddr.models import DraftClaim, Citation, SupportLevel, EvidenceRelation, Confidence


def _claim(section="s1", support=SupportLevel.FULLY_SUPPORTED):
    return DraftClaim(
        section_id=section, text="claimed strongly",
        sources=[Citation(node_id="n", page=1, source_confidence=Confidence.HIGH)],
        support_level=support, evidence_relation=EvidenceRelation.QUOTED,
    )


def test_judge_downgrade_raises_verify_question():
    claims = [_claim(support=SupportLevel.FULLY_SUPPORTED)]
    verdicts = [{"index": 0, "support_level": "unsupported", "contradiction": False,
                 "note": "page does not state this"}]
    qs = ingest_verdicts(verdicts, claims)
    assert len(qs) == 1
    assert qs[0].raised_by == "verify"
    assert qs[0].section_id == "s1"
    assert "page does not state this" in qs[0].question


def test_agreement_raises_nothing():
    claims = [_claim(support=SupportLevel.FULLY_SUPPORTED)]
    verdicts = [{"index": 0, "support_level": "fully_supported", "contradiction": False, "note": ""}]
    assert ingest_verdicts(verdicts, claims) == []


def test_contradiction_flag_always_raises():
    claims = [_claim(support=SupportLevel.PARTIALLY_SUPPORTED)]
    verdicts = [{"index": 0, "support_level": "partially_supported", "contradiction": True,
                 "note": "conflicts with r304"}]
    qs = ingest_verdicts(verdicts, claims)
    assert len(qs) == 1 and qs[0].raised_by == "verify"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_draft_verify.py -v`
Expected: FAIL with `ModuleNotFoundError: tlddr.draft.verify`

- [ ] **Step 3: Write minimal implementation**

```python
# tlddr/draft/verify.py
from tlddr.models import DraftClaim, SupportLevel, Question

_RANK = {SupportLevel.UNSUPPORTED: 0, SupportLevel.PARTIALLY_SUPPORTED: 1,
         SupportLevel.FULLY_SUPPORTED: 2}


def ingest_verdicts(verdicts: list[dict], claims: list[DraftClaim]) -> list[Question]:
    questions: list[Question] = []
    for v in verdicts:
        claim = claims[v["index"]]
        judged = SupportLevel(v["support_level"])
        downgrade = _RANK[judged] < _RANK[claim.support_level]
        if not (downgrade or v.get("contradiction")):
            continue
        reason = "contradiction" if v.get("contradiction") else \
            f"judge:{judged.value} < drafter:{claim.support_level.value}"
        note = (v.get("note") or "").strip()
        questions.append(Question(
            id=f"verify-{v['index']}", raised_by="verify", node_id=None,
            section_id=claim.section_id,
            question=f"[{reason}] '{claim.text[:80]}' — {note}".rstrip(" -"),
        ))
    return questions
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/test_draft_verify.py -v`
Expected: PASS (3 tests).

- [ ] **Step 5: Commit**

```bash
git add tlddr/draft/verify.py tests/test_draft_verify.py
git commit -m "feat(draft): C-lite verdict ingestion into raised_by=verify questions"
```

---

### Task 7: Assemble (published draft + reviewer sidecar)

**Files:**
- Create: `tlddr/draft/assemble.py`
- Test: `tests/test_draft_assemble.py`

**Interfaces:**
- Consumes: `DraftClaim`, `Section`, `Question`, `Node`, `SupportLevel`, `EvidenceRelation`, `Confidence` (Task 1); `no_evidence_sections` (Task 5).
- Produces: `render_published(sections: list[Section], claims: list[DraftClaim]) -> str`; `render_sidecar(sections: list[Section], claims: list[DraftClaim], questions: list[Question], nodes: dict[str, Node]) -> str`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_draft_assemble.py
from tlddr.draft.assemble import render_published, render_sidecar
from tlddr.models import (
    Section, DraftClaim, Citation, Question, Node, SupportLevel, EvidenceRelation,
    Confidence, Triage,
)


def _sections():
    return [Section(id="s1", title="Overview"), Section(id="s2", title="Gaps")]


def _node(id="r518", interp=Confidence.HIGH):
    return Node(id=id, extracted_id=id, title="R518 Report", doc_type="report", description="d",
                confidence_extraction=Confidence.HIGH, confidence_interpretation=interp,
                triage=Triage.GREEN)


def _claims():
    return [
        DraftClaim(section_id="s1", text="Design life is 25 years.",
                   sources=[Citation(node_id="r518", page=12, source_confidence=Confidence.HIGH)],
                   support_level=SupportLevel.FULLY_SUPPORTED,
                   evidence_relation=EvidenceRelation.QUOTED),
        DraftClaim(section_id="s1", text="Implies mid-life inverter swap.",
                   sources=[Citation(node_id="r304", page=3, source_confidence=Confidence.LOW)],
                   support_level=SupportLevel.PARTIALLY_SUPPORTED,
                   evidence_relation=EvidenceRelation.INFERRED),
    ]


def test_published_is_clean_prose_by_section():
    out = render_published(_sections(), _claims())
    assert "## Overview" in out
    assert "Design life is 25 years. Implies mid-life inverter swap." in out
    assert "r518" not in out and "fully_supported" not in out      # no provenance leaks into draft


def test_sidecar_lists_provenance_warnings_inferences_and_no_evidence():
    nodes = {"r518": _node(), "r304": _node(id="r304", interp=Confidence.LOW)}
    questions = [Question(id="q1", raised_by="verify", section_id="s1",
                          question="judge downgrade on claim 1")]
    out = render_sidecar(_sections(), _claims(), questions, nodes)
    assert "## Overview" in out
    assert "[[r518]]" in out and "[[r304]]" in out                  # provenance
    assert "r304" in out and "inference" in out.lower()             # inference surfaced
    assert "low" in out.lower()                                     # low-confidence warning
    assert "judge downgrade on claim 1" in out                      # open question
    assert "Gaps" in out and "insufficient evidence" in out.lower() # s2 no-evidence
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_draft_assemble.py -v`
Expected: FAIL with `ModuleNotFoundError: tlddr.draft.assemble`

- [ ] **Step 3: Write minimal implementation**

```python
# tlddr/draft/assemble.py
from tlddr.models import (
    DraftClaim, Section, Question, Node, SupportLevel, EvidenceRelation, Confidence,
)
from tlddr.draft.eval import no_evidence_sections

_WEAK_SUPPORT = {SupportLevel.PARTIALLY_SUPPORTED, SupportLevel.UNSUPPORTED}


def _by_section(claims: list[DraftClaim], section_id: str) -> list[DraftClaim]:
    return [c for c in claims if c.section_id == section_id]


def render_published(sections: list[Section], claims: list[DraftClaim]) -> str:
    lines: list[str] = ["# Draft report", ""]
    for s in sections:
        lines.append(f"## {s.title}")
        text = " ".join(c.text for c in _by_section(claims, s.id))
        lines.append(text if text else "_(no content drafted)_")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def render_sidecar(sections: list[Section], claims: list[DraftClaim],
                   questions: list[Question], nodes: dict[str, Node]) -> str:
    no_evidence = {s.id for s in no_evidence_sections(claims, sections)}
    lines: list[str] = ["# Reviewer comments", ""]
    for s in sections:
        lines.append(f"## {s.title}")
        if s.id in no_evidence:
            lines.append("- **insufficient evidence**: no source document fed this section.")
            lines.append("")
            continue
        section_claims = _by_section(claims, s.id)

        provenance = sorted({c.node_id for cl in section_claims for c in cl.sources})
        lines.append("**Provenance:** " + ", ".join(f"[[{n}]]" for n in provenance))

        warnings: list[str] = []
        for cl in section_claims:
            if cl.support_level in _WEAK_SUPPORT:
                warnings.append(f"{cl.support_level.value}: '{cl.text[:60]}'")
            for c in cl.sources:
                if c.source_confidence is Confidence.LOW:
                    warnings.append(f"low-confidence source [[{c.node_id}]] used for "
                                    f"'{cl.text[:60]}'")
        if warnings:
            lines.append("**Warnings:**")
            lines += [f"- {w}" for w in warnings]

        inferences = [cl for cl in section_claims
                      if cl.evidence_relation is EvidenceRelation.INFERRED]
        if inferences:
            lines.append("**Inferences (not stated verbatim in the sources):**")
            for cl in inferences:
                srcs = ", ".join(f"[[{c.node_id}]] p{c.page}" for c in cl.sources)
                lines.append(f"- '{cl.text[:80]}' (from {srcs})")

        section_qs = [q for q in questions if q.section_id == s.id]
        if section_qs:
            lines.append("**Open questions:**")
            lines += [f"- ({q.raised_by}) {q.question}" for q in section_qs]
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/test_draft_assemble.py -v`
Expected: PASS (2 tests).

- [ ] **Step 5: Commit**

```bash
git add tlddr/draft/assemble.py tests/test_draft_assemble.py
git commit -m "feat(draft): assemble published draft + reviewer sidecar"
```

---

### Task 8: CLI wiring

**Files:**
- Modify: `tlddr/cli.py` (imports at top; new functions after `understand_render`, line ~113; new subparsers + dispatch in `main`)
- Test: `tests/test_draft_cli.py`

**Interfaces:**
- Consumes: every `tlddr.draft.*` function (Tasks 2–7); existing `_load_doc`, `load_sections`, `section_ids`.
- Produces CLI functions: `draft_read(extracted_dir, node_id, pages)`, `draft_commit(claims_path, extracted_dir, work_dir, sections_path)`, `draft_verify_commit(verdicts_path, work_dir)`, `draft_eval(work_dir, sections_path)`, `assemble(work_dir, out_dir, sections_path)`. Subcommands: `draft-read`, `draft-commit`, `draft-verify-commit`, `draft-eval`, `assemble`.

Persistence layout (under `--work`, default `.tlddr`): nodes in `nodes/*.json` (existing), claims in `claims.json` (list; `draft-commit` replaces the committed section's prior claims), questions in `questions.json` (existing; findings/verdicts appended).

- [ ] **Step 1: Write the failing test**

```python
# tests/test_draft_cli.py
import json
from pathlib import Path
from tlddr.cli import main
from tlddr.models import ExtractedDoc, Node, PageProvenance, SignalType, ExtractMethod, Confidence, Triage


def _setup(tmp: Path):
    work = tmp / ".tlddr"
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
    sections = tmp / "sections.json"
    sections.write_text(json.dumps([{"id": "s1", "title": "Overview"},
                                    {"id": "s2", "title": "Gaps"}]))
    return work, extracted, sections


def test_draft_commit_then_assemble_writes_report_and_sidecar(tmp_path):
    work, extracted, sections = _setup(tmp_path)
    claims = tmp_path / "claims.json"
    claims.write_text(json.dumps([{
        "section_id": "s1", "text": "Design life is 25 years.",
        "support_level": "fully_supported", "evidence_relation": "quoted",
        "sources": [{"node_id": "r518", "page": 12}],
    }]))

    assert main(["draft-commit", "--claims", str(claims), "--extracted", str(extracted),
                 "--work", str(work), "--sections", str(sections)]) == 0
    assert (work / "claims.json").exists()

    out = tmp_path / "out"
    assert main(["assemble", "--work", str(work), "--out", str(out),
                 "--sections", str(sections)]) == 0
    report = (out / "report.md").read_text()
    sidecar = (out / "report_comments.md").read_text()
    assert "Design life is 25 years." in report
    assert "[[r518]]" in sidecar
    assert "insufficient evidence" in sidecar.lower()      # s2 had no claims


def test_draft_read_prints_page(tmp_path, capsys):
    work, extracted, sections = _setup(tmp_path)
    assert main(["draft-read", "--extracted", str(extracted), "--id", "r518",
                 "--pages", "12"]) == 0
    assert "design life 25 years" in capsys.readouterr().out
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_draft_cli.py -v`
Expected: FAIL with `SystemExit`/`argparse` error (`invalid choice: 'draft-commit'`).

- [ ] **Step 3: Write minimal implementation**

Add imports near the other `tlddr.*` imports in `tlddr/cli.py`:

```python
from tlddr.draft.read import build_read
from tlddr.draft.claims import validate_claims
from tlddr.draft.eval import groundedness_readout
from tlddr.draft.verify import ingest_verdicts
from tlddr.draft.assemble import render_published, render_sidecar
from tlddr.models import DraftClaim
```

Add these functions after `understand_render`:

```python
def _load_claims(work_dir: Path) -> list[DraftClaim]:
    path = work_dir / "claims.json"
    return [DraftClaim.model_validate(c) for c in json.loads(path.read_text())] if path.exists() else []


def _append_questions(work_dir: Path, new: list, drop_section: str | None = None) -> None:
    path = work_dir / "questions.json"
    existing = json.loads(path.read_text()) if path.exists() else []
    if drop_section is not None:
        existing = [q for q in existing if not
                    (q.get("raised_by") == "draft" and q.get("section_id") == drop_section)]
    existing.extend(q.model_dump(mode="json") for q in new)
    path.write_text(json.dumps(existing, indent=2))


def draft_read(extracted_dir: Path, node_id: str, pages: list[int] | None) -> str:
    return build_read(_load_doc(extracted_dir, node_id), pages=pages)


def draft_commit(claims_path: Path, extracted_dir: Path, work_dir: Path,
                 sections_path: Path | None = None) -> list[DraftClaim]:
    raw = json.loads(claims_path.read_text())
    docs = {p.stem: _load_doc(extracted_dir, p.stem) for p in extracted_dir.glob("*.json")}
    nodes = {n.id: n for n in (Node.model_validate_json(p.read_text())
                               for p in (work_dir / "nodes").glob("*.json"))}
    valid, findings = validate_claims(raw, docs, nodes)

    committed_sections = {c.section_id for c in valid}
    committed = [c for c in _load_claims(work_dir) if c.section_id not in committed_sections]
    committed.extend(valid)
    (work_dir / "claims.json").write_text(
        json.dumps([c.model_dump(mode="json") for c in committed], indent=2))
    for section in {c.section_id for c in valid}:
        _append_questions(work_dir, [], drop_section=section)
    _append_questions(work_dir, findings)
    print(f"committed {len(valid)} claims, {len(findings)} findings")
    return valid


def draft_verify_commit(verdicts_path: Path, work_dir: Path) -> None:
    verdicts = json.loads(verdicts_path.read_text())
    questions = ingest_verdicts(verdicts, _load_claims(work_dir))
    _append_questions(work_dir, questions)
    print(f"raised {len(questions)} verify questions")


def draft_eval(work_dir: Path, sections_path: Path) -> None:
    print(groundedness_readout(_load_claims(work_dir), load_sections(sections_path)))


def assemble(work_dir: Path, out_dir: Path, sections_path: Path) -> None:
    claims = _load_claims(work_dir)
    sections = load_sections(sections_path)
    nodes = {n.id: n for n in (Node.model_validate_json(p.read_text())
                               for p in (work_dir / "nodes").glob("*.json"))}
    questions_path = work_dir / "questions.json"
    questions = ([Question.model_validate(q) for q in json.loads(questions_path.read_text())]
                 if questions_path.exists() else [])
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "report.md").write_text(render_published(sections, claims))
    (out_dir / "report_comments.md").write_text(render_sidecar(sections, claims, questions, nodes))
    print(f"assembled {len(claims)} claims into report.md + report_comments.md")
```

Add subparsers in `main` (after the `understand-render` parser):

```python
    dread = sub.add_parser("draft-read", help="serve a node's content/pages for drafting")
    dread.add_argument("--extracted", required=True, type=Path)
    dread.add_argument("--id", required=True)
    dread.add_argument("--pages", type=str, default=None, help="comma-separated page numbers")

    dcommit = sub.add_parser("draft-commit", help="validate agent draft claims for a section")
    dcommit.add_argument("--claims", required=True, type=Path)
    dcommit.add_argument("--extracted", required=True, type=Path)
    dcommit.add_argument("--work", default=Path(".tlddr"), type=Path)
    dcommit.add_argument("--sections", type=Path, default=None)

    dverify = sub.add_parser("draft-verify-commit", help="ingest C-lite judge verdicts")
    dverify.add_argument("--verdicts", required=True, type=Path)
    dverify.add_argument("--work", default=Path(".tlddr"), type=Path)

    deval = sub.add_parser("draft-eval", help="print the tier-B groundedness readout")
    deval.add_argument("--work", default=Path(".tlddr"), type=Path)
    deval.add_argument("--sections", required=True, type=Path)

    asm = sub.add_parser("assemble", help="assemble report.md + report_comments.md")
    asm.add_argument("--work", default=Path(".tlddr"), type=Path)
    asm.add_argument("--out", default=Path("report"), type=Path)
    asm.add_argument("--sections", required=True, type=Path)
```

Add dispatch branches (before `return 1`):

```python
    if args.command == "draft-read":
        pages = [int(p) for p in args.pages.split(",")] if args.pages else None
        print(draft_read(args.extracted, args.id, pages))
        return 0
    if args.command == "draft-commit":
        draft_commit(args.claims, args.extracted, args.work, args.sections)
        return 0
    if args.command == "draft-verify-commit":
        draft_verify_commit(args.verdicts, args.work)
        return 0
    if args.command == "draft-eval":
        draft_eval(args.work, args.sections)
        return 0
    if args.command == "assemble":
        assemble(args.work, args.out, args.sections)
        return 0
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/test_draft_cli.py -v`
Expected: PASS (2 tests). Then run the whole suite: `.venv/bin/pytest` — Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add tlddr/cli.py tests/test_draft_cli.py
git commit -m "feat(draft): wire draft-read/commit/verify/eval/assemble CLI subcommands"
```

---

### Task 9: Host-agent procedures (skills)

**Files:**
- Modify: `skills/generate-sections/SKILL.md`
- Create: `skills/draft/SKILL.md`, `skills/draft-verify/SKILL.md`

This task is documentation; its "test" is the consistency self-review in Step 3 + the whole suite still passing (no code changed). Match the structure/voice of the existing `skills/understand/SKILL.md`.

- [ ] **Step 1: Update `skills/generate-sections/SKILL.md`**

Add a step (and adjust the materialization step) so the agent preserves each section's *body* content into `Section.guidance`: when interpreting the raw heading file, for every heading capture the text/tables/bullets that sit under it (until the next heading) verbatim as that section's `guidance`; a heading with nothing under it gets `guidance: null`. The emitted `sections.json` objects become `{id, title, parent?, guidance?}`. State explicitly: do not invent guidance the user did not write; do not flatten a rich template — capture it verbatim.

- [ ] **Step 2: Create `skills/draft/SKILL.md`** — per-section drafting procedure:
  1. Prereqs: a committed vault (`nodes/*.json`), `sections.json`, the `ExtractedDoc` store.
  2. For each section: gather its tagged nodes (`report_sections` contains the section id). If none, the CLI emits the no-evidence finding — skip drafting.
  3. Read content with `tlddr draft-read --extracted <dir> --id <node>` (whole if short; for a large-doc overview, re-call with `--pages <list>` to pull specific pages — bounded, ranked by relevance).
  4. Draft the section against its `guidance` (+ the fixed grounding/format preamble: ground only in provided context; cite every claim with `(node_id, page)`; default structure if guidance is thin; mark each claim `quoted` vs `inferred` and `fully_supported`/`partially_supported`/`unsupported`).
  5. Emit a claims JSON array and `tlddr draft-commit`. Reminder: only cite pages you actually read; the CLI drops unresolvable citations and turns zero-citation claims into findings.

- [ ] **Step 3: Create `skills/draft-verify/SKILL.md`** — the C-lite independent judge:
  1. Run with fresh context (do not reuse the drafting reasoning).
  2. For each committed claim, read its cited page(s) via `tlddr draft-read --id <node> --pages <p>` and judge: does the page support the claim text? Emit a verdict `{index, support_level, contradiction, note}` — judge support independently; flag contradictions between cited sources.
  3. `tlddr draft-verify-commit` ingests the verdicts; disagreements become `raised_by=verify` questions for the human.

- [ ] **Step 4: Self-review + run suite**

Re-read the three skills for consistency with the CLI flags in Task 8 (exact subcommand names and arguments). Run `.venv/bin/pytest` — Expected: all pass (no code changed).

- [ ] **Step 5: Commit**

```bash
git add skills/generate-sections/SKILL.md skills/draft/SKILL.md skills/draft-verify/SKILL.md
git commit -m "docs(draft): draft + draft-verify skills; generate-sections preserves guidance"
```

---

### Task 10: Module index docs

**Files:**
- Create: `tlddr/draft/CLAUDE.md`
- Modify: `tlddr/CLAUDE.md` (the `cli.py` section: add the five draft subcommands; mention the new `draft/` package and `Section.guidance`/`DraftClaim`/`Citation` contracts in `models.py`)

This task is documentation. Match the format of `tlddr/understand/CLAUDE.md`.

- [ ] **Step 1: Create `tlddr/draft/CLAUDE.md`**

A module index for `tlddr/draft/` listing each file's purpose and key functions: `pages.py` (`citable_pages`, `page_text`), `read.py` (`build_read`, `WHOLE_DOC_MAX_CHARS`), `claims.py` (`validate_claims`), `eval.py` (`groundedness_readout`, `no_evidence_sections`), `verify.py` (`ingest_verdicts`), `assemble.py` (`render_published`, `render_sidecar`). One paragraph header: the deterministic Draft toolkit (stage 3) — the model drafts + judges via skills; these helpers validate citations, score groundedness, and render the published draft + reviewer sidecar; page-addressing decision A.

- [ ] **Step 2: Update `tlddr/CLAUDE.md`**

In the `models.py` entry add `SupportLevel`/`EvidenceRelation`/`Citation`/`DraftClaim` and `Section.guidance`. In the `cli.py` entry add the five subcommands (`draft-read`, `draft-commit`, `draft-verify-commit`, `draft-eval`, `assemble`) and note the new `tlddr/draft/` package. Update the intro line so Draft is "in progress" rather than "next".

- [ ] **Step 3: Run suite**

Run `.venv/bin/pytest` — Expected: all pass (no code changed).

- [ ] **Step 4: Commit**

```bash
git add tlddr/draft/CLAUDE.md tlddr/CLAUDE.md
git commit -m "docs(draft): module index for tlddr/draft + refresh top-level index"
```

---

## Self-Review (completed)

**Spec coverage:** D1 → Tasks 1 (Section.guidance) + 9 (generate-sections preserves it) + grounding preamble in 9. D2 → Tasks 2 (page-addressing A) + 3 (tiered read) + 8 (`draft-read`). D3 → Tasks 1 (two-axis DraftClaim) + 4 (validation, looked-up confidence, zero-citation finding). D4 → Task 7 (sidecar, deterministically assembled) + 8 (shared questions.json queue). D5 → Tasks 5 (Tier B) + 6 (C-lite verdicts) + 9 (draft-verify skill); C-full explicitly deferred. D6 → async queue is the persistence model (claims.json + questions.json; re-passes by re-running `draft-commit` per section) — no blocking interactive code, per decision. Page-addressing decision A → Task 2.

**Placeholder scan:** none — every code step carries full code; doc tasks (9, 10) specify exact content to write.

**Type consistency:** `validate_claims(raw, docs, nodes)`, `groundedness_readout(claims, sections)`, `ingest_verdicts(verdicts, claims)`, `render_published(sections, claims)`, `render_sidecar(sections, claims, questions, nodes)`, `build_read(doc, pages, max_chars)`, `citable_pages(doc)`/`page_text(doc, page)` — names and signatures match across Tasks 1–10 and the CLI wiring in Task 8.

## Proving (after Task 10)

Follow `skills/understand/SKILL.md` to (re)build the vault, then run `skills/draft` over the corpus + `.tlddr/sections.json`, `tlddr draft-eval`, `skills/draft-verify`, and `tlddr assemble`. Gate: report reads coherently, every claim traces to a real page, `draft-eval` shows a sane support distribution, and `report_comments.md` honestly lists provenance/warnings/inferences/no-evidence per section. (Separate from the gold-comparison, which remains gated on a finished worked example.)
