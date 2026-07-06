---
name: generate-sections
description: Use when a user-provided markdown headings file needs to be turned into a curated sections.json for an Understand run — including first-time setup and whenever the section file changes.
---

# generate-sections

## Overview

Turns a user-provided markdown headings file into the canonical `sections.json` that the Understand run keys off. This is a deliberate, curated act: run it once when setting up a corpus, and re-run it when the section file changes. It is not part of the per-run understanding loop.

## Output location

All paths below are relative to the run's output base, `$TLDDR_OUTPUT` (default
the current directory when unset). Set it once at the start of the run so every `tlddr`
command and file reference resolves under the same directory:

    export TLDDR_OUTPUT=<your-output-dir>   # e.g. output/Chevron-10K

Work artifacts live under `$TLDDR_OUTPUT/.tlddr/`, the rendered vault under
`$TLDDR_OUTPUT/vault/`, and the report under `$TLDDR_OUTPUT/report/`.

## Procedure

### 1. Input

Obtain the path to the user's raw section file — a markdown headings file (e.g. `output_sections.md`). All headings in the file (H1–H6) will become sections.

### 2. Interpret

Read every heading in document order. For each, derive:

- `id` — kebab-case slug of the heading text. Prefix child slugs with their parent's id to avoid collisions on generic names (e.g. `key-technology-overview`, not `overview`).
- `title` — the heading text verbatim.
- `parent` — the `id` of the nearest ancestor heading; omit for top-level headings.
- `guidance` — the body content that sits under the heading, captured verbatim until the next heading at the same or higher level. This includes all text, bullet lists, numbered lists, tables, and any other content between this heading and the next. A heading that has no body content (the next line is another heading, or it is the last heading in the file) gets `guidance: null`.

Rules for guidance capture:

- Do not invent guidance the user did not write.
- Do not flatten, summarise, or paraphrase a rich template — capture the body verbatim, preserving whitespace and list formatting.
- If the user's template has elaborate instructions or tables under a heading, those are the guidance for that section and must be preserved exactly.

Take the template at face value. Every heading becomes a section, including placeholder slots such as "Technology type 1" or "Technology type 2". Vagueness is the agent's to interpret, not to drop.

### 3. Propose and steer

Present the proposed structure as a readable list or table (id, title, parent). For sections with non-null guidance, show a brief indication (e.g. `[has guidance]`) so the user can verify the body was captured. Wait for the user's corrections — rename, regroup, merge, or drop. Incorporate all changes. Do not write the file until the user approves the structure.

### 4. Materialize

Write the curated list to `$TLDDR_OUTPUT/.tlddr/sections.json` as a JSON array in document order. Top-level entries use `{id, title}`; nested entries add `parent`; entries with body content add `guidance`.

```json
[
  {"id": "key-technology", "title": "Key Technology"},
  {
    "id": "key-technology-overview",
    "title": "Overview",
    "parent": "key-technology",
    "guidance": "Provide a concise overview of the technology, including its primary purpose and maturity level."
  },
  {
    "id": "key-technology-type-1",
    "title": "Technology type 1",
    "parent": "key-technology",
    "guidance": null
  }
]
```

Omit `guidance` entirely when it is null rather than writing `"guidance": null` — both are valid JSON but the omitted form is cleaner. Omit `parent` for top-level entries.

### 5. Validate

Run:

```
tlddr sections --sections "$TLDDR_OUTPUT/.tlddr/sections.json"
```

The command prints each section (`id — title`, children indented) and exits 0. Duplicate ids and unknown parent references fail loudly — fix the JSON and re-run until the output is clean.
