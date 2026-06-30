def clean_cell(text: str) -> str:
    # Keep each table row on one line and avoid breaking the markdown table.
    return text.replace("|", "\\|").replace("\n", " ").strip()


def table_markdown(rows: list[list[str]]) -> str:
    cleaned = [[clean_cell(cell) for cell in row] for row in rows]
    if not cleaned:
        return ""
    width = len(cleaned[0])
    lines = ["| " + " | ".join(cleaned[0]) + " |"]
    lines.append("| " + " | ".join(["---"] * width) + " |")
    for row in cleaned[1:]:
        lines.append("| " + " | ".join(row) + " |")
    return "\n".join(lines)
