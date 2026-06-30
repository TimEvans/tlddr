---
name: generate-sections
description: Use when a user-provided markdown headings file needs to be turned into a curated sections.json for an Understand run — including first-time setup and whenever the section file changes.
---

# generate-sections

## Overview

Turns a user-provided markdown headings file into the canonical `sections.json` that the Understand run keys off. This is a deliberate, curated act: run it once when setting up a corpus, and re-run it when the section file changes. It is not part of the per-run understanding loop.

## Procedure

### 1. Input

Obtain the path to the user's raw section file — a markdown headings file (e.g. `output_sections.md`). All headings in the file (H1–H6) will become sections.

### 2. Interpret

Read every heading in document order. For each, derive:

- `id` — kebab-case slug of the heading text. Prefix child slugs with their parent's id to avoid collisions on generic names (e.g. `key-technology-overview`, not `overview`).
- `title` — the heading text verbatim.
- `parent` — the `id` of the nearest ancestor heading; omit for top-level headings.

Take the template at face value. Every heading becomes a section, including placeholder slots such as "Technology type 1" or "Technology type 2". Vagueness is the agent's to interpret, not to drop.

### 3. Propose and steer

Present the proposed structure as a readable list or table (id, title, parent). Wait for the user's corrections — rename, regroup, merge, or drop. Incorporate all changes. Do not write the file until the user approves the structure.

### 4. Materialize

Write the curated list to `sections.json` as a JSON array in document order. Top-level entries use `{id, title}`; nested entries add `parent`.

```json
[
  {"id": "key-technology", "title": "Key Technology"},
  {"id": "key-technology-overview", "title": "Overview", "parent": "key-technology"},
  {"id": "key-technology-type-1", "title": "Technology type 1", "parent": "key-technology"}
]
```

### 5. Validate

Run:

```
tlddr sections --sections <path-to-sections.json>
```

The command prints each section (`id — title`, children indented) and exits 0. Duplicate ids and unknown parent references fail loudly — fix the JSON and re-run until the output is clean.
