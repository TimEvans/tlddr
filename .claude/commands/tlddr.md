---
description: Run or resume the tl-ddr pipeline — interactive launcher over extract/understand/draft/verify/review/assemble.
argument-hint: [stage] [--output <dir>] [--preset quick|careful]
---

# tlddr launcher

You are the front door to the tl-ddr pipeline. You are THIN: every deterministic
step is a `tlddr` CLI call; you only converse and hand off to stage skills for
work that needs judgment. Never inspect the base yourself to guess progress — ask
the CLI.

Args passed by the user: `$ARGUMENTS`

## 1. Establish state (deterministic)

Resolve the output base: if the user passed `--output <dir>`, use it; else default
to the current directory. Then run:

    .venv/bin/tlddr status --output <base>

Read its output. Its `resume point:` line is authoritative — do not infer state
any other way.

## 2. Open the state-aware fork

- **resume point is `none` (no run):** offer **Quick start (recommended)** or **Configure**.
- **a middle stage is pending (in-progress run):** offer **Resume at `<stage>` / Start over / Configure**.
- **resume point is `complete`:** offer **Re-open review / Re-run a stage / Start over / Configure**.

Present the options plainly (a short numbered list) and wait for the choice.

## 3. Gather configuration (deterministic resolution)

- **Quick start:** ask only for the corpus location (the one input that cannot be
  safely defaulted — never guess it). Then run:
      .venv/bin/tlddr config --preset quick --corpus <corpus> --output <base>
- **Configure:** walk the flat list — corpus, output, preset (`quick` (recommended)
  / `careful`), and any overrides the user wants (`--model`, `--effort`,
  `--interaction`, `--benchmark`). Then run `tlddr config` with those flags.

`tlddr config` writes `tlddr.toml`, initializes the run state, and prints the
resolved config. Read it back to the user in one line and confirm before running.

## 4. Run the pipeline (per resolved interaction style)

Run the stages in order from the resume point. For each stage, do the stage's work,
then record completion deterministically:

    .venv/bin/tlddr mark-stage <stage> --output <base>

Stage playbook:
- **extract** (deterministic): `.venv/bin/tlddr extract --source <corpus> --output <base>`
- **understand** (agentic): follow `skills/generate-sections/SKILL.md` if there is no
  `sections.json`, then `skills/understand/SKILL.md`; commit + render via the CLI.
- **draft** (agentic): follow `skills/draft/SKILL.md`.
- **verify** (agentic): follow `skills/draft-verify/SKILL.md`, then `tlddr draft-eval`.
- **review** (agentic, interactive): follow `skills/review/SKILL.md`.
- **assemble** (deterministic): `.venv/bin/tlddr assemble --output <base>`.

**Interaction style** (from the resolved config): `autonomous` → chain the stages
without pausing, surface the review queue at the end; `guided` → after each stage,
show `tlddr status` and confirm before the next.

## 5. Finish

End on `tlddr status` so the user sees the final per-stage summary (tokens, rounds,
quarantine). If `assemble` warned about unapplied revises or 3+ cycles, surface it.
