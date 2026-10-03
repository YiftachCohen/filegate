"""Route every file: excluded | skip | cheap | full, with the reason."""
from __future__ import annotations

from . import rules
from .facts import risk


def route(f: dict, cfg: dict, backend) -> dict:
    """Decision record for one file. Never contains file content."""
    pol = cfg["policy"]
    low = pol["low_risk_route"]
    d = {"path": f["path"], "bytes": f["bytes"]}
    why = rules.excluded(f, cfg["excludes"])
    if why:
        return {**d, "route": "excluded", "level": None, "kind": None, "reason": why}
    lvl, why = rules.level(f)
    kind = rules.kind(f, lvl, why)
    d.update(level=lvl, kind=kind)
    if lvl <= 1:
        return {**d, "route": low, "reason": why}
    if kind is None or kind not in pol["gate_kinds"]:
        return {**d, "route": "full", "reason": why}
    answers = backend.answer(f, kind)
    score = risk(answers, cfg["facts"].get(kind, {}))
    t = pol["thresholds"].get(backend.name, {}).get(kind, 0.5)
    kf = cfg["facts"].get(kind, {})
    hit = [k for k, p in sorted(answers.items(), key=lambda kv: -kv[1])
           if p >= 0.5 and kf.get(k, {}).get("role") != "discount"][:3]
    disc = [k for k, p in answers.items() if p >= 0.5 and kf.get(k, {}).get("role") == "discount"]
    detail = (f"{why}; {backend.name} risk {score:.2f} vs {t:.2f}" + (f" ({', '.join(hit)})" if hit else "")
              + (f" [discounted: {', '.join(disc)}]" if disc else ""))
    return {**d, "route": "full" if score >= t else low, "score": round(score, 4),
            "facts": {k: round(v, 4) for k, v in answers.items()}, "reason": detail}
