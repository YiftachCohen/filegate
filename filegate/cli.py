"""filegate CLI.

  filegate fetch-models [--with linguist,nano,head] [--config C]   once, where there is internet
  filegate scan REPO [--config C] [--out decisions.jsonl]           offline
  filegate eval --decisions D --labels findings.jsonl|labels.csv [--config C]
  filegate train --repo PATH --labels labels.csv [--repo ... --labels ...] [--config C]
"""
from __future__ import annotations

import argparse, hashlib, json, sys, time, urllib.request
from pathlib import Path

from . import config, policy, rules
from .inventory import scan as inventory

# Pinned upstream revisions. Bump deliberately, re-run `filegate eval`, commit.
PINS = {
    "linguist": ("github-linguist/linguist", "5fbdfcb8133be2bed88bf3ce62b2335f50474525"),
    "nano": ("manjunathshiva/opendecider-nano", "beeeb640f3333aec4ef78ed3b7bd0605f973a590"),
    "head": ("Alibaba-NLP/gte-modernbert-base", "e7f32e3c00f91d699e8c43b53106206bcc72bb22"),
}
LOCAL = {"nano": "opendecider-nano", "head": "gte-modernbert-base"}


def _sha256_tree(d: Path) -> dict:
    return {str(p.relative_to(d)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(d.rglob("*")) if p.is_file() and ".cache" not in p.parts}


def _download(url: str, dest: Path, tries: int = 3) -> None:
    """Fetch to a temp file, check the length, then move into place."""
    for i in range(tries):
        try:
            with urllib.request.urlopen(url, timeout=60) as r:
                data = r.read()
                n = r.headers.get("Content-Length")
            if n is not None and int(n) != len(data):
                raise OSError(f"short read {len(data)}/{n}")
            tmp = dest.with_suffix(dest.suffix + ".part")
            tmp.write_bytes(data)
            tmp.replace(dest)
            return
        except OSError:
            if i == tries - 1:
                raise
            time.sleep(2 * (i + 1))


def cmd_fetch(a, cfg):
    md = Path(cfg["models_dir"])
    md.mkdir(parents=True, exist_ok=True)
    manifest = {}
    for what in a.with_.split(","):
        what = what.strip()
        if what == "linguist":
            repo, sha = PINS["linguist"]
            d = md / "linguist"
            d.mkdir(exist_ok=True)
            for name in ("languages", "vendor", "documentation"):
                _download(f"https://raw.githubusercontent.com/{repo}/{sha}/lib/linguist/{name}.yml", d / f"{name}.yml")
        elif what in ("nano", "head"):
            try:
                from huggingface_hub import snapshot_download
            except ImportError:
                sys.exit(f"fetching '{what}' needs: pip install 'filegate[{what}]'")
            repo, sha = PINS[what]
            d = md / LOCAL[what]
            snapshot_download(repo, revision=sha, local_dir=d)
        else:
            sys.exit(f"unknown model {what!r} (linguist | nano | head)")
        manifest[what] = {"source": PINS[what][0], "revision": PINS[what][1], "files": _sha256_tree(d)}
        print(f"fetched {what} -> {d}")
    old = json.loads((md / "MANIFEST.json").read_text()) if (md / "MANIFEST.json").exists() else {}
    (md / "MANIFEST.json").write_text(json.dumps({**old, **manifest}, indent=1))


def verify(cfg) -> None:
    """Refuse to run on model files that don't match the manifest written at fetch time."""
    md = Path(cfg["models_dir"])
    m = md / "MANIFEST.json"
    if not m.exists():
        return
    for what, entry in json.loads(m.read_text()).items():
        d = md / ("linguist" if what == "linguist" else LOCAL[what])
        if d.exists() and _sha256_tree(d) != entry["files"]:
            sys.exit(f"model files under {d} changed since fetch (checksum mismatch); re-fetch or investigate")


def cmd_scan(a, cfg):
    from .facts import get
    verify(cfg)
    backend = get(cfg)
    out = open(a.out, "w") if a.out else sys.stdout
    n, t = 0, time.time()
    counts = {}
    for f in inventory(a.repo, cfg["models_dir"]):
        d = policy.route(f, cfg, backend)
        out.write(json.dumps(d) + "\n")
        counts[d["route"]] = counts.get(d["route"], 0) + 1
        n += 1
    if a.out:
        out.close()
    print(f"[filegate] {n} files in {time.time() - t:.1f}s via {backend.name}: {counts}", file=sys.stderr)


def cmd_eval(a, cfg):
    from .evaluate import evaluate, load_findings
    decisions = [json.loads(l) for l in open(a.decisions)]
    print(json.dumps(evaluate(decisions, load_findings(a.labels), cfg), indent=1))


def cmd_train(a, cfg):
    from . import head
    verify(cfg)
    from .evaluate import load_findings
    if len(a.repo) != len(a.labels):
        sys.exit("give one --labels per --repo")
    rows = []
    for repo, lab in zip(a.repo, a.labels):
        pos = {p for _, files in load_findings(lab) for p in files}
        for f in inventory(repo, cfg["models_dir"]):
            if rules.excluded(f, cfg["excludes"]):
                continue
            lvl, why = rules.level(f)
            k = rules.kind(f, lvl, why)
            if k in cfg["policy"]["gate_kinds"]:
                # group by repo + top-level dir, so CV never scores a component it trained on
                rows.append((f, k, int(f["path"] in pos), f"{Path(repo).name}:{f['path'].split('/')[0]}"))
    out = Path(cfg["models_dir"]) / cfg["head"]["path"]
    print(json.dumps(head.train(rows, cfg["models_dir"], str(out)), indent=1))
    print(f"saved {out}; set `backend: head` in your config to use it")


def main(argv=None):
    ap = argparse.ArgumentParser(prog="filegate", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--config", help="YAML config (defaults: built-in default.yaml)")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("fetch-models"); p.add_argument("--with", dest="with_", default="linguist")
    p = sub.add_parser("scan"); p.add_argument("repo"); p.add_argument("--out")
    p = sub.add_parser("eval"); p.add_argument("--decisions", required=True); p.add_argument("--labels", required=True)
    p = sub.add_parser("train"); p.add_argument("--repo", action="append", required=True); p.add_argument("--labels", action="append", required=True)
    a = ap.parse_args(argv)
    cfg = config.load(a.config)
    {"fetch-models": cmd_fetch, "scan": cmd_scan, "eval": cmd_eval, "train": cmd_train}[a.cmd](a, cfg)


if __name__ == "__main__":
    main()
