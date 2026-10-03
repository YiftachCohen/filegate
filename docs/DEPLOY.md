# Deploying filegate in a locked-down environment

filegate is built for environments where customer code must never reach a
third-party service.

## Guarantees

- **No network at scan time.** `scan`, `eval` and `train` read only the repo
  and `models_dir`. The `nano` and `head` backends set `HF_HUB_OFFLINE=1`
  before loading.
- **No file content in outputs.** Decisions contain path, size, level, kind,
  fact probabilities and a reason, never file text. At most 1 MB of each file is
  read, and an 8 KB head is held in memory only while that file is scored.
- **Pinned, verified models.** `fetch-models` downloads fixed upstream
  revisions (see `PINS` in `filegate/cli.py`) and writes `MANIFEST.json` with a
  SHA-256 per file. Every `scan` refuses to run if a model file changed since.
- The only network calls are in `fetch-models` (GitHub raw + Hugging Face) and
  the optional `systemone` backend, which talks to a URL you configure.

## Air-gapped install

On a machine with internet:

```bash
pip download "filegate[nano,head]" -d wheels/      # or build a container image
filegate fetch-models --with linguist,nano,head --config prod.yaml   # models_dir: ./models
tar czf filegate-bundle.tgz wheels models prod.yaml
```

Inside the environment:

```bash
pip install --no-index --find-links wheels/ "filegate[nano,head]"
filegate --config prod.yaml scan /repos/monorepo --out decisions.jsonl
```

Mount `models/` read-only. To upgrade a model, change its revision in `PINS`,
re-fetch, re-run `filegate eval` on your labels, and ship the new bundle.

## Integration patterns

1. **Library inside the scanner** (lowest ops cost):

   ```python
   from filegate import config, policy
   from filegate.facts import get
   from filegate.cli import verify
   from filegate.inventory import scan

   cfg = config.load("prod.yaml")
   verify(cfg)                 # checksum the model files once at startup
   backend = get(cfg)
   for f in scan(repo_path, cfg["models_dir"]):
       d = policy.route(f, cfg, backend)   # d["route"] in {"excluded", "cheap", "full"}, d["reason"]
       ...
   ```

2. **Pre-pass CLI step:** run `filegate scan` before the scanner and feed it
   the `full` / `cheap` lists from `decisions.jsonl`.
3. **Shared decision service:** run a Jev-compatible server (Clef-flash on a GPU,
   or `opendecider serve` on CPU) on your own infrastructure and point
   `backend: systemone` at it. Only worth it at high volume.

## Sizing (measured on an Apple Silicon laptop, CPU only)

| backend | per gated file | notes |
|---|---|---|
| regex | < 1 ms | deterministic |
| nano (4–8 facts, 512 tokens) | ~0.8–3 s | only tests, config and JS/TS are gated |
| head | ~0.7–0.9 s | one embedding pass |

Rough cost per file on a general-purpose cloud CPU instance is around $0.0001,
against roughly $0.04 for a frontier-model scan call. Compute doesn't decide
this; the miss rate does.

## Recommended rollout

1. Run with `backend: regex` and `low_risk_route: cheap` in shadow mode: scan
   everything as today, and log filegate's decisions.
2. Export labels from past scans ([LABELS.md](LABELS.md)) and run `filegate eval`.
3. Try `nano`, then `filegate train` + `head`. Pick thresholds per kind from the
   `eval` output at the miss rate you can accept.
4. Turn routing on. Keep `cheap` rather than `skip` unless the numbers on your
   own labels say skipping is safe.
