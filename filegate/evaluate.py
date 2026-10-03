"""Findings caught vs dollars, from decisions + your labels. Prints aggregates only.

Labels, either:
  findings.jsonl  {"id": "...", "files": ["path", ...]}   a finding is caught if ANY of its files is scanned
  labels.csv      path,label                                  every label=1 file counts as its own finding
Paths are relative to the scanned repo root.
"""
from __future__ import annotations

import csv, json
from collections import Counter, defaultdict

from .cost import file_cost


def load_findings(path: str) -> list[tuple[str, list[str]]]:
    if path.endswith(".csv"):
        with open(path, newline="") as fh:
            return [(r["path"], [r["path"]]) for r in csv.DictReader(fh) if str(r.get("label", "1")).strip() in ("1", "true", "True")]
    return [(x["id"], list(x["files"])) for x in map(json.loads, open(path))]


def evaluate(decisions: list[dict], findings: list[tuple[str, list[str]]], cfg: dict) -> dict:
    c = cfg["cost"]
    by = {d["path"]: d for d in decisions}
    routes = Counter(d["route"] for d in decisions)
    before = sum(file_cost(d, "full", c) for d in decisions if d["route"] != "excluded")
    after = sum(file_cost(d, d["route"], c) for d in decisions)
    by_kind = defaultdict(lambda: Counter())
    for d in decisions:
        by_kind[d.get("kind") or "-"][d["route"]] += 1

    def caught(routes_ok):
        n = 0
        missing = []
        for fid, files in findings:
            if any(by.get(p, {}).get("route") in routes_ok for p in files):
                n += 1
            else:
                missing.append(fid)
        return n, missing

    full_n, full_miss = caught({"full"})
    any_n, any_miss = caught({"full", "cheap"})
    unknown = sum(1 for _, files in findings if not any(p in by for p in files))
    return {
        "files": dict(routes),
        "files_by_kind": {k: dict(v) for k, v in by_kind.items()},
        "cost_all_full": round(before, 2),
        "cost_after": round(after, 2),
        "saved_pct": round(100 * (1 - after / before), 1) if before else 0.0,
        "findings": len(findings),
        "findings_with_unknown_files": unknown,
        "caught_by_full_model": full_n,
        "caught_by_full_or_cheap": any_n,
        "missed_entirely": any_miss[:50],
        "routed_only_to_cheap": sorted(set(full_miss) - set(any_miss))[:50],
    }
