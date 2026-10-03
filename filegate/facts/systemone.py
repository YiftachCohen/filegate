"""Any self-hosted Jev-compatible decision server: POST {base_url}/v1/systemone.

Works with `opendecider serve`, Kev, Clef-flash or similar, as long as it runs on
infrastructure you operate. Request: {"state", "questions"} with yes/no ("noul")
questions. Accepted answer shapes: {"noul": p}, {"probability": p}, or
{"probabilities": {"true"|"yes": p, ...}}.
"""
from __future__ import annotations

import json, urllib.request

from . import state


def _prob(a: dict) -> float:
    if isinstance(a.get("noul"), (int, float)):
        return float(a["noul"])
    if isinstance(a.get("probability"), (int, float)):
        return float(a["probability"])
    probs = a.get("probabilities") or {}
    for k in ("true", "yes", "True", "Yes", "1"):
        if k in probs:
            return float(probs[k])
    raise ValueError(f"cannot read a yes-probability from answer {a!r}")


class SystemOneFacts:
    name = "systemone"

    def __init__(self, cfg: dict):
        self.url = cfg["systemone"]["base_url"].rstrip("/") + "/v1/systemone"
        self.timeout = float(cfg["systemone"].get("timeout_s", 30))
        self.qs = {
            kind: {k: {"type": "noul", "instructions": q["ask"]} for k, q in facts.items()}
            for kind, facts in cfg["facts"].items()
        }

    def answer(self, f: dict, kind: str) -> dict[str, float]:
        qs = self.qs.get(kind)
        if not qs:
            return {}
        body = json.dumps({"state": state(f), "questions": qs}).encode()
        req = urllib.request.Request(self.url, data=body, headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=self.timeout) as r:
            ans = json.load(r)["answers"]
        return {k: _prob(ans[k]) for k in qs}
