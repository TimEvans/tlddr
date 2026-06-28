# Understand Toolkit Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the deterministic Python toolkit the Understand stage runs on — slice-building, extraction-confidence, triage derivation, edge validation, and node/vault rendering — plus the `tlddr` CLI subcommands that expose them, so a host agent can drive a full Understand run.

**Architecture:** The host agent does the comprehension (description, doc_type, interpretation confidence, proposed edges, questions) and hands the result to the CLI as an enrichment JSON. The CLI does everything deterministic: it reads the faithful `ExtractedDoc` store, builds the bounded slice the agent reads, computes extraction confidence, validates proposed edges against the known node set, derives the traffic-light triage, writes structured node records, and renders the Obsidian vault + `_index.md` + `_triage.md`. The node is an understanding overlay plus a pointer to the content store — never a clone.

**Tech Stack:** Python 3.11+, pydantic v2, pyyaml (frontmatter), pytest. Builds on the existing `tlddr` package (`ExtractedDoc`, `SignalType`, `PageProvenance` from `tlddr/models.py`).

## Global Constraints

- **No emojis** anywhere — code, comments, commit messages, or output.
- **Conventional commits**: `type(scope): description`.
- **No model calls in this toolkit.** All comprehension is the host agent's; this code only does deterministic work. The agent's output enters as an enrichment JSON.
- **The node is an overlay + pointer, never a content clone.** Faithful content stays in the `ExtractedDoc` store; the node references it by `extracted_id`.
- **Grounding guardrail:** nothing here ever copies source content into the node body beyond the model's own description. Citations (a later stage) resolve to the store, not to node text.
- **Confidence is ordinal** (`high`/`medium`/`low`); **triage is derived, never hand-set.**
- **Machine-trust:** an edge whose `target` is not a known node id is dropped, not written.
- **Composition over inheritance:** the `Node` references the extracted record by id; it does not subclass `ExtractedDoc`.
- **Minimal dependencies:** add only `pyyaml`. Nothing else.

---

## File structure

```
tl-ddr/
  pyproject.toml                       # add pyyaml
  tlddr/
    models.py                          # ADD: Confidence, Triage, RelationType, Edge, Question, Node
    understand/
      __init__.py
      slice.py                         # build_slice(doc) -> str
      confidence.py                    # extraction_confidence(doc) -> Confidence
      triage.py                        # derive_triage(...) -> Triage
      edges.py                         # validate_edges(...) -> (valid, dropped)
      node_render.py                   # render_node_markdown(node) -> str
      render.py                        # render_index(nodes), render_triage(nodes, questions)
      commit.py                        # build_node(enrichment, doc, known_ids) -> (Node, questions)
    cli.py                             # ADD: understand-slice / understand-commit / understand-render
  tests/
    test_understand_models.py
    test_slice.py
    test_confidence.py
    test_triage.py
    test_edges.py
    test_node_render.py
    test_render.py
    test_commit.py
    test_understand_cli.py
```

---

### Task 1: Understand data models

**Files:**
- Modify: `tlddr/models.py`
- Modify: `pyproject.toml` (add `pyyaml`)
- Test: `tests/test_understand_models.py`

**Interfaces:**
- Consumes: existing `tlddr.models` enums/classes.
- Produces:
  - `Confidence(str, Enum)` — `HIGH="high"`, `MEDIUM="medium"`, `LOW="low"`
  - `Triage(str, Enum)` — `GREEN="green"`, `AMBER="amber"`, `RED="red"`
  - `RelationType(str, Enum)` — `CONTRADICTS`, `SUPERSEDES`, `CORROBORATES`, `REFERENCES`, `SAME_SUBJECT`, `INPUT_TO`
  - `Edge(BaseModel)` — `target: str`, `relation: RelationType`, `rationale: str`
  - `Question(BaseModel)` — `id: str`, `raised_by: str`, `node_id: str | None = None`, `section_id: str | None = None`, `question: str`, `blocks: list[str] = []`, `blocking: bool = False`, `answer: str | None = None`
  - `Node(BaseModel)` — `id: str`, `extracted_id: str`, `title: str`, `doc_type: str`, `description: str`, `report_sections: list[str] = []`, `confidence_extraction: Confidence`, `confidence_interpretation: Confidence`, `triage: Triage`, `open_questions: list[str] = []`, `related: list[Edge] = []`

- [ ] **Step 1: Add `pyyaml` to dependencies**

In `pyproject.toml`, add `"pyyaml>=6.0"` to the `dependencies` list (after `openpyxl>=3.1`). Then run:
```bash
.venv/bin/pip install -q -e ".[dev]"
```
Expected: installs pyyaml without error.

- [ ] **Step 2: Write the failing test**

Create `tests/test_understand_models.py`:

```python
from tlddr.models import (
    Confidence, Triage, RelationType, Edge, Question, Node,
)


def test_enums_serialise_to_strings():
    assert Confidence.HIGH.value == "high"
    assert Triage.AMBER.value == "amber"
    assert RelationType.CONTRADICTS.value == "contradicts"


def test_node_round_trips_json_with_edges():
    node = Node(
        id="a6", extracted_id="a6", title="A6", doc_type="cba",
        description="A cost benefit analysis.",
        confidence_extraction=Confidence.HIGH,
        confidence_interpretation=Confidence.MEDIUM,
        triage=Triage.AMBER,
        open_questions=["q-0001"],
        related=[Edge(target="a3", relation=RelationType.CORROBORATES, rationale="same REZ data")],
    )
    restored = Node.model_validate_json(node.model_dump_json())
    assert restored.triage is Triage.AMBER
    assert restored.related[0].relation is RelationType.CORROBORATES
    assert restored.report_sections == []


def test_question_defaults():
    q = Question(id="q-1", raised_by="understand", question="Which pump?")
    assert q.blocking is False
    assert q.blocks == []
    assert q.answer is None
```

- [ ] **Step 3: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_understand_models.py -v`
Expected: FAIL with `ImportError: cannot import name 'Confidence'`.

- [ ] **Step 4: Implement the models — append to `tlddr/models.py`**

Add at the end of `tlddr/models.py`:

```python
class Confidence(str, Enum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class Triage(str, Enum):
    GREEN = "green"
    AMBER = "amber"
    RED = "red"


class RelationType(str, Enum):
    CONTRADICTS = "contradicts"
    SUPERSEDES = "supersedes"
    CORROBORATES = "corroborates"
    REFERENCES = "references"
    SAME_SUBJECT = "same_subject"
    INPUT_TO = "input_to"


class Edge(BaseModel):
    target: str
    relation: RelationType
    rationale: str


class Question(BaseModel):
    id: str
    raised_by: str
    node_id: str | None = None
    section_id: str | None = None
    question: str
    blocks: list[str] = Field(default_factory=list)
    blocking: bool = False
    answer: str | None = None


class Node(BaseModel):
    id: str
    extracted_id: str
    title: str
    doc_type: str
    description: str
    report_sections: list[str] = Field(default_factory=list)
    confidence_extraction: Confidence
    confidence_interpretation: Confidence
    triage: Triage
    open_questions: list[str] = Field(default_factory=list)
    related: list[Edge] = Field(default_factory=list)
```

- [ ] **Step 5: Run test to verify it passes**

Run: `.venv/bin/pytest tests/test_understand_models.py -v`
Expected: PASS (3 passed).

- [ ] **Step 6: Commit**

```bash
git add tlddr/models.py pyproject.toml tests/test_understand_models.py
git commit -m "feat(understand): add Confidence, Triage, Edge, Question, Node models"
```

---

### Task 2: Bounded slice builder

**Files:**
- Create: `tlddr/understand/__init__.py` (empty)
- Create: `tlddr/understand/slice.py`
- Test: `tests/test_slice.py`

**Interfaces:**
- Consumes: `tlddr.models.ExtractedDoc`.
- Produces: `tlddr.understand.slice.build_slice(doc: ExtractedDoc, max_chars: int = 8000) -> str` — a bounded textual slice: title + signal type, the document's structure (page/sheet markers and markdown headings), the extraction warnings, and a head sample of the content capped so the whole slice stays near `max_chars`.

- [ ] **Step 1: Write the failing test**

Create `tests/test_slice.py`:

```python
from tlddr.understand.slice import build_slice
from tlddr.models import ExtractedDoc, PageProvenance, SignalType, ExtractMethod


def _doc(content, **kw):
    base = dict(
        id="d", source_path="/x/d.pdf", source_sha256="abc",
        signal_type=SignalType.BORN_DIGITAL_REPORT, raw_title="Big Report",
        content=content, pages=[], warnings=[], extractor="pdf",
    )
    base.update(kw)
    return ExtractedDoc(**base)


def test_slice_includes_title_structure_and_warnings():
    content = "--- page 1 ---\n# Executive Summary\nbody text\n--- page 2 ---\n## Risks\nmore"
    doc = _doc(content, warnings=["page 3 image-only"])
    s = build_slice(doc)
    assert "Big Report" in s
    assert "born_digital_report" in s
    assert "Executive Summary" in s        # heading surfaced as structure
    assert "page 3 image-only" in s         # warning surfaced
    assert "body text" in s                 # head sample present


def test_slice_is_bounded():
    doc = _doc("x" * 50000)
    s = build_slice(doc, max_chars=2000)
    # the content sample is capped; total stays in a sane bound
    assert len(s) < 4000
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_slice.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'tlddr.understand'`.

- [ ] **Step 3: Implement**

Create empty `tlddr/understand/__init__.py`.

Create `tlddr/understand/slice.py`:

```python
import re
from tlddr.models import ExtractedDoc

_MARKER = re.compile(r"^(--- (?:page \d+|sheet: .+) ---|#{1,6} .+)$", re.MULTILINE)
_MAX_STRUCTURE_LINES = 60
_MAX_WARNINGS = 20


def build_slice(doc: ExtractedDoc, max_chars: int = 8000) -> str:
    lines = [
        f"# {doc.raw_title}",
        f"signal_type: {doc.signal_type.value}",
        f"extractor: {doc.extractor}",
    ]

    structure = _MARKER.findall(doc.content)
    if structure:
        lines.append("\n## structure")
        lines.extend(structure[:_MAX_STRUCTURE_LINES])

    if doc.warnings:
        lines.append("\n## warnings")
        lines.extend(f"- {w}" for w in doc.warnings[:_MAX_WARNINGS])

    lines.append("\n## content sample")
    lines.append(doc.content[:max_chars])

    return "\n".join(lines)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/test_slice.py -v`
Expected: PASS (2 passed).

- [ ] **Step 5: Commit**

```bash
git add tlddr/understand/__init__.py tlddr/understand/slice.py tests/test_slice.py
git commit -m "feat(understand): add bounded slice builder"
```

---

### Task 3: Extraction confidence

**Files:**
- Create: `tlddr/understand/confidence.py`
- Test: `tests/test_confidence.py`

**Interfaces:**
- Consumes: `tlddr.models.ExtractedDoc`, `Confidence`, `SignalType`.
- Produces: `tlddr.understand.confidence.extraction_confidence(doc: ExtractedDoc) -> Confidence` — proportional, from the extraction signals only (never the model's view).

- [ ] **Step 1: Write the failing test**

Create `tests/test_confidence.py`:

```python
from tlddr.understand.confidence import extraction_confidence
from tlddr.models import ExtractedDoc, PageProvenance, SignalType, ExtractMethod, Confidence


def _doc(**kw):
    base = dict(
        id="d", source_path="/x", source_sha256="a",
        signal_type=SignalType.BORN_DIGITAL_REPORT, raw_title="t",
        content="", pages=[], warnings=[], extractor="pdf",
    )
    base.update(kw)
    return ExtractedDoc(**base)


def _pages(n_text, n_image):
    pages = [PageProvenance(page=i + 1, method=ExtractMethod.PYMUPDF_TEXT, has_text_layer=True)
             for i in range(n_text)]
    pages += [PageProvenance(page=n_text + i + 1, method=ExtractMethod.VISION, has_text_layer=False)
              for i in range(n_image)]
    return pages


def test_all_text_pdf_is_high():
    assert extraction_confidence(_doc(pages=_pages(10, 0))) is Confidence.HIGH


def test_one_image_cover_in_long_doc_stays_high():
    assert extraction_confidence(_doc(signal_type=SignalType.MIXED, pages=_pages(114, 1))) is Confidence.HIGH


def test_mostly_image_doc_is_low():
    assert extraction_confidence(_doc(signal_type=SignalType.DRAWING, pages=_pages(0, 5))) is Confidence.LOW


def test_half_image_is_medium():
    assert extraction_confidence(_doc(signal_type=SignalType.MIXED, pages=_pages(5, 5))) is Confidence.MEDIUM


def test_geospatial_identity_is_high():
    assert extraction_confidence(_doc(signal_type=SignalType.GEOSPATIAL, pages=[])) is Confidence.HIGH


def test_truncated_spreadsheet_is_medium():
    doc = _doc(signal_type=SignalType.SPREADSHEET, warnings=["sheet 'X' truncated at 200 rows"])
    assert extraction_confidence(doc) is Confidence.MEDIUM


def test_clean_docx_is_high():
    # docx has no pages; faithful text+tables -> high
    assert extraction_confidence(_doc(signal_type=SignalType.BORN_DIGITAL_REPORT, extractor="docx", pages=[])) is Confidence.HIGH
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_confidence.py -v`
Expected: FAIL with `ModuleNotFoundError`.

- [ ] **Step 3: Implement**

Create `tlddr/understand/confidence.py`:

```python
from tlddr.models import ExtractedDoc, SignalType, Confidence


def extraction_confidence(doc: ExtractedDoc) -> Confidence:
    # Identity-only datasets are complete for what they are.
    if doc.signal_type == SignalType.GEOSPATIAL:
        return Confidence.HIGH

    # Spreadsheets: truncation is the fidelity risk.
    if doc.signal_type == SignalType.SPREADSHEET:
        truncated = any("truncated" in w for w in doc.warnings)
        return Confidence.MEDIUM if truncated else Confidence.HIGH

    # Documents without pagination (docx) are extracted faithfully (prose + tables);
    # embedded-image warnings do not reduce text fidelity.
    if not doc.pages:
        return Confidence.HIGH

    # Paginated docs: proportion of text-bearing pages.
    text_fraction = sum(1 for p in doc.pages if p.has_text_layer) / len(doc.pages)
    if text_fraction >= 0.9:
        return Confidence.HIGH
    if text_fraction >= 0.5:
        return Confidence.MEDIUM
    return Confidence.LOW
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/test_confidence.py -v`
Expected: PASS (7 passed).

- [ ] **Step 5: Commit**

```bash
git add tlddr/understand/confidence.py tests/test_confidence.py
git commit -m "feat(understand): add proportional extraction-confidence derivation"
```

---

### Task 4: Triage derivation

**Files:**
- Create: `tlddr/understand/triage.py`
- Test: `tests/test_triage.py`

**Interfaces:**
- Consumes: `tlddr.models.Confidence`, `Triage`, `Question`.
- Produces: `tlddr.understand.triage.derive_triage(extraction: Confidence, interpretation: Confidence, questions: list[Question]) -> Triage` — the deterministic traffic-light rule.

- [ ] **Step 1: Write the failing test**

Create `tests/test_triage.py`:

```python
from tlddr.understand.triage import derive_triage
from tlddr.models import Confidence, Triage, Question


def q(blocking=False):
    return Question(id="q", raised_by="understand", question="?", blocking=blocking)


def test_both_high_no_questions_is_green():
    assert derive_triage(Confidence.HIGH, Confidence.HIGH, []) is Triage.GREEN


def test_any_low_is_red():
    assert derive_triage(Confidence.LOW, Confidence.HIGH, []) is Triage.RED
    assert derive_triage(Confidence.HIGH, Confidence.LOW, []) is Triage.RED


def test_blocking_question_is_red_even_if_confident():
    assert derive_triage(Confidence.HIGH, Confidence.HIGH, [q(blocking=True)]) is Triage.RED


def test_medium_is_amber():
    assert derive_triage(Confidence.HIGH, Confidence.MEDIUM, []) is Triage.AMBER


def test_open_nonblocking_question_is_amber():
    assert derive_triage(Confidence.HIGH, Confidence.HIGH, [q(blocking=False)]) is Triage.AMBER
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_triage.py -v`
Expected: FAIL with `ModuleNotFoundError`.

- [ ] **Step 3: Implement**

Create `tlddr/understand/triage.py`:

```python
from tlddr.models import Confidence, Triage, Question

_ORDER = {Confidence.LOW: 0, Confidence.MEDIUM: 1, Confidence.HIGH: 2}


def derive_triage(extraction: Confidence, interpretation: Confidence,
                  questions: list[Question]) -> Triage:
    if any(q.blocking for q in questions):
        return Triage.RED
    worst = min(extraction, interpretation, key=lambda c: _ORDER[c])
    if worst is Confidence.LOW:
        return Triage.RED
    if worst is Confidence.MEDIUM or questions:
        return Triage.AMBER
    return Triage.GREEN
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/test_triage.py -v`
Expected: PASS (5 passed).

- [ ] **Step 5: Commit**

```bash
git add tlddr/understand/triage.py tests/test_triage.py
git commit -m "feat(understand): add deterministic triage derivation"
```

---

### Task 5: Edge validation

**Files:**
- Create: `tlddr/understand/edges.py`
- Test: `tests/test_edges.py`

**Interfaces:**
- Consumes: `tlddr.models.Edge`.
- Produces: `tlddr.understand.edges.validate_edges(proposed: list[Edge], known_node_ids: set[str], source_id: str) -> tuple[list[Edge], list[Edge]]` — returns `(valid, dropped)`. An edge is dropped if its `target` is not in `known_node_ids` or equals `source_id` (no self-links). Order is preserved; duplicates (same target+relation) are de-duplicated, keeping the first.

- [ ] **Step 1: Write the failing test**

Create `tests/test_edges.py`:

```python
from tlddr.understand.edges import validate_edges
from tlddr.models import Edge, RelationType


def e(target, relation=RelationType.CORROBORATES):
    return Edge(target=target, relation=relation, rationale="r")


def test_drops_edge_to_unknown_target():
    valid, dropped = validate_edges([e("ghost")], known_node_ids={"a", "b"}, source_id="a")
    assert valid == []
    assert [d.target for d in dropped] == ["ghost"]


def test_keeps_edge_to_known_target():
    valid, dropped = validate_edges([e("b")], known_node_ids={"a", "b"}, source_id="a")
    assert [v.target for v in valid] == ["b"]
    assert dropped == []


def test_drops_self_link():
    valid, dropped = validate_edges([e("a")], known_node_ids={"a"}, source_id="a")
    assert valid == []
    assert [d.target for d in dropped] == ["a"]


def test_dedupes_same_target_and_relation():
    valid, _ = validate_edges([e("b"), e("b")], known_node_ids={"a", "b"}, source_id="a")
    assert len(valid) == 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_edges.py -v`
Expected: FAIL with `ModuleNotFoundError`.

- [ ] **Step 3: Implement**

Create `tlddr/understand/edges.py`:

```python
from tlddr.models import Edge


def validate_edges(proposed: list[Edge], known_node_ids: set[str],
                   source_id: str) -> tuple[list[Edge], list[Edge]]:
    valid: list[Edge] = []
    dropped: list[Edge] = []
    seen: set[tuple[str, str]] = set()
    for edge in proposed:
        if edge.target == source_id or edge.target not in known_node_ids:
            dropped.append(edge)
            continue
        key = (edge.target, edge.relation.value)
        if key in seen:
            continue
        seen.add(key)
        valid.append(edge)
    return valid, dropped
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/test_edges.py -v`
Expected: PASS (4 passed).

- [ ] **Step 5: Commit**

```bash
git add tlddr/understand/edges.py tests/test_edges.py
git commit -m "feat(understand): add edge validation with self-link and dup guards"
```

---

### Task 6: Node markdown rendering

**Files:**
- Create: `tlddr/understand/node_render.py`
- Test: `tests/test_node_render.py`

**Interfaces:**
- Consumes: `tlddr.models.Node`, `Edge`; `yaml`.
- Produces: `tlddr.understand.node_render.render_node_markdown(node: Node) -> str` — YAML frontmatter (the queryable overlay) + a readable body (title, description, `## Related` wikilinks by node id, `## Open questions` pointer to `_triage.md`). Wikilinks are `[[target_id]]` so Obsidian resolves them to `target_id.md`.

- [ ] **Step 1: Write the failing test**

Create `tests/test_node_render.py`:

```python
import yaml
from tlddr.understand.node_render import render_node_markdown
from tlddr.models import Node, Edge, RelationType, Confidence, Triage


def _node():
    return Node(
        id="a6", extracted_id="a6", title="A6 Cost-Benefit Analysis",
        doc_type="cost-benefit analysis", description="Walks through the CBA: net market benefits.",
        report_sections=[], confidence_extraction=Confidence.HIGH,
        confidence_interpretation=Confidence.MEDIUM, triage=Triage.AMBER,
        open_questions=["q-0007"],
        related=[Edge(target="a3-renewable-energy-zones", relation=RelationType.CORROBORATES,
                      rationale="shares REZ boundary data")],
    )


def test_frontmatter_is_parseable_and_carries_overlay():
    md = render_node_markdown(_node())
    assert md.startswith("---\n")
    fm = yaml.safe_load(md.split("---\n")[1])
    assert fm["extracted_id"] == "a6"
    assert fm["triage"] == "amber"
    assert fm["confidence_interpretation"] == "medium"
    assert fm["related"][0]["target"] == "a3-renewable-energy-zones"
    assert fm["related"][0]["relation"] == "corroborates"


def test_body_has_description_and_wikilink_and_question_pointer():
    md = render_node_markdown(_node())
    assert "net market benefits" in md
    assert "[[a3-renewable-energy-zones]]" in md
    assert "_triage.md" in md
    assert "q-0007" in md


def test_rationale_with_colon_survives_frontmatter():
    n = _node()
    n.related[0].rationale = "capacity figures: spec says 500MW"
    fm = yaml.safe_load(render_node_markdown(n).split("---\n")[1])
    assert fm["related"][0]["rationale"] == "capacity figures: spec says 500MW"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_node_render.py -v`
Expected: FAIL with `ModuleNotFoundError`.

- [ ] **Step 3: Implement**

Create `tlddr/understand/node_render.py`:

```python
import yaml
from tlddr.models import Node


def render_node_markdown(node: Node) -> str:
    frontmatter = {
        "id": node.id,
        "extracted_id": node.extracted_id,
        "doc_type": node.doc_type,
        "report_sections": node.report_sections,
        "confidence_extraction": node.confidence_extraction.value,
        "confidence_interpretation": node.confidence_interpretation.value,
        "triage": node.triage.value,
        "open_questions": node.open_questions,
        "related": [
            {"target": e.target, "relation": e.relation.value, "rationale": e.rationale}
            for e in node.related
        ],
    }
    fm = yaml.safe_dump(frontmatter, sort_keys=False, allow_unicode=True)

    body = [f"# {node.title}", "", node.description, ""]
    if node.related:
        body.append("## Related")
        for e in node.related:
            body.append(f"- [[{e.target}]] — {e.relation.value}: {e.rationale}")
        body.append("")
    if node.open_questions:
        body.append("## Open questions")
        body.append(f"See `_triage.md` ({', '.join(node.open_questions)}).")
        body.append("")

    return f"---\n{fm}---\n\n" + "\n".join(body)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/test_node_render.py -v`
Expected: PASS (3 passed).

- [ ] **Step 5: Commit**

```bash
git add tlddr/understand/node_render.py tests/test_node_render.py
git commit -m "feat(understand): render node markdown (frontmatter overlay + body)"
```

---

### Task 7: Index and triage rendering

**Files:**
- Create: `tlddr/understand/render.py`
- Test: `tests/test_render.py`

**Interfaces:**
- Consumes: `tlddr.models.Node`, `Question`, `Triage`.
- Produces:
  - `tlddr.understand.render.render_index(nodes: list[Node]) -> str` — a markdown table of all nodes (id wikilink, doc_type, triage), sorted by id.
  - `tlddr.understand.render.render_triage(nodes: list[Node], questions: list[Question]) -> str` — nodes grouped under Red / Amber / Green headings, then an `## Open questions` section listing each question with an `> answer:` line to fill in.

- [ ] **Step 1: Write the failing test**

Create `tests/test_render.py`:

```python
from tlddr.understand.render import render_index, render_triage
from tlddr.models import Node, Question, Confidence, Triage


def _node(id, triage):
    return Node(
        id=id, extracted_id=id, title=id.upper(), doc_type="report",
        description="d", confidence_extraction=Confidence.HIGH,
        confidence_interpretation=Confidence.HIGH if triage is Triage.GREEN else Confidence.MEDIUM,
        triage=triage,
    )


def test_index_lists_all_nodes_with_triage():
    md = render_index([_node("b", Triage.GREEN), _node("a", Triage.AMBER)])
    assert "[[a]]" in md and "[[b]]" in md
    assert "amber" in md and "green" in md
    # sorted by id: a before b
    assert md.index("[[a]]") < md.index("[[b]]")


def test_triage_groups_by_colour_and_lists_questions():
    nodes = [_node("a", Triage.RED), _node("b", Triage.GREEN)]
    questions = [Question(id="q-1", raised_by="understand", node_id="a",
                          question="Which pump is this curve for?")]
    md = render_triage(nodes, questions)
    assert "## Red" in md and "## Green" in md
    assert "[[a]]" in md
    assert "Which pump" in md
    assert "> answer:" in md
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_render.py -v`
Expected: FAIL with `ModuleNotFoundError`.

- [ ] **Step 3: Implement**

Create `tlddr/understand/render.py`:

```python
from tlddr.models import Node, Question, Triage

_GROUP_ORDER = [Triage.RED, Triage.AMBER, Triage.GREEN]
_GROUP_TITLE = {Triage.RED: "Red", Triage.AMBER: "Amber", Triage.GREEN: "Green"}


def render_index(nodes: list[Node]) -> str:
    lines = ["# Vault index", "", "| document | doc_type | triage |", "|----|----|----|"]
    for n in sorted(nodes, key=lambda n: n.id):
        lines.append(f"| [[{n.id}]] | {n.doc_type} | {n.triage.value} |")
    return "\n".join(lines) + "\n"


def render_triage(nodes: list[Node], questions: list[Question]) -> str:
    lines = ["# Triage", ""]
    by_triage = {t: [n for n in nodes if n.triage is t] for t in _GROUP_ORDER}
    for t in _GROUP_ORDER:
        group = sorted(by_triage[t], key=lambda n: n.id)
        lines.append(f"## {_GROUP_TITLE[t]} ({len(group)})")
        for n in group:
            lines.append(f"- [[{n.id}]] — {n.doc_type}")
        lines.append("")

    lines.append("## Open questions")
    if not questions:
        lines.append("None.")
    for q in questions:
        target = f" ([[{q.node_id}]])" if q.node_id else ""
        flag = " [blocking]" if q.blocking else ""
        lines.append(f"### {q.id}{flag}{target}")
        lines.append(q.question)
        lines.append("> answer:")
        lines.append("")
    return "\n".join(lines) + "\n"
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/test_render.py -v`
Expected: PASS (2 passed).

- [ ] **Step 5: Commit**

```bash
git add tlddr/understand/render.py tests/test_render.py
git commit -m "feat(understand): render vault index and triage surfaces"
```

---

### Task 8: Node assembly from enrichment

**Files:**
- Create: `tlddr/understand/commit.py`
- Test: `tests/test_commit.py`

**Interfaces:**
- Consumes: `ExtractedDoc`, `Node`, `Edge`, `Question`, `RelationType`, `Confidence`, `extraction_confidence`, `validate_edges`, `derive_triage`.
- Produces: `tlddr.understand.commit.build_node(enrichment: dict, doc: ExtractedDoc, known_node_ids: set[str]) -> tuple[Node, list[Edge], list[Question]]` — turns the agent's enrichment dict + the source `ExtractedDoc` into a validated `Node`, the list of dropped edges (for logging), and the parsed questions. Computes extraction confidence, validates edges, derives triage. The enrichment dict has keys: `doc_type` (str), `description` (str), `confidence_interpretation` (str), `related` (list of `{target, relation, rationale}`), `questions` (list of `{id, question, blocking?, section_id?}`).

- [ ] **Step 1: Write the failing test**

Create `tests/test_commit.py`:

```python
from tlddr.understand.commit import build_node
from tlddr.models import ExtractedDoc, SignalType, Triage, Confidence


def _doc(id="a6"):
    return ExtractedDoc(
        id=id, source_path=f"/x/{id}.pdf", source_sha256="a",
        signal_type=SignalType.BORN_DIGITAL_REPORT, raw_title="A6 Report",
        content="body", pages=[], warnings=[], extractor="docx",
    )


def _enrichment():
    return {
        "doc_type": "cost-benefit analysis",
        "description": "A CBA appendix.",
        "confidence_interpretation": "medium",
        "related": [
            {"target": "a3", "relation": "corroborates", "rationale": "shared data"},
            {"target": "ghost", "relation": "references", "rationale": "does not exist"},
        ],
        "questions": [{"id": "q-1", "question": "Which scenario?", "blocking": False}],
    }


def test_build_node_validates_edges_and_derives_triage():
    node, dropped, questions = build_node(_enrichment(), _doc(), known_node_ids={"a6", "a3"})
    assert node.extracted_id == "a6"
    assert node.title == "A6 Report"
    assert node.confidence_extraction is Confidence.HIGH      # clean docx
    assert node.confidence_interpretation is Confidence.MEDIUM
    assert [e.target for e in node.related] == ["a3"]          # ghost dropped
    assert [d.target for d in dropped] == ["ghost"]
    assert node.triage is Triage.AMBER                          # medium + a question
    assert node.open_questions == ["q-1"]
    assert questions[0].node_id == "a6"
    assert questions[0].raised_by == "understand"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_commit.py -v`
Expected: FAIL with `ModuleNotFoundError`.

- [ ] **Step 3: Implement**

Create `tlddr/understand/commit.py`:

```python
from tlddr.models import (
    ExtractedDoc, Node, Edge, Question, RelationType, Confidence,
)
from tlddr.understand.confidence import extraction_confidence
from tlddr.understand.edges import validate_edges
from tlddr.understand.triage import derive_triage


def build_node(enrichment: dict, doc: ExtractedDoc,
               known_node_ids: set[str]) -> tuple[Node, list[Edge], list[Question]]:
    proposed = [
        Edge(target=r["target"], relation=RelationType(r["relation"]), rationale=r["rationale"])
        for r in enrichment.get("related", [])
    ]
    valid, dropped = validate_edges(proposed, known_node_ids, source_id=doc.id)

    questions = [
        Question(
            id=q["id"], raised_by="understand", node_id=doc.id,
            section_id=q.get("section_id"), question=q["question"],
            blocking=q.get("blocking", False),
        )
        for q in enrichment.get("questions", [])
    ]

    ext_conf = extraction_confidence(doc)
    interp_conf = Confidence(enrichment["confidence_interpretation"])
    triage = derive_triage(ext_conf, interp_conf, questions)

    node = Node(
        id=doc.id,
        extracted_id=doc.id,
        title=doc.raw_title,
        doc_type=enrichment["doc_type"],
        description=enrichment["description"],
        confidence_extraction=ext_conf,
        confidence_interpretation=interp_conf,
        triage=triage,
        open_questions=[q.id for q in questions],
        related=valid,
    )
    return node, dropped, questions
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/test_commit.py -v`
Expected: PASS (1 passed).

- [ ] **Step 5: Commit**

```bash
git add tlddr/understand/commit.py tests/test_commit.py
git commit -m "feat(understand): assemble validated node from agent enrichment"
```

---

### Task 9: CLI subcommands

**Files:**
- Modify: `tlddr/cli.py`
- Test: `tests/test_understand_cli.py`

**Interfaces:**
- Consumes: `build_slice`, `build_node`, `render_node_markdown`, `render_index`, `render_triage`, `ExtractedDoc`, `Node`, `Question`.
- Produces (added to `tlddr/cli.py`):
  - `understand_slice(extracted_dir: Path, node_id: str) -> str` — load `extracted_dir/<id>.json`, return `build_slice`.
  - `understand_commit(enrichment_path: Path, extracted_dir: Path, out_dir: Path) -> Node` — load the enrichment JSON and the matching `ExtractedDoc`; known ids = every `*.json` stem in `extracted_dir`; build the node; write `out_dir/nodes/<id>.json` and append questions to `out_dir/questions.json`; print dropped edges; return the node.
  - `understand_render(work_dir: Path, vault_dir: Path) -> None` — load all `work_dir/nodes/*.json` and `work_dir/questions.json`; write `vault_dir/<id>.md` per node, plus `vault_dir/_index.md` and `vault_dir/_triage.md`.
  - Three argparse subcommands wired into `main`: `understand-slice`, `understand-commit`, `understand-render`.

- [ ] **Step 1: Write the failing test**

Create `tests/test_understand_cli.py`:

```python
import json
from pathlib import Path
from tlddr.cli import understand_slice, understand_commit, understand_render
from tlddr.models import ExtractedDoc, SignalType


def _write_doc(d: Path, id: str):
    doc = ExtractedDoc(
        id=id, source_path=f"/x/{id}.pdf", source_sha256="a",
        signal_type=SignalType.BORN_DIGITAL_REPORT, raw_title=f"{id} title",
        content="--- page 1 ---\nbody", pages=[], warnings=[], extractor="docx",
    )
    (d / f"{id}.json").write_text(doc.model_dump_json())


def test_slice_then_commit_then_render(tmp_path):
    extracted = tmp_path / "extracted"
    extracted.mkdir()
    _write_doc(extracted, "a6")
    _write_doc(extracted, "a3")

    # slice
    s = understand_slice(extracted, "a6")
    assert "a6 title" in s and "body" in s

    # commit (enrichment references a real node a3 and a ghost)
    enrichment = {
        "extracted_id": "a6", "doc_type": "cba", "description": "A CBA.",
        "confidence_interpretation": "high",
        "related": [{"target": "a3", "relation": "corroborates", "rationale": "x"},
                    {"target": "ghost", "relation": "references", "rationale": "y"}],
        "questions": [],
    }
    ep = tmp_path / "a6.enrichment.json"
    ep.write_text(json.dumps(enrichment))
    work = tmp_path / "work"
    node = understand_commit(ep, extracted, work)
    assert node.id == "a6"
    assert [e.target for e in node.related] == ["a3"]          # ghost dropped
    assert (work / "nodes" / "a6.json").exists()

    # render
    vault = tmp_path / "vault"
    understand_render(work, vault)
    assert (vault / "a6.md").exists()
    assert (vault / "_index.md").exists()
    assert (vault / "_triage.md").exists()
    assert "[[a3]]" in (vault / "a6.md").read_text()
    assert "a6" in (vault / "_index.md").read_text()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_understand_cli.py -v`
Expected: FAIL with `ImportError: cannot import name 'understand_slice'`.

- [ ] **Step 3: Implement — add to `tlddr/cli.py`**

Add these imports near the top of `tlddr/cli.py` (with the existing imports):

```python
import json
from tlddr.models import ExtractedDoc, Node, Question
from tlddr.understand.slice import build_slice
from tlddr.understand.commit import build_node
from tlddr.understand.node_render import render_node_markdown
from tlddr.understand.render import render_index, render_triage
```

Add these functions to `tlddr/cli.py` (before `main`):

```python
def _load_doc(extracted_dir: Path, node_id: str) -> ExtractedDoc:
    return ExtractedDoc.model_validate_json((extracted_dir / f"{node_id}.json").read_text())


def understand_slice(extracted_dir: Path, node_id: str) -> str:
    return build_slice(_load_doc(extracted_dir, node_id))


def understand_commit(enrichment_path: Path, extracted_dir: Path, out_dir: Path) -> Node:
    enrichment = json.loads(enrichment_path.read_text())
    doc = _load_doc(extracted_dir, enrichment["extracted_id"])
    known_ids = {p.stem for p in extracted_dir.glob("*.json")}

    node, dropped, questions = build_node(enrichment, doc, known_ids)

    nodes_dir = out_dir / "nodes"
    nodes_dir.mkdir(parents=True, exist_ok=True)
    (nodes_dir / f"{node.id}.json").write_text(node.model_dump_json(indent=2))

    questions_path = out_dir / "questions.json"
    existing = json.loads(questions_path.read_text()) if questions_path.exists() else []
    existing.extend(json.loads(q.model_dump_json()) for q in questions)
    questions_path.write_text(json.dumps(existing, indent=2))

    for d in dropped:
        print(f"dropped edge {node.id} -> {d.target} ({d.relation.value}): target not in node set")
    print(f"committed {node.id} [{node.triage.value}] ({len(node.related)} edges, {len(questions)} questions)")
    return node


def understand_render(work_dir: Path, vault_dir: Path) -> None:
    nodes = [Node.model_validate_json(p.read_text())
             for p in sorted((work_dir / "nodes").glob("*.json"))]
    questions_path = work_dir / "questions.json"
    questions = ([Question.model_validate(q) for q in json.loads(questions_path.read_text())]
                 if questions_path.exists() else [])

    vault_dir.mkdir(parents=True, exist_ok=True)
    for node in nodes:
        (vault_dir / f"{node.id}.md").write_text(render_node_markdown(node))
    (vault_dir / "_index.md").write_text(render_index(nodes))
    (vault_dir / "_triage.md").write_text(render_triage(nodes, questions))
    print(f"rendered {len(nodes)} nodes to {vault_dir}")
```

In `main`, add three subparsers alongside the existing `extract` one (after the `extract_cmd` block, before `args = parser.parse_args(argv)`):

```python
    slice_cmd = sub.add_parser("understand-slice", help="print the bounded slice for one document")
    slice_cmd.add_argument("--extracted", required=True, type=Path)
    slice_cmd.add_argument("--id", required=True)

    commit_cmd = sub.add_parser("understand-commit", help="assemble a validated node from agent enrichment")
    commit_cmd.add_argument("--enrichment", required=True, type=Path)
    commit_cmd.add_argument("--extracted", required=True, type=Path)
    commit_cmd.add_argument("--out", default=Path(".tlddr"), type=Path)

    render_cmd = sub.add_parser("understand-render", help="render the vault, index, and triage")
    render_cmd.add_argument("--work", default=Path(".tlddr"), type=Path)
    render_cmd.add_argument("--vault", default=Path("vault"), type=Path)
```

In `main`, extend the command dispatch (after the existing `if args.command == "extract":` block) with:

```python
    if args.command == "understand-slice":
        print(understand_slice(args.extracted, args.id))
        return 0
    if args.command == "understand-commit":
        understand_commit(args.enrichment, args.extracted, args.out)
        return 0
    if args.command == "understand-render":
        understand_render(args.work, args.vault)
        return 0
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `.venv/bin/pytest tests/test_understand_cli.py -v`
Expected: PASS (1 passed).

- [ ] **Step 5: Run the full suite**

Run: `.venv/bin/pytest -q`
Expected: all tests pass, output pristine.

- [ ] **Step 6: Commit**

```bash
git add tlddr/cli.py tests/test_understand_cli.py
git commit -m "feat(cli): add understand-slice / understand-commit / understand-render subcommands"
```

---

## Self-review

**Spec coverage (deterministic-toolkit scope; agent/SKILL.md run is the follow-on):**
- Reduce-in / bounded slice → Task 2 (`build_slice`, title + structure + warnings + capped sample). Covered.
- Node = overlay + pointer, no clone → Task 1 (`Node` has `extracted_id`, no content field) + Task 6 (body carries description, not source content). Covered.
- Extraction confidence script-derived, proportional → Task 3. Covered.
- Interpretation confidence from the agent → Task 8 (read from enrichment). Covered.
- Triage deterministic rule → Task 4 (exact rule from the spec). Covered.
- Edges: machine-trust (drop unknown target), validation → Task 5 + Task 8. Covered.
- Relation vocabulary → Task 1 (`RelationType`). Covered.
- Vault outputs: node md, `_index.md`, `_triage.md` → Tasks 6, 7, 9. Covered.
- Quarantine questions, section-tied, `> answer:` surface → Tasks 1, 7, 8. Covered.
- Ordinal confidence, no false precision → Task 1 (string enums). Covered.
- Host-agent boundary (enrichment JSON in, deterministic out; no model calls) → Task 8/9 (enrichment is input). Covered.

**Deferred to later plans / the follow-on (intentionally not here):** `SKILL.md` authoring and the model-driven proving run; section-tagging against the profile (`report_sections` stays `[]`); the cross-doc edge *proposal* pass (agent judgment — this toolkit only *validates* proposed edges); contradiction-escalation; the content digest; auto-deep-read escalation; TurboVault coverage integration.

**Placeholder scan:** none — every step has complete code and a real assertion. No "TBD"/"similar to Task N"/"add validation".

**Type consistency:** `Confidence`, `Triage`, `RelationType`, `Edge`, `Question`, `Node` field names and the function signatures (`build_slice`, `extraction_confidence`, `derive_triage`, `validate_edges`, `render_node_markdown`, `render_index`, `render_triage`, `build_node`, and the three CLI functions) are used identically across tasks. Enum string values (`high`, `amber`, `corroborates`, ...) match between producers and assertions. The enrichment dict shape is identical in Tasks 8 and 9.

---

## Notes for the follow-on (SKILL.md + proving run)

- The skill loop per doc: `tlddr understand-slice` → agent comprehends + proposes edges + raises questions → write enrichment JSON → `tlddr understand-commit`. After all docs: `tlddr understand-render`, then add TurboVault to the vault and pull coverage to enrich `_triage.md`.
- The edge *proposal* is the agent seeing the index of all node descriptions at once (20 docs fit) — this toolkit only validates what the agent proposes.
- Proving gate: eyeball `vault/` + `_triage.md` and judge it a trustworthy map.
