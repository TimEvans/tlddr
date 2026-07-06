import tomllib
from pathlib import Path

PRESETS = {
    "quick":   {"model": "sonnet", "effort": "medium", "interaction": "autonomous"},
    "careful": {"model": "opus",   "effort": "high",   "interaction": "guided"},
}
_DEFAULTS = {"model": "sonnet", "effort": "medium", "interaction": "autonomous",
             "benchmark": False}
_AXES = ["model", "effort", "interaction", "benchmark"]


def resolve_config(preset: str | None, overrides: dict, toml_cfg: dict) -> dict:
    """Precedence (highest first): explicit override > toml [overrides] > preset > default."""
    cfg = dict(_DEFAULTS)
    if preset and preset in PRESETS:
        cfg.update(PRESETS[preset])
    cfg.update({k: v for k, v in toml_cfg.get("overrides", {}).items() if k in _AXES})
    cfg.update({k: v for k, v in overrides.items() if k in _AXES and v is not None})
    cfg["preset"] = preset or toml_cfg.get("preset")
    for key in ("corpus", "output"):
        if overrides.get(key) is not None:
            cfg[key] = overrides[key]
        elif key in toml_cfg:
            cfg[key] = toml_cfg[key]
    return cfg


def read_toml(path: Path) -> dict:
    if not Path(path).exists():
        return {}
    return tomllib.loads(Path(path).read_text())


def _fmt(v) -> str:
    if isinstance(v, bool):
        return "true" if v else "false"
    return f'"{v}"'


def write_toml(path: Path, cfg: dict) -> None:
    """Emit the flat launcher schema (top-level scalars + an [overrides] table).
    Hand-rolled for this known shape; no third-party TOML writer needed."""
    top = [f"{k} = {_fmt(v)}" for k, v in cfg.items() if k != "overrides"]
    lines = list(top)
    if cfg.get("overrides"):
        lines.append("")
        lines.append("[overrides]")
        lines += [f"{k} = {_fmt(v)}" for k, v in cfg["overrides"].items()]
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text("\n".join(lines) + "\n")
