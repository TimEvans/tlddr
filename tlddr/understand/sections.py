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
