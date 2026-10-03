# filegate

**Decide, per file, whether an expensive LLM security scan is worth it.**

LLM code scanners that send every file to a frontier model get expensive on big
monorepos: frontend, backend, tests, infra and CI, each file billed. Glob
excludes are all-or-nothing. You can't exclude `*.scss` if some stylesheets pull
in remote URLs, or all tests if some exercise auth. filegate looks at each file
first and routes it:

| route | meaning |
|---|---|
| `excluded` | on your exclude list or binary, same as today |
| `cheap` | low risk: scan with a cheaper model (default), or `skip` if you configure it |
| `full` | scan with your main model |

Every decision carries a readable reason, for example
`code (JavaScript); nano risk 0.18 vs 0.26 [discounted: ui_only]` or
`config/data; nano risk 0.86 vs 0.37 (exec)`.

It runs **fully self-hosted and offline**. No file content leaves the machine,
and models load from a local folder with pinned revisions and checksums.

## How it decides

1. **Rules (free, deterministic).** Content type ([Magika](https://github.com/google/magika)),
   language and vendored/docs paths ([linguist](https://github.com/github-linguist/linguist) data)
   and content signals give every file a risk level 0–5. Docs, license files and
   stylesheets without imports are low risk. Production code, templates, CI/infra
   and anything with a possible secret always go to `full`.
2. **Narrow facts on the files rules can't settle:** tests, config/data and
   production JS/TS. Instead of asking "is this vulnerable?" (that scores at
   chance), filegate asks factual yes/no questions about what is *visible in the
   file*:
   - tests: does it exercise auth? send crafted input? do real I/O? is it a fuzz harness?
   - config: does it define commands or hooks that run? set security options? hold credentials? contain evaluated queries or templates?
   - JS/TS: does it only render UI? call the network? handle auth/tokens? insert raw HTML or redirects? read user input? run server-side?

   The answers form a risk profile. Backends: `regex` (default, free),
   `nano` ([OpenDecider-Nano](https://huggingface.co/manjunathshiva/opendecider-nano), ~0.4B, CPU),
   `systemone` (any self-hosted Jev-compatible server: Clef-flash, Kev, `opendecider serve`),
   or `head`.
3. **A classifier trained on your own scanner history** (`filegate train`):
   a frozen [gte-modernbert-base](https://huggingface.co/Alibaba-NLP/gte-modernbert-base)
   embedding plus logistic regression, on CPU. On the public proxy this was the
   strongest option once one or two misses are tolerated.

## Quick start

```bash
pip install "filegate[nano,head]"            # or plain `pip install filegate` for rules + regex only
filegate fetch-models --with linguist,nano,head   # once, where there is internet; writes models/MANIFEST.json
filegate scan path/to/repo --out decisions.jsonl  # offline
filegate eval --decisions decisions.jsonl --labels findings.jsonl   # findings caught vs $ saved
```

Train on your own history (files with confirmed findings from past scans):

```bash
filegate train --repo path/to/repo --labels labels.csv   # grouped-CV AUROC printed, head saved to models/
# then set `backend: head` in your config
```

Configure everything in YAML: excludes, questions, thresholds, backend, prices.
See [`filegate/default.yaml`](filegate/default.yaml) and
[`configs/example.yaml`](configs/example.yaml).

## What we measured (public proxy)

Labels: the 298 true-positive findings from [SastBench](https://arxiv.org/abs/2601.02941)
(CVE-fix commits, 148 repos). Savings measured on three large public
monorepos (grafana, sentry, posthog). Cost model: Opus 4.8 per file. Counted
per **finding**: a finding is caught if any of its files is scanned in full.

| policy | findings caught | off the monorepo scan bill |
|---|---|---|
| rules only | ~99% | 1–4% |
| narrow facts, OpenDecider-Nano | ~99.7% | ~17% |
| trained head on tests/config + JS/TS | ~99% | ~43% |

Details, caveats and what wasn't measured: [docs/RESULTS.md](docs/RESULTS.md).
The short version: the model decisions rest on **32 findings**, so the
approaches can be ranked but the exact percentages can't be trusted. Run
`filegate eval` on your own labels before relying on any threshold.

## Docs

- [docs/DEPLOY.md](docs/DEPLOY.md): air-gapped install, pinning, integration patterns
- [docs/LABELS.md](docs/LABELS.md): exporting labels from your scanner
- [docs/RESULTS.md](docs/RESULTS.md): the experiment behind the defaults
- [bench/README.md](bench/README.md): reproduce the public numbers

## License

Apache-2.0. Model weights fetched by `fetch-models` keep their own licenses
(OpenDecider-Nano and gte-modernbert-base are Apache-2.0; linguist data is MIT).
