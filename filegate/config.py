"""Load the YAML config: package defaults, deep-merged with the user's file."""
from __future__ import annotations

from importlib import resources
from pathlib import Path

import yaml


def _merge(base: dict, over: dict) -> dict:
    out = dict(base)
    for k, v in (over or {}).items():
        out[k] = _merge(out[k], v) if isinstance(v, dict) and isinstance(out.get(k), dict) else v
    return out


def load(path: str | Path | None = None) -> dict:
    cfg = yaml.safe_load(resources.files("filegate").joinpath("default.yaml").read_text())
    root = Path.cwd()
    if path:
        p = Path(path)
        cfg = _merge(cfg, yaml.safe_load(p.read_text()) or {})
        root = p.resolve().parent
    md = Path(cfg["models_dir"])
    cfg["models_dir"] = str(md if md.is_absolute() else (root / md).resolve())
    return cfg
