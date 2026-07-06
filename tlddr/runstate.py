import hashlib
import json
from pathlib import Path

STAGES = ["extract", "understand", "draft", "verify", "review", "assemble"]


def corpus_fingerprint(corpus_dir: Path) -> str:
    """Cheap, deterministic content-ish fingerprint: sha256 over sorted
    '<relpath>:<size>' for every file under corpus_dir. Path+size (no mtime) is
    enough for a 'corpus changed since this run' warning; full content hashing is
    a documented later upgrade."""
    corpus_dir = Path(corpus_dir)
    entries = sorted(
        f"{p.relative_to(corpus_dir).as_posix()}:{p.stat().st_size}"
        for p in corpus_dir.rglob("*") if p.is_file()
    )
    digest = hashlib.sha256("\n".join(entries).encode()).hexdigest()
    return f"sha256:{digest}"


def _blank(config: dict, fingerprint: str) -> dict:
    return {
        "config": config,
        "corpus_fingerprint": fingerprint,
        "stages": {s: {"status": "pending", "rounds": 0} for s in STAGES},
    }


def init_state(state_path: Path, config: dict, fingerprint: str) -> dict:
    state = _blank(config, fingerprint)
    state_path.parent.mkdir(parents=True, exist_ok=True)
    state_path.write_text(json.dumps(state, indent=2))
    return state


def load_state(state_path: Path) -> dict | None:
    if not state_path.exists():
        return None
    return json.loads(state_path.read_text())


def update_config(state_path: Path, config: dict, fingerprint: str) -> dict:
    """Reconfigure a run's config in place. If there is no existing manifest,
    or the corpus fingerprint changed (a different corpus is a fresh run),
    fall back to init_state (which resets every stage to pending). Otherwise
    update the config block and fingerprint but leave `stages` untouched, so
    reconfiguring an in-progress run does not wipe recorded progress."""
    existing = load_state(state_path)
    if existing is None or existing.get("corpus_fingerprint") != fingerprint:
        return init_state(state_path, config, fingerprint)
    existing["config"] = config
    existing["corpus_fingerprint"] = fingerprint
    state_path.parent.mkdir(parents=True, exist_ok=True)
    state_path.write_text(json.dumps(existing, indent=2))
    return existing


def mark_stage(state_path: Path, stage: str, now: str) -> dict:
    state = load_state(state_path) or _blank({}, "")
    entry = state["stages"].setdefault(stage, {"status": "pending", "rounds": 0})
    entry["status"] = "done"
    entry["rounds"] = entry.get("rounds", 0) + 1
    entry["updated"] = now
    state_path.parent.mkdir(parents=True, exist_ok=True)
    state_path.write_text(json.dumps(state, indent=2))
    return state
