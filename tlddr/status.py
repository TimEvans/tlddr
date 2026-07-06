from tlddr.runstate import STAGES
from tlddr.models import QuestionStatus

_STATUS_LABEL = {
    QuestionStatus.OPEN: "open",
    QuestionStatus.ACCEPTED: "caveats",
    QuestionStatus.REVISE_PENDING: "pending",
    QuestionStatus.REVISE_APPLIED: "applied",
}


def resume_point(state: dict | None) -> str:
    if not state:
        return "none"
    for s in STAGES:
        if state["stages"].get(s, {}).get("status") != "done":
            return s
    return "complete"


def _tokens_by_stage(bench_rows: list[dict]) -> dict[str, int]:
    totals: dict[str, int] = {}
    for r in bench_rows:
        totals[r.get("stage", "")] = totals.get(r.get("stage", ""), 0) + int(r.get("tokens", 0) or 0)
    return totals


def _quarantine_counts(questions: list) -> dict[str, int]:
    counts = {"open": 0, "caveats": 0, "pending": 0, "applied": 0}
    for q in questions:
        counts[_STATUS_LABEL[q.status]] += 1
    return counts


def render_status(state: dict | None, bench_rows: list[dict], questions: list) -> str:
    if not state:
        return "no run found in this base — quick start or configure."
    tok = _tokens_by_stage(bench_rows)
    q = _quarantine_counts(questions)
    cfg = state.get("config", {})
    lines = [f"run · preset: {cfg.get('preset', '?')} · corpus: {cfg.get('corpus', '?')}", ""]
    for s in STAGES:
        e = state["stages"].get(s, {"status": "pending", "rounds": 0})
        row = f"{s:<11}{e['status']:<9}{e.get('rounds', 0)} round(s)"
        if tok.get(s):
            row += f"   {tok[s]} tok"
        if s in ("verify", "review"):
            row += f"   quarantine: {q['open']} open, {q['applied']} applied, {q['caveats']} caveats"
        lines.append(row)
    lines.append("")
    lines.append(f"resume point: {resume_point(state)}")
    return "\n".join(lines)
