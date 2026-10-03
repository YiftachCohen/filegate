# Labels: what to export from your scanner

filegate needs to know which files your scanner found real problems in. Two
formats; paths are relative to the repo root that you pass to `scan` / `train`.

## findings.jsonl (preferred)

One line per **confirmed** finding, listing every file the finding points at:

```json
{"id": "SCAN-1234", "files": ["services/api/auth.py", "services/api/tests/test_auth.py"]}
```

A finding counts as caught if **any** of its files is routed `full` (and
separately, `full` or `cheap`). This matters: a fix often touches a test that
exercises the vulnerable code, and per-file labels would wrongly make that test
look as risky as the vulnerable file.

## labels.csv (simple)

```csv
path,label
services/api/auth.py,1
web/src/components/Button.tsx,0
```

Each `label=1` file is treated as its own finding. Files not listed count as 0
for training.

## What to include

- Only **confirmed** findings (triaged as true positives). Unreviewed or
  false-positive findings teach the model the scanner's noise.
- Several repos if you can. `train` groups cross-validation by repo and top-level
  directory, so it never scores a component it trained on.
- Tens of findings that live in tests, config or JS/TS are the minimum for
  meaningful thresholds; hundreds are better.

## Privacy

`eval` prints aggregate counts, the cost estimate, and the IDs of missed
findings (up to 50). It never prints file content. Decisions and labels stay
wherever you run filegate.
