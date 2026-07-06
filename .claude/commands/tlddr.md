---
description: Run or resume the tl-ddr pipeline — one launcher with verbs (extract/understand/draft/verify/assemble/review) plus status and resume.
argument-hint: [verb] [--output <dir>] [--preset quick|careful]
---

# tlddr launcher

You are the front door to the tl-ddr pipeline: a single `/tlddr` command with a small
family of verbs. You are THIN — every deterministic step is a `tlddr` CLI call, and the
judgment stages are handed to the matching `skills/*/SKILL.md`; the user never needs to
know which is which. Never inspect the base to guess progress — ask `tlddr status`.

Args passed by the user: `$ARGUMENTS`. The first token, if it is a known verb, is the
VERB; the rest are flags (`--output`, `--preset`, …).

## Dispatch

Resolve the output base first: if `--output <dir>` was passed, use it; otherwise the
current directory. Then branch on the first token of `$ARGUMENTS`:

- **no verb (bare `/tlddr`)** → the interactive launcher, section **A**.
- **`status`** → run `.venv/bin/tlddr status --output <base>`, show it, stop.
- **`resume`** → run `tlddr status`, then run every stage from the reported `resume point:`
  through to the end, non-interactively (section **C**).
- **a stage verb** (`extract` / `understand` / `draft` / `verify` / `assemble` / `review`)
  → run just that one stage (section **B**), then stop.
- **anything else** → run `tlddr status` and list the valid verbs.

---

## A. Interactive launcher (bare `/tlddr`)

### 1. Establish state
Run `.venv/bin/tlddr status --output <base>`. Its `resume point:` line is authoritative.

### 2. State-aware fork
- **resume point `none`:** offer **Quick start (recommended)** or **Configure**.
- **a middle stage pending:** offer **Resume at `<stage>` / Start over / Configure**.
- **`complete`:** offer **Re-open review / Re-run a stage / Start over / Configure**.
Present a short numbered list and wait for the choice.

### 3. Gather configuration
- **Quick start:** ask only for the corpus location (the one input that cannot be safely
  defaulted — never guess it), then:
      .venv/bin/tlddr config --preset quick --corpus <corpus> --output <base>
- **Configure:** ask each of these as its own explicit question — do not skip any:
  **corpus**; **output** (where the run is written — its `.tlddr/`, `tlddr.toml`, and
  `report/` all land here; default is the current directory, but always surface the
  choice, never silently default it); **preset** (`quick` (recommended) / `careful`);
  and any overrides (`--model`, `--effort`, `--interaction`, `--benchmark`) — then run
  `tlddr config` with those flags. Each `tlddr config` call records exactly the
  flags it is given (it does not merge with a previous call's). For a pin that should
  persist across runs and preset changes, set it in `tlddr.toml`'s `[overrides]` table —
  that file is the sticky config layer, and its values win over the preset.

`tlddr config` writes `tlddr.toml`, initializes the run state (or updates it in place,
preserving stage progress, when reconfiguring the same corpus), and prints the resolved
config. Read it back in one line and confirm before running.

### 4. Run
Run the stages in order from the resume point (section **C**), honoring the resolved
**interaction style**: `autonomous` → chain the stages without pausing, surface the review
queue at the end; `guided` → after each stage, show `tlddr status` and confirm before the
next. Each stage's **Proving Gate** honors this: under `autonomous` a non-blocking gate
defers its findings to the end-of-run queue and continues, while a **blocking/red** gate (a
blocking open question, or an unsupported claim / contradiction) stops even under
`autonomous`.

### 5. Finish
End on `tlddr status`: rounds and quarantine counts, plus a per-stage token breakdown if
benchmarking was enabled (off by default, so tokens are often blank). Surface any
`assemble` warning about unapplied revises or 3+ cycles.

---

## B. Run one stage

A single-stage verb re-runs (or runs) just that stage against the existing run. It needs a
configured run: if there is no `tlddr.toml` / run state for the base, tell the user to run
bare `/tlddr` first. Otherwise, do the stage's work from the playbook (section **C**), then
`.venv/bin/tlddr mark-stage <stage> --output <base>`, then show `tlddr status`.

## C. Stage playbook

For each stage, do its work, then `.venv/bin/tlddr mark-stage <stage> --output <base>`:

- **extract:** `.venv/bin/tlddr extract --source <corpus> --output <base>`
- **understand:** follow `skills/generate-sections/SKILL.md` if there is no `sections.json`,
  then `skills/understand/SKILL.md`; commit + render via the CLI.
- **draft:** follow `skills/draft/SKILL.md`.
- **verify:** follow `skills/draft-verify/SKILL.md`, then `.venv/bin/tlddr draft-eval --output <base>`.
- **review:** follow `skills/review/SKILL.md` (the interactive answer loop).
- **assemble:** `.venv/bin/tlddr assemble --output <base>`.

`resume` runs this playbook for every stage from the resume point onward; a single-stage
verb runs exactly one entry.
