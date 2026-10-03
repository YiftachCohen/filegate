"""Deterministic facts: each configured regex either matches the file head (1.0) or not (0.0)."""
from __future__ import annotations

import re


class RegexFacts:
    name = "regex"

    def __init__(self, cfg: dict):
        self.rx = {
            kind: {k: re.compile(q["regex"], re.I) for k, q in facts.items() if q.get("regex")}
            for kind, facts in cfg["facts"].items()
        }

    def answer(self, f: dict, kind: str) -> dict[str, float]:
        t = f.get("text", "")
        return {k: float(bool(rx.search(t))) for k, rx in self.rx.get(kind, {}).items()}
