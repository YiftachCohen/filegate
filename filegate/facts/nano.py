"""OpenDecider-Nano (Apache-2.0, ~0.4B encoder) answering the narrow facts on CPU.

Loads from models_dir only (run `filegate fetch-models --with nano` once, where
there is internet). Never downloads at scan time.
"""
from __future__ import annotations

import os
from pathlib import Path

from . import state


class NanoFacts:
    name = "nano"

    def __init__(self, cfg: dict):
        os.environ.setdefault("HF_HUB_OFFLINE", "1")
        try:
            from opendecider import load
        except ImportError as e:
            raise SystemExit("backend 'nano' needs: pip install 'filegate[nano]'") from e
        path = Path(cfg["models_dir"]) / cfg["nano"]["path"]
        if not (path / "opendecider.json").exists():
            raise SystemExit(f"no OpenDecider-Nano at {path}; run `filegate fetch-models --with nano` first")
        self.model = load(str(path), device="cpu")
        self.model.impl.max_len = int(cfg["nano"]["max_len"])
        self.qs = {
            kind: {k: {"type": "noul", "instructions": q["ask"]} for k, q in facts.items()}
            for kind, facts in cfg["facts"].items()
        }

    def answer(self, f: dict, kind: str) -> dict[str, float]:
        qs = self.qs.get(kind)
        if not qs:
            return {}
        a = self.model.system_one(state(f), qs)["answers"]
        return {k: float(a[k]["noul"]) for k in qs}
