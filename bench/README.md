# Reproducing the public numbers

```bash
pip install -e ".[nano,head]"
filegate fetch-models --with linguist,nano

# 1. Labelled set. SastBench is not redistributed here (no data license is
#    stated); get sastbench-v0.1-original.json from its authors (arXiv:2601.02941).
python bench/sastbench.py --sastbench path/to/sastbench-v0.1-original.json --limit 20   # start small
python bench/sastbench.py --sastbench path/to/sastbench-v0.1-original.json              # all 148 repos, ~2 GB download

# 2. Size of the prize on large monorepos (cost only, no labels)
python bench/sastbench.py --monorepo grafana/grafana@<sha> --monorepo getsentry/sentry@<sha> --monorepo PostHog/posthog@<sha>
```

Switch backends with a config (`backend: nano`, `backend: head`) and pass it
with `--config`. Snapshots of the public repos are cached in `bench/.cache/`
(gitignored).

The original experiment computed its tables with a sampled, weighted analysis
(see [docs/RESULTS.md](../docs/RESULTS.md)). This script runs the shipped tool
on every file, so expect close but not identical numbers.
