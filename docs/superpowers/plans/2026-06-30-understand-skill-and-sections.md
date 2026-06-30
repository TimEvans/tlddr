# Understand: Skill + Section-tagging + Proving Run — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the Understand stage run end-to-end — add section-tagging against a user-provided section structure, the holistic edge pass, coverage in triage, and the two `SKILL.md` procedures — then prove it over the 20-document corpus.

**Architecture:** The deterministic toolkit (`tlddr understand-*`) already exists and is tested. This slice adds (1) a Node-free `sections.py` module that loads/validates the canonical `sections.json` and validates section tags (machine-trust, mirroring `validate_edges`), (2) `--sections` wiring through `understand-commit` (validate + populate `report_sections`) and `understand-render` (section no-evidence + isolated-node coverage in `_triage.md`), (3) a `tlddr sections` command, and (4) two host-agent `SKILL.md` procedures — one that generates `sections.json` (agent interprets, user steers), one that drives the per-run loop. The model does comprehension/edges/section-tags; the CLI does everything deterministic.

**Tech Stack:** Python 3.14, pydantic, pytest, pyyaml. Host agent = whatever loads the skills. TurboVault (MCP) for graph coverage.

## Global Constraints

- Python 3.14; project venv at `.venv`. Run tests with `.venv/bin/pytest`.
- No emojis anywhere — code, comments, commit messages, skill prose (hard user rule).
- Conventional commits: `type(scope): description`.
- Work on branch `understand-skill-sections` (already checked out).
- **Machine-trust at the seams:** the model never writes an edge target or a section tag that the CLI has not verified against a known set. Unknown ids are dropped, not trusted.
- The Node is an overlay + `extracted_id` pointer; it never clones source content.
- Deterministic helpers are unit-tested Python; model judgment lives in `SKILL.md`, never in code.
- Spec: `docs/superpowers/specs/2026-06-30-understand-skill-and-sections.md`.

---

## File Structure

| File | Responsibility | Action |
|---|---|---|
| `tlddr/models.py` | add `Section` contract | Modify |
| `tlddr/understand/sections.py` | load/validate `sections.json`; validate section tags (Node-free) | Create |
| `tests/test_sections.py` | unit tests for the above | Create |
| `tlddr/cli.py` | `sections` command; `--sections` on commit/render; pass-through | Modify |
| `tlddr/understand/commit.py` | `build_node` validates + populates `report_sections` | Modify |
| `tests/test_commit.py` | update for new `build_node` arity + section tags | Modify |
| `tlddr/understand/render.py` | `section_coverage`, `isolated_nodes`; triage coverage blocks | Modify |
| `tests/test_render.py` | update for coverage rendering | Modify |
| `tests/test_understand_cli.py` | `--sections` end-to-end cases | Modify |
| `skills/generate-sections/SKILL.md` | procedure: raw section file → curated `sections.json` | Create |
| `skills/understand/SKILL.md` | procedure: the per-run Understand loop | Create |
| `.tlddr/sections.json` | the curated sections for the corpus (proving artifact) | Generate |

---

## Task 1: `Section` model + `sections.py` loader/validator/tag-validator

**Files:**
- Modify: `tlddr/models.py` (add `Section` after `Edge`)
- Create: `tlddr/understand/sections.py`
- Test: `tests/test_sections.py`

**Interfaces:**
- Produces:
  - `Section(BaseModel)` with `id: str`, `title: str`, `parent: str | None = None`
  - `load_sections(path: Path) -> list[Section]` — raises `ValueError` on duplicate ids or unknown parent refs
  - `section_ids(sections: list[Section]) -> set[str]`
  - `validate_section_tags(tags: list[str], known_ids: set[str]) -> tuple[list[str], list[str]]` — returns `(valid_unique_in_order, dropped_unknown)`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_sections.py`:

```python
import json
import pytest
from pathlib import Path
from tlddr.understand.sections import load_sections, section_ids, validate_section_tags
from tlddr.models import Section


def _write(tmp_path: Path, data) -> Path:
    p = tmp_path / "sections.json"
    p.write_text(json.dumps(data))
    return p


def test_load_sections_preserves_fields_and_parent(tmp_path):
    p = _write(tmp_path, [
        {"id": "permitting-environmental", "title": "Permitting and Environmental review"},
        {"id": "key-technology", "title": "Key Technology"},
        {"id": "key-technology-type-1", "title": "Technology type 1", "parent": "key-technology"},
    ])
    sections = load_sections(p)
    assert [s.id for s in sections] == [
        "permitting-environmental", "key-technology", "key-technology-type-1"]
    assert sections[2].parent == "key-technology"
    assert sections[0].parent is None


def test_load_sections_rejects_duplicate_ids(tmp_path):
    p = _write(tmp_path, [
        {"id": "a", "title": "A"},
        {"id": "a", "title": "A again"},
    ])
    with pytest.raises(ValueError, match="duplicate"):
        load_sections(p)


def test_load_sections_rejects_unknown_parent(tmp_path):
    p = _write(tmp_path, [{"id": "child", "title": "Child", "parent": "ghost"}])
    with pytest.raises(ValueError, match="parent"):
        load_sections(p)


def test_section_ids_returns_the_id_set(tmp_path):
    sections = [Section(id="a", title="A"), Section(id="b", title="B")]
    assert section_ids(sections) == {"a", "b"}


def test_validate_section_tags_keeps_known_drops_unknown_dedupes():
    known = {"a", "b", "c"}
    valid, dropped = validate_section_tags(["b", "ghost", "a", "b"], known)
    assert valid == ["b", "a"]          # known, unique, in order
    assert dropped == ["ghost"]         # unknown reported once
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.venv/bin/pytest tests/test_sections.py -v`
Expected: FAIL — `ModuleNotFoundError: tlddr.understand.sections` (and `ImportError` for `Section`).

- [ ] **Step 3: Add the `Section` model**

In `tlddr/models.py`, add after the `Edge` class (around line 70):

```python
class Section(BaseModel):
    id: str
    title: str
    parent: str | None = None
```

- [ ] **Step 4: Implement `sections.py`**

Create `tlddr/understand/sections.py`:

```python
import json
from pathlib import Path
from tlddr.models import Section


def load_sections(path: Path) -> list[Section]:
    raw = json.loads(Path(path).read_text())
    sections = [Section.model_validate(item) for item in raw]

    ids = [s.id for s in sections]
    if len(ids) != len(set(ids)):
        raise ValueError("sections.json has duplicate section ids")

    known = set(ids)
    for s in sections:
        if s.parent is not None and s.parent not in known:
            raise ValueError(
                f"section '{s.id}' references unknown parent '{s.parent}'")
    return sections


def section_ids(sections: list[Section]) -> set[str]:
    return {s.id for s in sections}


def validate_section_tags(tags: list[str],
                          known_ids: set[str]) -> tuple[list[str], list[str]]:
    valid: list[str] = []
    dropped: list[str] = []
    seen: set[str] = set()
    for tag in tags:
        if tag not in known_ids:
            dropped.append(tag)
            continue
        if tag in seen:
            continue
        seen.add(tag)
        valid.append(tag)
    return valid, dropped
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `.venv/bin/pytest tests/test_sections.py -v`
Expected: PASS (5 tests).

- [ ] **Step 6: Commit**

```bash
git add tlddr/models.py tlddr/understand/sections.py tests/test_sections.py
git commit -m "feat(understand): add Section model and sections loader/validator"
```

---

## Task 2: `tlddr sections` command — load, validate, print the canonical list

**Files:**
- Modify: `tlddr/cli.py` (import, `understand_sections`, subparser, dispatch)
- Test: `tests/test_understand_cli.py` (add cases)

**Interfaces:**
- Consumes: `load_sections` (Task 1)
- Produces: `understand_sections(sections_path: Path) -> list[Section]` — prints one line per section (`id — title`, two-space indent for children) and returns the list. Used by the generate skill (validation gate) and the run skill (canonical read).

- [ ] **Step 1: Write the failing test**

Add to `tests/test_understand_cli.py`:

```python
def test_sections_command_prints_and_validates(tmp_path, capsys):
    from tlddr.cli import understand_sections
    p = tmp_path / "sections.json"
    p.write_text(json.dumps([
        {"id": "key-technology", "title": "Key Technology"},
        {"id": "key-technology-type-1", "title": "Technology type 1",
         "parent": "key-technology"},
    ]))
    sections = understand_sections(p)
    assert [s.id for s in sections] == ["key-technology", "key-technology-type-1"]
    out = capsys.readouterr().out
    assert "key-technology — Key Technology" in out
    assert "  key-technology-type-1 — Technology type 1" in out  # indented child
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `.venv/bin/pytest tests/test_understand_cli.py::test_sections_command_prints_and_validates -v`
Expected: FAIL — `ImportError: cannot import name 'understand_sections'`.

- [ ] **Step 3: Implement the command**

In `tlddr/cli.py`, add to the imports near the top:

```python
from tlddr.models import ExtractedDoc, Node, Question, SignalType, Section
from tlddr.understand.sections import load_sections, section_ids
```

(Replace the existing `from tlddr.models import ExtractedDoc, Node, Question, SignalType` line with the first line above; add the second line beside the other `tlddr.understand` imports.)

Add the function after `understand_slice`:

```python
def understand_sections(sections_path: Path) -> list[Section]:
    sections = load_sections(sections_path)
    for s in sections:
        prefix = "  " if s.parent else ""
        print(f"{prefix}{s.id} — {s.title}")
    return sections
```

In `main`, add the subparser after the `slice_cmd` block:

```python
    sections_cmd = sub.add_parser("sections", help="load, validate, and print the section structure")
    sections_cmd.add_argument("--sections", required=True, type=Path)
```

And the dispatch after the `understand-slice` branch:

```python
    if args.command == "sections":
        understand_sections(args.sections)
        return 0
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `.venv/bin/pytest tests/test_understand_cli.py::test_sections_command_prints_and_validates -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add tlddr/cli.py tests/test_understand_cli.py
git commit -m "feat(cli): add tlddr sections command to print and validate sections.json"
```

---

## Task 3: `build_node` validates and populates `report_sections`

**Files:**
- Modify: `tlddr/understand/commit.py`
- Test: `tests/test_commit.py`

**Interfaces:**
- Consumes: `validate_section_tags` (Task 1)
- Produces (new signature): `build_node(enrichment: dict, doc: ExtractedDoc, known_node_ids: set[str], known_section_ids: set[str] = frozenset()) -> tuple[Node, list[Edge], list[str], list[Question]]` — the 4-tuple is `(node, dropped_edges, dropped_section_tags, questions)`. Reads `enrichment["report_sections"]` (default `[]`), validates against `known_section_ids`, sets `node.report_sections` to the valid tags.

- [ ] **Step 1: Update the test for the new arity and section tags**

In `tests/test_commit.py`, replace `_enrichment()` and `test_build_node_validates_edges_and_derives_triage` with:

```python
def _enrichment():
    return {
        "doc_type": "cost-benefit analysis",
        "description": "A CBA appendix.",
        "confidence_interpretation": "medium",
        "report_sections": ["financial-model", "ghost-section", "financial-model"],
        "related": [
            {"target": "a3", "relation": "corroborates", "rationale": "shared data"},
            {"target": "ghost", "relation": "references", "rationale": "does not exist"},
        ],
        "questions": [{"id": "q-1", "question": "Which scenario?", "blocking": False}],
    }


def test_build_node_validates_edges_sections_and_derives_triage():
    node, dropped_edges, dropped_sections, questions = build_node(
        _enrichment(), _doc(),
        known_node_ids={"a6", "a3"},
        known_section_ids={"financial-model", "energy-yield"},
    )
    assert node.extracted_id == "a6"
    assert node.title == "A6 Report"
    assert node.confidence_extraction is Confidence.HIGH      # clean docx
    assert node.confidence_interpretation is Confidence.MEDIUM
    assert [e.target for e in node.related] == ["a3"]          # ghost dropped
    assert [d.target for d in dropped_edges] == ["ghost"]
    assert node.report_sections == ["financial-model"]        # known, deduped
    assert dropped_sections == ["ghost-section"]              # unknown dropped
    assert node.triage is Triage.AMBER                          # medium + a question
    assert node.open_questions == ["q-1"]
    assert questions[0].node_id == "a6"
    assert questions[0].raised_by == "understand"
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `.venv/bin/pytest tests/test_commit.py -v`
Expected: FAIL — `ValueError: not enough values to unpack` (build_node still returns a 3-tuple) / `report_sections` not set.

- [ ] **Step 3: Update `build_node`**

In `tlddr/understand/commit.py`, update the imports and function:

```python
from tlddr.models import (
    ExtractedDoc, Node, Edge, Question, RelationType, Confidence,
)
from tlddr.understand.confidence import extraction_confidence
from tlddr.understand.edges import validate_edges
from tlddr.understand.sections import validate_section_tags
from tlddr.understand.triage import derive_triage


def build_node(enrichment: dict, doc: ExtractedDoc,
               known_node_ids: set[str],
               known_section_ids: set[str] = frozenset(),
               ) -> tuple[Node, list[Edge], list[str], list[Question]]:
    proposed = [
        Edge(target=r["target"], relation=RelationType(r["relation"]), rationale=r["rationale"])
        for r in enrichment.get("related", [])
    ]
    valid_edges, dropped_edges = validate_edges(proposed, known_node_ids, source_id=doc.id)

    valid_sections, dropped_sections = validate_section_tags(
        enrichment.get("report_sections", []), set(known_section_ids))

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
        report_sections=valid_sections,
        confidence_extraction=ext_conf,
        confidence_interpretation=interp_conf,
        triage=triage,
        open_questions=[q.id for q in questions],
        related=valid_edges,
    )
    return node, dropped_edges, dropped_sections, questions
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `.venv/bin/pytest tests/test_commit.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add tlddr/understand/commit.py tests/test_commit.py
git commit -m "feat(understand): validate and populate report_sections in build_node"
```

---

## Task 4: `understand-commit --sections` wiring

**Files:**
- Modify: `tlddr/cli.py` (`understand_commit`, subparser arg, dispatch)
- Test: `tests/test_understand_cli.py`

**Interfaces:**
- Consumes: `build_node` (4-tuple, Task 3), `load_sections` + `section_ids` (Task 1)
- Produces (new signature): `understand_commit(enrichment_path: Path, extracted_dir: Path, out_dir: Path, sections_path: Path | None = None) -> Node`. When `sections_path` is given, validates section tags against it; otherwise `known_section_ids` is empty (tags drop). Prints dropped section tags alongside dropped edges.

- [ ] **Step 1: Write the failing test**

Add to `tests/test_understand_cli.py`:

```python
def test_commit_validates_section_tags_against_spec(tmp_path):
    extracted = tmp_path / "extracted"
    extracted.mkdir()
    _write_doc(extracted, "a6")

    sections = tmp_path / "sections.json"
    sections.write_text(json.dumps([
        {"id": "financial-model", "title": "Financial Model"},
    ]))

    enrichment = {
        "extracted_id": "a6", "doc_type": "cba", "description": "d",
        "confidence_interpretation": "high", "related": [],
        "report_sections": ["financial-model", "ghost-section"],
        "questions": [],
    }
    ep = tmp_path / "a6.enrichment.json"
    ep.write_text(json.dumps(enrichment))
    work = tmp_path / "work"

    node = understand_commit(ep, extracted, work, sections)
    assert node.report_sections == ["financial-model"]   # ghost-section dropped
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `.venv/bin/pytest tests/test_understand_cli.py::test_commit_validates_section_tags_against_spec -v`
Expected: FAIL — `understand_commit()` takes 3 positional args, got 4.

- [ ] **Step 3: Update `understand_commit` and the CLI**

In `tlddr/cli.py`, replace `understand_commit`:

```python
def understand_commit(enrichment_path: Path, extracted_dir: Path, out_dir: Path,
                      sections_path: Path | None = None) -> Node:
    enrichment = json.loads(enrichment_path.read_text())
    doc = _load_doc(extracted_dir, enrichment["extracted_id"])
    known_ids = {p.stem for p in extracted_dir.glob("*.json")}
    known_section_ids = (section_ids(load_sections(sections_path))
                         if sections_path else frozenset())

    node, dropped_edges, dropped_sections, questions = build_node(
        enrichment, doc, known_ids, known_section_ids)

    nodes_dir = out_dir / "nodes"
    nodes_dir.mkdir(parents=True, exist_ok=True)
    (nodes_dir / f"{node.id}.json").write_text(node.model_dump_json(indent=2))

    questions_path = out_dir / "questions.json"
    existing = json.loads(questions_path.read_text()) if questions_path.exists() else []
    existing = [q for q in existing if q.get("node_id") != node.id]
    existing.extend(q.model_dump(mode="json") for q in questions)
    questions_path.write_text(json.dumps(existing, indent=2))

    for d in dropped_edges:
        print(f"dropped edge {node.id} -> {d.target} ({d.relation.value}): target not in node set")
    for t in dropped_sections:
        print(f"dropped section tag {node.id} -> {t}: not in sections.json")
    print(f"committed {node.id} [{node.triage.value}] "
          f"({len(node.related)} edges, {len(node.report_sections)} sections, "
          f"{len(questions)} questions)")
    return node
```

In `main`, add to `commit_cmd`:

```python
    commit_cmd.add_argument("--sections", type=Path, default=None)
```

And update the dispatch:

```python
    if args.command == "understand-commit":
        understand_commit(args.enrichment, args.extracted, args.out, args.sections)
        return 0
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `.venv/bin/pytest tests/test_understand_cli.py -v`
Expected: PASS (including the existing `test_slice_then_commit_then_render`, which calls `understand_commit` with 3 args — `sections_path` defaults to `None`).

- [ ] **Step 5: Commit**

```bash
git add tlddr/cli.py tests/test_understand_cli.py
git commit -m "feat(cli): wire --sections through understand-commit for tag validation"
```

---

## Task 5: render coverage — section no-evidence + isolated nodes in `_triage.md`

**Files:**
- Modify: `tlddr/understand/render.py`
- Test: `tests/test_render.py`

**Interfaces:**
- Consumes: `Section` (Task 1), `Node`, `Question`
- Produces:
  - `isolated_nodes(nodes: list[Node]) -> list[str]` — sorted ids of nodes with no outgoing edges and not the target of any edge
  - `section_coverage(nodes: list[Node], sections: list[Section]) -> dict[str, list[str]]` — section id → tagged node ids
  - `render_triage(nodes, questions, sections: list[Section] | None = None) -> str` — gains a `## Section coverage` block (only when `sections` given) and a `## Isolated documents` block, both placed before `## Open questions`

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_render.py` (extend the imports line first):

```python
from tlddr.understand.render import (
    render_index, render_triage, section_coverage, isolated_nodes,
)
from tlddr.models import Node, Question, Confidence, Triage, Section, Edge, RelationType
```

Add a helper and tests:

```python
def _node_tagged(id, triage, sections=(), related=()):
    return Node(
        id=id, extracted_id=id, title=id.upper(), doc_type="report",
        description="d", report_sections=list(sections),
        confidence_extraction=Confidence.HIGH,
        confidence_interpretation=Confidence.HIGH if triage is Triage.GREEN else Confidence.MEDIUM,
        triage=triage, related=list(related),
    )


def test_section_coverage_maps_sections_to_nodes():
    sections = [Section(id="fin", title="Financial Model"),
                Section(id="oem", title="Operation and Maintenance")]
    nodes = [_node_tagged("a", Triage.GREEN, sections=["fin"]),
             _node_tagged("b", Triage.GREEN, sections=["fin"])]
    cov = section_coverage(nodes, sections)
    assert cov == {"fin": ["a", "b"], "oem": []}


def test_isolated_nodes_finds_unconnected():
    edge = Edge(target="b", relation=RelationType.CORROBORATES, rationale="x")
    nodes = [_node_tagged("a", Triage.GREEN, related=[edge]),   # -> b
             _node_tagged("b", Triage.GREEN),                    # target of a
             _node_tagged("c", Triage.GREEN)]                    # isolated
    assert isolated_nodes(nodes) == ["c"]


def test_triage_renders_section_coverage_and_no_evidence():
    sections = [Section(id="fin", title="Financial Model"),
                Section(id="oem", title="Operation and Maintenance")]
    nodes = [_node_tagged("a", Triage.GREEN, sections=["fin"])]
    md = render_triage(nodes, [], sections)
    assert "## Section coverage" in md
    assert "Financial Model" in md and "[[a]]" in md
    assert "Operation and Maintenance" in md and "no evidence" in md.lower()
    # Open questions stays the final section
    assert md.index("## Section coverage") < md.index("## Open questions")
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.venv/bin/pytest tests/test_render.py -v`
Expected: FAIL — `ImportError: cannot import name 'section_coverage'`.

- [ ] **Step 3: Implement the render additions**

In `tlddr/understand/render.py`, update the import and add the functions; rewrite `render_triage` to insert the two blocks before Open questions:

```python
from tlddr.models import Node, Question, Triage, Section

_GROUP_ORDER = [Triage.RED, Triage.AMBER, Triage.GREEN]
_GROUP_TITLE = {Triage.RED: "Red", Triage.AMBER: "Amber", Triage.GREEN: "Green"}


def render_index(nodes: list[Node]) -> str:
    lines = ["# Vault index", "", "| document | doc_type | triage |", "|----|----|----|"]
    for n in sorted(nodes, key=lambda n: n.id):
        lines.append(f"| [[{n.id}]] | {n.doc_type} | {n.triage.value} |")
    return "\n".join(lines) + "\n"


def section_coverage(nodes: list[Node], sections: list[Section]) -> dict[str, list[str]]:
    coverage: dict[str, list[str]] = {s.id: [] for s in sections}
    for n in sorted(nodes, key=lambda n: n.id):
        for sid in n.report_sections:
            if sid in coverage:
                coverage[sid].append(n.id)
    return coverage


def isolated_nodes(nodes: list[Node]) -> list[str]:
    targets = {e.target for n in nodes for e in n.related}
    return sorted(n.id for n in nodes if not n.related and n.id not in targets)


def render_triage(nodes: list[Node], questions: list[Question],
                  sections: list[Section] | None = None) -> str:
    lines = ["# Triage", ""]
    by_triage = {t: [n for n in nodes if n.triage is t] for t in _GROUP_ORDER}
    for t in _GROUP_ORDER:
        group = sorted(by_triage[t], key=lambda n: n.id)
        lines.append(f"## {_GROUP_TITLE[t]} ({len(group)})")
        for n in group:
            lines.append(f"- [[{n.id}]] — {n.doc_type}")
        lines.append("")

    if sections is not None:
        coverage = section_coverage(nodes, sections)
        lines.append("## Section coverage")
        for s in sections:
            tagged = coverage[s.id]
            refs = ", ".join(f"[[{i}]]" for i in tagged) if tagged else "no evidence"
            lines.append(f"- {s.title} (`{s.id}`): {refs}")
        lines.append("")

    iso = isolated_nodes(nodes)
    lines.append("## Isolated documents")
    if iso:
        for i in iso:
            lines.append(f"- [[{i}]]")
    else:
        lines.append("None.")
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

- [ ] **Step 4: Run the tests to verify they pass**

Run: `.venv/bin/pytest tests/test_render.py -v`
Expected: PASS — including the three existing triage tests (the new blocks sit before `## Open questions`, so the `split("## Open questions")[1]` assertion still holds).

- [ ] **Step 5: Commit**

```bash
git add tlddr/understand/render.py tests/test_render.py
git commit -m "feat(understand): render section coverage and isolated nodes in triage"
```

---

## Task 6: `understand-render --sections` wiring

**Files:**
- Modify: `tlddr/cli.py` (`understand_render`, subparser arg, dispatch)
- Test: `tests/test_understand_cli.py`

**Interfaces:**
- Consumes: `render_triage` (Task 5), `load_sections` (Task 1)
- Produces (new signature): `understand_render(work_dir: Path, vault_dir: Path, sections_path: Path | None = None) -> None`. Loads sections when given and passes them to `render_triage`.

- [ ] **Step 1: Write the failing test**

Add to `tests/test_understand_cli.py`:

```python
def test_render_writes_section_coverage(tmp_path):
    extracted = tmp_path / "extracted"
    extracted.mkdir()
    _write_doc(extracted, "a6")

    sections = tmp_path / "sections.json"
    sections.write_text(json.dumps([
        {"id": "financial-model", "title": "Financial Model"},
        {"id": "energy-yield", "title": "Independent Energy Yield Assessment Summary"},
    ]))

    enrichment = {
        "extracted_id": "a6", "doc_type": "cba", "description": "d",
        "confidence_interpretation": "high", "related": [],
        "report_sections": ["financial-model"], "questions": [],
    }
    ep = tmp_path / "a6.enrichment.json"
    ep.write_text(json.dumps(enrichment))
    work = tmp_path / "work"
    understand_commit(ep, extracted, work, sections)

    vault = tmp_path / "vault"
    understand_render(work, vault, sections)
    triage = (vault / "_triage.md").read_text()
    assert "## Section coverage" in triage
    assert "Financial Model" in triage and "[[a6]]" in triage
    assert "no evidence" in triage.lower()   # energy-yield has none
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `.venv/bin/pytest tests/test_understand_cli.py::test_render_writes_section_coverage -v`
Expected: FAIL — `understand_render()` takes 2 positional args, got 3.

- [ ] **Step 3: Update `understand_render` and the CLI**

In `tlddr/cli.py`, replace `understand_render`:

```python
def understand_render(work_dir: Path, vault_dir: Path,
                      sections_path: Path | None = None) -> None:
    nodes = [Node.model_validate_json(p.read_text())
             for p in sorted((work_dir / "nodes").glob("*.json"))]
    questions_path = work_dir / "questions.json"
    questions = ([Question.model_validate(q) for q in json.loads(questions_path.read_text())]
                 if questions_path.exists() else [])
    sections = load_sections(sections_path) if sections_path else None

    vault_dir.mkdir(parents=True, exist_ok=True)
    for node in nodes:
        (vault_dir / f"{node.id}.md").write_text(render_node_markdown(node))
    (vault_dir / "_index.md").write_text(render_index(nodes))
    (vault_dir / "_triage.md").write_text(render_triage(nodes, questions, sections))
    print(f"rendered {len(nodes)} nodes to {vault_dir}")
```

In `main`, add to `render_cmd`:

```python
    render_cmd.add_argument("--sections", type=Path, default=None)
```

And update the dispatch:

```python
    if args.command == "understand-render":
        understand_render(args.work, args.vault, args.sections)
        return 0
```

- [ ] **Step 4: Run the full suite to verify nothing regressed**

Run: `.venv/bin/pytest -q`
Expected: PASS (all prior 54 + the new tests).

- [ ] **Step 5: Commit**

```bash
git add tlddr/cli.py tests/test_understand_cli.py
git commit -m "feat(cli): wire --sections through understand-render for coverage"
```

---

## Task 7: Author the `generate-sections` skill and produce the corpus `sections.json`

**REQUIRED SUB-SKILL:** Use superpowers:writing-skills to author the `SKILL.md`.

**Files:**
- Create: `skills/generate-sections/SKILL.md`
- Generate: `.tlddr/sections.json` (the curated corpus structure)

**Interfaces:**
- Consumes: `tlddr sections` (Task 2) as the validation gate
- Produces: a curated `sections.json` the Understand run consumes

- [ ] **Step 1: Author `skills/generate-sections/SKILL.md`**

Write a procedure with this exact content shape (frontmatter `name: generate-sections`, `description:` covering "turn a user-provided report section file into a curated sections.json"). The body must specify:

1. **Input:** the user's raw section file (a markdown headings file, e.g. `output_sections.md`).
2. **Interpret:** read every heading (H1–H6). For each, derive a stable `id` (kebab-case slug of the heading text; prefix child slugs with the parent slug to disambiguate generic names like `overview`), a `title` (the heading text verbatim), and a `parent` id for nested headings. Take the template at face value — every heading becomes a section, including placeholder slots like `Technology type 1/2`; vagueness is the agent's to interpret, not to drop.
3. **Propose + steer:** present the proposed structure to the user (the visual companion or a terminal table) and incorporate their corrections (rename, regroup, merge, drop) before writing anything.
4. **Materialize:** write the curated list to `sections.json` as a JSON array of `{id, title, parent?}` objects, in document order.
5. **Validate:** run `tlddr sections --sections <path>` and confirm it prints the structure with no error (duplicate ids and unknown parents fail loudly).

Note in the skill that regeneration is a deliberate, curated act — re-run it when the section file changes; it is not part of the per-run loop.

- [ ] **Step 2: Run the skill against the corpus section file**

Follow the skill to interpret `docs/test-reports/Engineering reports test/output_sections.md` into a proposed structure, present it to the user, incorporate steering, and write `.tlddr/sections.json`. The starting interpretation (before steering) is the 8-entry tree in the spec's "Data shapes" section.

- [ ] **Step 3: Validate the generated file**

Run: `.venv/bin/tlddr sections --sections .tlddr/sections.json`
Expected: prints each section (`id — title`, children indented), exits 0, no error.

- [ ] **Step 4: Commit the skill** (the `.tlddr/sections.json` artifact is gitignored)

```bash
git add skills/generate-sections/SKILL.md
git commit -m "feat(skill): add generate-sections procedure for curating sections.json"
```

---

## Task 8: Author the Understand run skill

**REQUIRED SUB-SKILL:** Use superpowers:writing-skills to author the `SKILL.md`.

**Files:**
- Create: `skills/understand/SKILL.md`

**Interfaces:**
- Consumes: the full CLI surface (`understand-slice`, `understand-commit --sections`, `understand-render --sections`, `sections`) and TurboVault (MCP)

- [ ] **Step 1: Author `skills/understand/SKILL.md`**

Write the per-run procedure (frontmatter `name: understand`, `description:` covering "drive the tlddr Understand stage over an extracted corpus to produce a linked, triaged vault"). The body must specify, as ordered phases:

- **Prereqs:** the extracted store exists (`.tlddr/extracted/*.json`, run `tlddr extract` if not) and a curated `sections.json` exists (run the `generate-sections` skill if not). Load the canonical sections once with `tlddr sections --sections .tlddr/sections.json`.
- **Phase 1 — Comprehend (per doc):** for each extracted id, run `tlddr understand-slice --extracted .tlddr/extracted --id <id>`, read the slice, and write `.tlddr/enrichment/<id>.json` with `extracted_id`, `doc_type`, `description` (a readable paragraph), `report_sections` (best-fit section ids from the loaded sections — multiple allowed, `[]` if none fit), `confidence_interpretation` (`high`/`medium`/`low` self-report), and `questions` (each `{id, question, blocking}`, ids like `q-0001`). **Do not propose edges yet.**
- **Phase 2 — Relate (holistic, once):** read every `.tlddr/enrichment/*.json`. Treat that set as the index of all document descriptions and propose typed edges across the whole corpus, adding a `related` list (`{target, relation, rationale}`) to each enrichment file. `relation` is one of `contradicts|supersedes|corroborates|references|same_subject|input_to`. Only link to ids that exist.
- **Phase 3 — Commit + Render:** for each enrichment file run `tlddr understand-commit --enrichment .tlddr/enrichment/<id>.json --extracted .tlddr/extracted --out .tlddr --sections .tlddr/sections.json`; then once run `tlddr understand-render --work .tlddr --vault vault --sections .tlddr/sections.json`.
- **Phase 4 — Coverage:** add `vault/` to TurboVault, explore isolation / thin clusters / hubs, and write the findings **into `vault/_triage.md`** as a coverage layer beneath the deterministic backbone (do not overwrite the rendered sections; append observations such as isolated documents the confidence signals missed).
- **Proving gate:** stop and ask the user to eyeball `vault/` + `vault/_triage.md` and judge it a trustworthy map.

State the deterministic/agent boundary explicitly: the CLI validates and renders; the agent supplies description, section tags, interpretation-confidence, questions, and edges; machine-trust means unknown edge targets and section tags are dropped by the CLI.

- [ ] **Step 2: Verify the documented commands match the CLI surface**

Run: `.venv/bin/tlddr --help` and `.venv/bin/tlddr understand-commit --help` and `.venv/bin/tlddr understand-render --help`
Expected: every command and flag the skill references exists with the documented name (`--sections` present on commit and render). Fix any drift in the skill prose.

- [ ] **Step 3: Commit**

```bash
git add skills/understand/SKILL.md
git commit -m "feat(skill): add Understand run procedure driving the tlddr CLI"
```

---

## Task 9: The proving run

**Files:** none (execution + human gate). Produces `vault/` and `vault/_triage.md`.

This task is agent-driven and ends at a human judgment, not a unit test. Do not mark it complete yourself — the user owns the gate.

- [ ] **Step 1: Ensure the extracted store is current**

Run: `.venv/bin/tlddr extract --source "docs/test-reports/Engineering reports test" --out .tlddr`
Expected: 20 records written to `.tlddr/extracted/` (re-run is idempotent; KMZ/xlsx warnings are expected).

- [ ] **Step 2: Ensure `sections.json` exists**

Confirm `.tlddr/sections.json` exists and validates (`.venv/bin/tlddr sections --sections .tlddr/sections.json`). If not, run the `generate-sections` skill (Task 7).

- [ ] **Step 3: Run the Understand procedure over all 20 documents**

Follow `skills/understand/SKILL.md` end to end: comprehend each doc (Phase 1), the holistic edge pass (Phase 2), commit + render (Phase 3), TurboVault coverage (Phase 4). All 20 documents — the value is cross-document.

- [ ] **Step 4: Sanity-check the artifacts before handing to the user**

Run: `ls vault/ && head -40 vault/_triage.md && head -30 vault/_index.md`
Expected: one `vault/<id>.md` per document, `_index.md`, and `_triage.md` with triage groups, section coverage (some "no evidence" lines acceptable), isolated documents, and the agent coverage layer.

- [ ] **Step 5: Present to the user for the proving gate**

Ask the user to eyeball `vault/` + `vault/_triage.md` and judge whether it is a trustworthy map of the corpus (useful descriptions, sensible relationships, honest traffic-light, meaningful section coverage). This is the make-or-break. Capture the verdict and any fixes the user wants; do not self-certify.

---

## Self-Review

**Spec coverage:**
- D1 (full heading tree, every heading a fit-target) — Task 7 skill interpretation step; `Section.parent` carries nesting (Task 1).
- D2 (skill loads sections once) — Task 8 prereqs (`tlddr sections` load); slice unchanged.
- D3 (deferred commit, holistic edge pass) — Task 8 Phases 1–3 (no edges in Phase 1; edge pass in Phase 2; commit in Phase 3).
- D4 (deterministic backbone + agent coverage layer) — Tasks 5/6 (no-evidence + isolated in render) and Task 8 Phase 4 (agent writes into `_triage.md`).
- D5 (section-spec is user input; CLI validates tags at commit, no-evidence at render) — Tasks 3/4 (commit) and 5/6 (render).
- D6 (generate sub-step: agent interprets, user steers, materialize) — Task 7.
- `sections.json` shape, `report_sections` field — Tasks 1, 3.
- CLI changes (`--sections` on commit/render, shared loader, `tlddr sections`) — Tasks 1, 2, 4, 6.
- Proving run over all 20 — Task 9.
- Deferred items (digest, deep-read, contradiction edges) — correctly absent.

**Placeholder scan:** every code step shows complete code; the two skill-authoring tasks specify exact body content (phases, commands, fields) rather than "write the skill". No TBD/TODO.

**Type consistency:** `build_node` returns the 4-tuple `(Node, list[Edge], list[str], list[Question])` in Task 3 and is unpacked as such in Task 4. `render_triage(nodes, questions, sections=None)` defined in Task 5, called with that signature in Task 6. `load_sections`/`section_ids`/`validate_section_tags` signatures defined in Task 1 are used consistently in Tasks 2–6. `Section(id, title, parent)` consistent throughout.
