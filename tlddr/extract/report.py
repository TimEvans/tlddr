from collections import Counter
from tlddr.models import ExtractedDoc

# The report is a human-readable preview; the full content always lives in the
# per-doc JSON. We cap the excerpt (rather than removing it) because some
# extracted content is very large (e.g. spreadsheet dumps run to megabytes), and
# we flag when an excerpt was truncated so the report never looks deceptively
# complete.
EXCERPT_CHARS = 4000


def render_report(docs: list[ExtractedDoc]) -> str:
    lines: list[str] = []
    lines.append("# Extraction reconnaissance report")
    lines.append("")
    lines.append(f"{len(docs)} documents extracted.")
    lines.append("")

    if docs:
        lines.append("| id | signal_type | pages | warnings |")
        lines.append("|----|-------------|-------|----------|")
        for d in docs:
            lines.append(f"| {d.id} | {d.signal_type.value} | {len(d.pages)} | {len(d.warnings)} |")
        lines.append("")

    for d in docs:
        lines.append(f"## {d.id}")
        lines.append("")
        lines.append(f"- title: {d.raw_title}")
        lines.append(f"- source: {d.source_path}")
        lines.append(f"- sha256: {d.source_sha256[:12]}")
        lines.append(f"- signal_type: {d.signal_type.value}")
        lines.append(f"- extractor: {d.extractor}")
        method_counts = Counter(p.method.value for p in d.pages)
        if method_counts:
            summary = ", ".join(f"{m}: {n}" for m, n in sorted(method_counts.items()))
            lines.append(f"- page methods: {summary}")
        if d.warnings:
            lines.append("- warnings:")
            for w in d.warnings:
                lines.append(f"  - {w}")
        lines.append("")
        excerpt = d.content[:EXCERPT_CHARS]
        if excerpt:
            lines.append("```")
            lines.append(excerpt)
            lines.append("```")
            if len(d.content) > EXCERPT_CHARS:
                lines.append(
                    f"_excerpt truncated; full {len(d.content):,}-char content in "
                    f"extracted/{d.id}.json_"
                )
        lines.append("")

    return "\n".join(lines)
