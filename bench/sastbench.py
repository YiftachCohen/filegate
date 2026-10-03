#!/usr/bin/env python3
"""Reproduce the public proxy numbers with filegate itself.

    python bench/sastbench.py --sastbench sastbench-v0.1-original.json [--config C] [--limit N]
    python bench/sastbench.py --monorepo grafana/grafana@<sha> --monorepo getsentry/sentry@<sha> [--config C]

SastBench (arXiv:2601.02941) is not redistributed here; get the JSON from its authors.
Its true positives are CVE-fix commits. For each repo we take the TP commit with the
most flagged files, download that snapshot from GitHub (public code, cached under
bench/.cache), run filegate on it and count findings caught. --monorepo measures
cost only (no labels). Nothing from this script is written into the repo.
"""
from __future__ import annotations

import argparse, http.client, io, json, shutil, subprocess, sys, tarfile, time, urllib.request
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT.parent))
from filegate import config, policy  # noqa: E402
from filegate.evaluate import evaluate  # noqa: E402
from filegate.facts import get  # noqa: E402
from filegate.inventory import scan  # noqa: E402

CACHE = ROOT / ".cache"


def download(url: str, tries: int = 4) -> bytes:
    """curl when available (more robust behind proxies), else urllib; both retried."""
    for i in range(tries):
        try:
            if shutil.which("curl"):
                return subprocess.run(["curl", "-sSfL", "--retry", "3", url], check=True, capture_output=True).stdout
            with urllib.request.urlopen(url, timeout=600) as r:
                return r.read()
        except (OSError, http.client.IncompleteRead, subprocess.CalledProcessError):
            if i == tries - 1:
                raise
            time.sleep(3 * (i + 1))


def snapshot(repo: str, commit: str) -> Path:
    d = CACHE / "repos" / f"{repo.replace('/', '__')}@{commit[:12]}"
    if (d / ".done").exists():
        return d
    d.mkdir(parents=True, exist_ok=True)
    data = download(f"https://codeload.github.com/{repo}/tar.gz/{commit}")
    with tarfile.open(fileobj=io.BytesIO(data), mode="r:gz") as tf:
        for m in tf:
            if not m.isfile():
                continue
            rel = m.name.split("/", 1)[1] if "/" in m.name else m.name
            out = (d / rel).resolve()
            if not str(out).startswith(str(d.resolve())):
                continue   # path traversal in archive
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_bytes(tf.extractfile(m).read())
    (d / ".done").touch()
    return d


def sastbench_targets(path: str):
    by = defaultdict(lambda: {"files": set(), "findings": []})
    for x in json.loads(Path(path).read_text()):
        if x.get("ground_truth") != "true_positive":
            continue
        files = sorted({l["file"] for l in x["to_analyzer"]["locations"]})
        e = by[(x["repo_name"], x["commit_hash"])]
        e["files"] |= set(files)
        e["findings"].append((x["finding_id"], files))
    best = {}
    for (repo, commit), e in by.items():
        if repo not in best or len(e["files"]) > len(best[repo][1]["files"]):
            best[repo] = (commit, e)
    return [(repo, c, e["findings"]) for repo, (c, e) in sorted(best.items())]


def run(cfg, backend, repo, commit, findings):
    d = snapshot(repo, commit)
    decisions = [policy.route(f, cfg, backend) for f in scan(d, cfg["models_dir"])]
    return evaluate(decisions, findings, cfg)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--config")
    ap.add_argument("--sastbench")
    ap.add_argument("--monorepo", action="append", default=[], help="owner/name@sha")
    ap.add_argument("--limit", type=int)
    a = ap.parse_args()
    cfg = config.load(a.config)
    backend = get(cfg)
    tot = defaultdict(float)
    if a.sastbench:
        targets = sastbench_targets(a.sastbench)[: a.limit]
        for i, (repo, commit, findings) in enumerate(targets):
            r = run(cfg, backend, repo, commit, findings)
            for k in ("cost_all_full", "cost_after", "findings", "caught_by_full_model", "caught_by_full_or_cheap"):
                tot[k] += r[k]
            print(f"[{i + 1}/{len(targets)}] {repo}: full {r['caught_by_full_model']}/{r['findings']}, "
                  f"saved {r['saved_pct']}%", file=sys.stderr)
        print(json.dumps({
            "repos": len(targets), "backend": backend.name, "low_risk_route": cfg["policy"]["low_risk_route"],
            "findings": int(tot["findings"]),
            "caught_by_full_model": int(tot["caught_by_full_model"]),
            "caught_by_full_or_cheap": int(tot["caught_by_full_or_cheap"]),
            "saved_pct": round(100 * (1 - tot["cost_after"] / tot["cost_all_full"]), 1),
        }, indent=1))
    for spec in a.monorepo:
        repo, sha = spec.split("@")
        r = run(cfg, backend, repo, sha, [])
        print(json.dumps({"monorepo": repo, "files": r["files"], "cost_all_full": r["cost_all_full"],
                          "cost_after": r["cost_after"], "saved_pct": r["saved_pct"]}, indent=1))


if __name__ == "__main__":
    main()
